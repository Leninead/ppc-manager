"""Bring the VPS Amazon Ads authorizations into a local stack, re-sealed for the local worker key.

`scripts/` is not in the image, so the script is piped from the repo root (ciphertext only crosses the wire):

    ssh <user>@<vps-host> 'cd <deploy-dir> && docker compose ... run --rm -T \
        -e BRIDGE_TARGET_PUBLIC_KEY_B64=<base64 of the local integration_settings.sealing_public_key> \
        integrations-worker python - export' < scripts/amazon_ads_bridge.py > bundle.json

    docker compose ... run --rm -T -e BRIDGE_ALLOW_IMPORT=local -v <absolute-path>/bundle.json:/tmp/bundle.json:ro \
        integrations-worker python - import --bundle /tmp/bundle.json < scripts/amazon_ads_bridge.py
"""
from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import json
import logging
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import requests
from cryptography.exceptions import UnsupportedAlgorithm
from cryptography.hazmat.primitives import serialization

from core.integrations import crypto, worker
from core.integrations.amazon_identity import SLUG
from core.integrations.store import (
    ACCOUNTS_TABLE,
    ACTIVE_STATUS,
    CONNECTIONS_TABLE,
    CREDENTIALS_TABLE,
    INVALID_STATUS,
    SEALING_KEY_SETTING,
    _Rest,
    fingerprint,
)

log = logging.getLogger("integrations.amazon_ads_bridge")

BUNDLE_FORMAT = "amazon_ads_bridge/v1"
TARGET_KEY_ENV = "BRIDGE_TARGET_PUBLIC_KEY_B64"
ALLOW_IMPORT_ENV = "BRIDGE_ALLOW_IMPORT"
ALLOW_IMPORT_VALUE = "local"
BRIDGE_ACTOR = "bridge"
EXTERNAL_ID_CONFLICT = "integration_slug,cuenta_externa_id"

_CREDENTIAL_COLUMNS = "label,public_fields,secret_sealed,fingerprint"
_CONNECTION_COLUMNS = (
    "id,cliente,cuenta_externa_id,nombre_externo,marketplace,estado,conectado_por,"
    "consent_date,scopes,metadata,refresh_token_sealed"
)
_ACCOUNT_COLUMNS = (
    "cuenta_externa_id,nombre_externo,tipo,region,marketplaces,cliente,connection_id,profiles,last_seen_at"
)
_CONNECTION_WRITE_COLUMNS = (
    "cliente", "cuenta_externa_id", "nombre_externo", "marketplace", "estado",
    "conectado_por", "consent_date", "scopes", "refresh_token_sealed",
)
_ACCOUNT_WRITE_COLUMNS = (
    "cuenta_externa_id", "nombre_externo", "tipo", "region", "marketplaces", "cliente", "profiles", "last_seen_at",
)


class BridgeError(RuntimeError):
    """The bridge refuses to go on."""


@dataclass(frozen=True)
class ImportSummary:
    source_key_fp: str
    target_key_fp: str
    credential_action: str
    connection_ids: dict[int, int]
    account_count: int

    def as_line(self) -> str:
        remap = ", ".join(f"{source}->{local}" for source, local in self.connection_ids.items())
        return (
            f"bridge import ok · key {self.source_key_fp} -> {self.target_key_fp} · "
            f"credential {self.credential_action} · connections {len(self.connection_ids)} ({remap}) · "
            f"accounts {self.account_count}"
        )


def key_fingerprint(public_pem: str) -> str:
    """sha256 of the DER SubjectPublicKeyInfo, first 12 hex chars: the same key reads the same in any PEM layout."""
    try:
        public_key = serialization.load_pem_public_key(public_pem.encode("ascii"))
    except (ValueError, TypeError, UnicodeEncodeError, UnsupportedAlgorithm) as exc:
        raise BridgeError(f"not a PEM public key ({type(exc).__name__})") from exc
    der = public_key.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    return hashlib.sha256(der).hexdigest()[:12]


def _fingerprint_of(public_pem: str | None, source: str) -> str:
    if not public_pem:
        raise BridgeError(f"{source} is missing")
    try:
        return key_fingerprint(public_pem)
    except BridgeError as exc:
        raise BridgeError(f"{source}: {exc}") from exc


def _verified_own_key_fp(rest: _Rest, private_pem: str) -> str:
    own_fp = key_fingerprint(crypto.public_from_private(private_pem))
    published_fp = _fingerprint_of(rest.get_setting(SEALING_KEY_SETTING), f"integration_settings.{SEALING_KEY_SETTING}")
    if own_fp != published_fp:
        raise BridgeError(f"the worker key ({own_fp}) is not the key this database published ({published_fp})")
    return own_fp


def target_public_key_from_env() -> str:
    encoded = os.environ.get(TARGET_KEY_ENV, "").strip()
    if not encoded:
        raise BridgeError(f"missing {TARGET_KEY_ENV} (base64 of the local sealing public key)")
    try:
        return base64.b64decode(encoded, validate=True).decode("ascii")
    except (binascii.Error, UnicodeDecodeError) as exc:
        raise BridgeError(f"{TARGET_KEY_ENV} is not base64 of a PEM file") from exc


def export_bundle(rest: _Rest, source_private_pem: str, target_public_pem: str,
                  connection_ids: tuple[int, ...] = (), now: datetime | None = None) -> dict:
    """Read-only on the source: check both keys, then re-seal the credential and the refresh tokens for the target."""
    source_key_fp = _verified_own_key_fp(rest, source_private_pem)
    target_key_fp = _fingerprint_of(target_public_pem, TARGET_KEY_ENV)
    if target_key_fp == source_key_fp:
        raise BridgeError("the target key is the source key: the bundle would only open on the VPS")

    credential = _read_credential(rest)
    connections = _read_connections(rest, connection_ids)
    accounts = _read_accounts(rest, [int(row["id"]) for row in connections])
    log.info("keys verified (source %s, target %s); re-sealing %d connections", source_key_fp, target_key_fp,
             len(connections))
    return {
        "format": BUNDLE_FORMAT,
        "exported_at": (now or datetime.now(timezone.utc)).isoformat(),
        "source_key_fp": source_key_fp,
        "target_key_fp": target_key_fp,
        "credential": {
            "label": credential.get("label") or "",
            "public_fields": credential.get("public_fields") or {},
            "fingerprint": credential.get("fingerprint") or fingerprint(credential["secret_sealed"]),
            "secret_sealed": _reseal(credential["secret_sealed"], source_private_pem, target_public_pem),
        },
        "connections": [
            {**row, "refresh_token_sealed": _reseal(row["refresh_token_sealed"], source_private_pem, target_public_pem)}
            for row in connections
        ],
        "accounts": accounts,
    }


def _reseal(sealed: str, source_private_pem: str, target_public_pem: str) -> str:
    return crypto.seal(crypto.unseal(sealed, source_private_pem), target_public_pem)


def _read_credential(rest: _Rest) -> dict:
    rows = rest.select(
        CREDENTIALS_TABLE,
        {"select": _CREDENTIAL_COLUMNS, "integration_slug": f"eq.{SLUG}", "estado": f"eq.{ACTIVE_STATUS}",
         "limit": "1"},
    )
    if not rows or not rows[0].get("secret_sealed"):
        raise BridgeError(f"{SLUG} has no active credential with a sealed secret")
    return rows[0]


def _read_connections(rest: _Rest, connection_ids: tuple[int, ...]) -> list[dict]:
    params = {"select": _CONNECTION_COLUMNS, "integration_slug": f"eq.{SLUG}", "estado": f"eq.{ACTIVE_STATUS}",
              "order": "id.asc"}
    if connection_ids:
        params["id"] = f"in.({','.join(str(connection_id) for connection_id in connection_ids)})"
    rows = rest.select(CONNECTIONS_TABLE, params)
    missing = sorted(set(connection_ids) - {int(row["id"]) for row in rows})
    if missing:
        raise BridgeError(f"{SLUG} connections not found or not active: {missing}")
    if not rows:
        raise BridgeError(f"no active {SLUG} connection to export")
    without_token = [int(row["id"]) for row in rows if not row.get("refresh_token_sealed")]
    if without_token:
        raise BridgeError(f"connections without a sealed refresh token: {without_token} "
                          "(pick the others with --connection-id)")
    return rows


def _read_accounts(rest: _Rest, connection_ids: list[int]) -> list[dict]:
    return rest.select(
        ACCOUNTS_TABLE,
        {"select": _ACCOUNT_COLUMNS, "integration_slug": f"eq.{SLUG}",
         "connection_id": f"in.({','.join(str(connection_id) for connection_id in connection_ids)})",
         "order": "id.asc"},
    )


def require_import_flag() -> None:
    if os.environ.get(ALLOW_IMPORT_ENV, "").strip() != ALLOW_IMPORT_VALUE:
        raise BridgeError(f"import writes to this database: set {ALLOW_IMPORT_ENV}={ALLOW_IMPORT_VALUE} "
                          "on a local stack")


def load_bundle(path: Path) -> dict:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise BridgeError(f"cannot read the bundle at {path}: {exc.strerror}") from exc
    # A PowerShell 5 redirect writes UTF-16, not UTF-8.
    encoding = "utf-16" if raw[:2] in (b"\xff\xfe", b"\xfe\xff") else "utf-8-sig"
    try:
        return json.loads(raw.decode(encoding))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BridgeError(f"the bundle at {path} is not JSON ({exc})") from exc


def import_bundle(rest: _Rest, local_private_pem: str, bundle: dict, now: datetime) -> ImportSummary:
    """Write the bundle into the local database, only after every key check and a round-trip unseal pass."""
    _validate_bundle(bundle)
    local_key_fp = _verified_own_key_fp(rest, local_private_pem)
    if local_key_fp != bundle["target_key_fp"]:
        raise BridgeError(f"the bundle is sealed for key {bundle['target_key_fp']}, this stack holds {local_key_fp}")
    if local_key_fp == bundle["source_key_fp"]:
        raise BridgeError("this stack holds the source key: refusing to import into the VPS")
    _check_bundle_opens(bundle, local_private_pem)

    credential_action = _write_credential(rest, bundle["credential"], local_private_pem)
    connection_ids = _write_connections(rest, bundle["connections"], now)
    _write_accounts(rest, bundle["accounts"], connection_ids, now)
    summary = ImportSummary(
        source_key_fp=bundle["source_key_fp"],
        target_key_fp=local_key_fp,
        credential_action=credential_action,
        connection_ids=connection_ids,
        account_count=len(bundle["accounts"]),
    )
    rest.audit("bridge_import", slug=SLUG, actor=BRIDGE_ACTOR, detail={
        "source_key_fp": summary.source_key_fp,
        "target_key_fp": summary.target_key_fp,
        "credential": credential_action,
        "connections": {str(source): local for source, local in connection_ids.items()},
        "accounts": summary.account_count,
    })
    return summary


def _validate_bundle(bundle: object) -> None:
    if not isinstance(bundle, dict) or bundle.get("format") != BUNDLE_FORMAT:
        raise BridgeError(f"not an {BUNDLE_FORMAT} bundle")
    missing = [key for key in ("source_key_fp", "target_key_fp", "credential", "connections", "accounts")
               if key not in bundle]
    if missing:
        raise BridgeError(f"the bundle is missing {missing}")
    credential = bundle["credential"]
    if not isinstance(credential, dict) or not (credential.get("secret_sealed") and credential.get("fingerprint")):
        raise BridgeError("the bundle credential has no sealed secret or fingerprint")
    if not isinstance(bundle["connections"], list) or not isinstance(bundle["accounts"], list):
        raise BridgeError("the bundle connections and accounts must be lists")
    incomplete = [connection for connection in bundle["connections"]
                  if not (isinstance(connection, dict) and isinstance(connection.get("id"), int)
                          and connection.get("cuenta_externa_id") and connection.get("refresh_token_sealed"))]
    if incomplete:
        raise BridgeError(f"{len(incomplete)} bundle connections lack an id, cuenta_externa_id or refresh token")
    carried_ids = {connection["id"] for connection in bundle["connections"]}
    orphans = [account for account in bundle["accounts"]
               if not isinstance(account, dict) or not account.get("cuenta_externa_id")
               or account.get("connection_id") not in carried_ids]
    if orphans:
        raise BridgeError(f"{len(orphans)} bundle accounts lack a cuenta_externa_id or a carried connection")


def _check_bundle_opens(bundle: dict, local_private_pem: str) -> None:
    sealed_values = [bundle["credential"]["secret_sealed"]]
    sealed_values += [connection["refresh_token_sealed"] for connection in bundle["connections"]]
    try:
        for sealed in sealed_values:
            crypto.unseal(sealed, local_private_pem)
    except crypto.SealError as exc:
        raise BridgeError("a sealed value in the bundle does not open with this stack's key") from exc


def _write_credential(rest: _Rest, credential: dict, local_private_pem: str) -> str:
    active = rest.select(
        CREDENTIALS_TABLE,
        {"select": "id,fingerprint,secret_sealed", "integration_slug": f"eq.{SLUG}",
         "estado": f"eq.{ACTIVE_STATUS}"},
    )
    # The fingerprint names the secret, not the key it is sealed with: a row sealed for an older key must be replaced.
    if any(row.get("fingerprint") == credential["fingerprint"] and _opens(row.get("secret_sealed"), local_private_pem)
           for row in active):
        log.info("credential %s is already the active one, kept", credential["fingerprint"])
        return "kept"
    if active:
        rest.update(
            CREDENTIALS_TABLE,
            {"integration_slug": f"eq.{SLUG}", "estado": f"eq.{ACTIVE_STATUS}"},
            {"estado": INVALID_STATUS, "rotated_by": BRIDGE_ACTOR},
        )
        log.info("retired %d local %s credentials", len(active), SLUG)
    rest.insert(CREDENTIALS_TABLE, {
        "integration_slug": SLUG,
        "label": credential.get("label") or "",
        "public_fields": credential.get("public_fields") or {},
        "secret_sealed": credential["secret_sealed"],
        "fingerprint": credential["fingerprint"],
        "estado": ACTIVE_STATUS,
        "created_by": BRIDGE_ACTOR,
    })
    log.info("credential %s bridged", credential["fingerprint"])
    return "bridged"


def _opens(sealed: str | None, private_pem: str) -> bool:
    if not sealed:
        return False
    try:
        crypto.unseal(sealed, private_pem)
    except crypto.SealError:
        return False
    return True


def _write_connections(rest: _Rest, connections: list[dict], now: datetime) -> dict[int, int]:
    local_ids: dict[int, int] = {}
    for connection in connections:
        source_id = int(connection["id"])
        row = {column: connection[column] for column in _CONNECTION_WRITE_COLUMNS if column in connection}
        row["integration_slug"] = SLUG
        row["last_error"] = ""
        row["metadata"] = {
            **(connection.get("metadata") or {}),
            "bridge": {"source": "vps", "source_connection_id": source_id, "imported_at": now.isoformat()},
        }
        # The local id is whatever this database assigned; sending the VPS id would collide with local rows.
        rest.upsert(CONNECTIONS_TABLE, row, on_conflict=EXTERNAL_ID_CONFLICT)
        local_id = worker._connection_id(rest, SLUG, connection["cuenta_externa_id"])
        if local_id is None:
            raise BridgeError(f"connection {source_id} was upserted but cannot be read back")
        local_ids[source_id] = local_id
        log.info("connection %d (%s) -> local id %d", source_id, connection.get("cliente", ""), local_id)
    return local_ids


def _write_accounts(rest: _Rest, accounts: list[dict], local_connection_ids: dict[int, int], now: datetime) -> None:
    for account in accounts:
        row = {column: account[column] for column in _ACCOUNT_WRITE_COLUMNS if column in account}
        row["integration_slug"] = SLUG
        row["connection_id"] = local_connection_ids[int(account["connection_id"])]
        row["updated_at"] = now.isoformat()
        rest.upsert(ACCOUNTS_TABLE, row, on_conflict=EXTERNAL_ID_CONFLICT)
    log.info("%d client accounts upserted", len(accounts))


def existing_worker_key() -> str:
    """The worker's private key, env var first, then the key file; never creates one.

    The export runs inside the image deployed on the VPS, which can be older than this script,
    so it only relies on crypto names that predate the Amazon Ads sync.
    """
    from_env = os.environ.get(crypto.PRIVATE_KEY_ENV, "").strip()
    if from_env:
        return from_env.replace("\\n", "\n")
    key_path = crypto.private_key_path()
    try:
        return key_path.read_text(encoding="ascii")
    except (OSError, UnicodeDecodeError) as exc:
        raise BridgeError(f"no worker key: {crypto.PRIVATE_KEY_ENV} is not set and {key_path} is unreadable") from exc


def command_export(connection_ids: tuple[int, ...]) -> int:
    bundle = export_bundle(worker._rest_worker(), existing_worker_key(), target_public_key_from_env(),
                           connection_ids)
    print(json.dumps(bundle, separators=(",", ":")))
    log.info("bundle written: %d connections, %d accounts", len(bundle["connections"]), len(bundle["accounts"]))
    return 0


def command_import(bundle_path: Path) -> int:
    require_import_flag()
    bundle = load_bundle(bundle_path)
    summary = import_bundle(worker._rest_worker(), existing_worker_key(), bundle,
                            datetime.now(timezone.utc))
    print(summary.as_line())
    return 0


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(prog="amazon_ads_bridge",
                                     description="Re-seal the VPS Amazon Ads authorizations for a local stack.")
    commands = parser.add_subparsers(dest="command", required=True)
    export_parser = commands.add_parser("export", help=f"on the VPS: print a bundle sealed for {TARGET_KEY_ENV}")
    export_parser.add_argument("--connection-id", dest="connection_ids", type=int, nargs="+", action="extend",
                               metavar="N", help="only these connections (default: every active one)")
    import_parser = commands.add_parser("import", help=f"on a local stack: write a bundle ({ALLOW_IMPORT_ENV}=local)")
    import_parser.add_argument("--bundle", required=True, type=Path, metavar="PATH")
    args = parser.parse_args(argv)

    try:
        if args.command == "export":
            return command_export(tuple(args.connection_ids or ()))
        return command_import(args.bundle)
    except (BridgeError, worker.WorkerError, crypto.SealError, requests.RequestException) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
