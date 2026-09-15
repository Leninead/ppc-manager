"""amazon_ads_bridge: key checks, read-only export, re-seal for the target key, local import. No network."""
from __future__ import annotations

import base64
import copy
import hashlib
import importlib.util
import json
import logging
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization

from core.integrations import crypto, oauth, worker
from core.integrations.store import ACCOUNTS_TABLE, CONNECTIONS_TABLE, CREDENTIALS_TABLE, SETTINGS_TABLE, _Rest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "amazon_ads_bridge.py"

_spec = importlib.util.spec_from_file_location("amazon_ads_bridge", SCRIPT)
bridge = importlib.util.module_from_spec(_spec)
# dataclasses resolve string annotations through sys.modules, so the module must be registered before it runs.
sys.modules[_spec.name] = bridge
_spec.loader.exec_module(bridge)

CLIENT_SECRET = "client-secret-plaintext-0001"
REFRESH_TOKENS = {41: "Atzr|refresh-plaintext-41", 42: "Atzr|refresh-plaintext-42", 43: "Atzr|refresh-plaintext-43"}
NOW = datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc)
AUDIT_FORBIDDEN_KEYS = {"secret", "token", "api_key", "client_secret", "password", "refresh_token", "verifier"}


@pytest.fixture(scope="module")
def source_keys():
    return crypto.generate_keypair()


@pytest.fixture(scope="module")
def target_keys():
    return crypto.generate_keypair()


@pytest.fixture(scope="module")
def stray_keys():
    return crypto.generate_keypair()


def _matches(row: dict, params: dict) -> bool:
    for column, condition in params.items():
        if column in ("select", "order", "limit"):
            continue
        operator, _, operand = condition.partition(".")
        cell = str(row.get(column))
        if operator == "eq":
            if cell != operand:
                return False
        elif operator == "in":
            if cell not in operand.strip("()").split(","):
                return False
        else:
            raise AssertionError(f"filter the fake does not model: {column}={condition}")
    return True


def _query(rows: list[dict], params: dict) -> list[dict]:
    matched = [row for row in rows if _matches(row, params)]
    if params.get("order") == "id.asc":
        matched.sort(key=lambda row: row["id"])
    if "limit" in params:
        matched = matched[: int(params["limit"])]
    columns = params.get("select")
    if not columns:
        return copy.deepcopy(matched)
    return [{column: copy.deepcopy(row[column]) for column in columns.split(",") if column in row} for row in matched]


class _Response:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _ReadOnlySession:
    """Source database behind a real `_Rest`: GETs are served from memory, any other verb is a recorded write."""

    def __init__(self, tables: dict):
        self.tables = tables
        self.writes: list[str] = []

    def get(self, url, params=None, headers=None, timeout=None):
        return _Response(_query(self.tables.get(url.rsplit("/", 1)[-1], []), params or {}))

    def __getattr__(self, verb):
        def write(*args, **kwargs):
            self.writes.append(verb)
            raise AssertionError(f"the export sent a {verb} to the source database")
        return write


class _LocalRest:
    """Local database stand-in with the `_Rest` calls the import is allowed to make."""

    def __init__(self, tables: dict):
        self.tables = tables
        self.writes: list[tuple] = []
        self.audits: list[dict] = []
        self._last_id = 100

    def get_setting(self, key):
        rows = _query(self.tables[SETTINGS_TABLE], {"clave": f"eq.{key}"})
        return rows[0]["valor"] if rows else None

    def select(self, table, params):
        return _query(self.tables.setdefault(table, []), params)

    def insert(self, table, row):
        self.writes.append(("insert", table, copy.deepcopy(row)))
        active_filter = {"integration_slug": f"eq.{row.get('integration_slug')}", "estado": "eq.activo"}
        if table == CREDENTIALS_TABLE and row.get("estado") == "activo" and _query(self.tables[table], active_filter):
            raise AssertionError("integration_credentials_activa_idx: a second active credential")
        self.tables.setdefault(table, []).append({"id": self._next_id(), **copy.deepcopy(row)})

    def upsert(self, table, row, on_conflict=None):
        self.writes.append(("upsert", table, copy.deepcopy(row), on_conflict))
        keys = on_conflict.split(",")
        rows = self.tables.setdefault(table, [])
        existing = next((stored for stored in rows if all(stored.get(key) == row[key] for key in keys)), None)
        if existing is None:
            rows.append({"id": self._next_id(), **copy.deepcopy(row)})
        else:
            existing.update(copy.deepcopy(row))

    def update(self, table, params, changes, stamp=True):
        self.writes.append(("update", table, dict(params), dict(changes)))
        for stored in self.tables.get(table, []):
            if _matches(stored, params):
                stored.update(changes)

    def audit(self, action, *, slug=None, actor="", detail=None):
        self.audits.append({"accion": action, "integration_slug": slug, "actor": actor, "detalle": detail or {}})

    def _next_id(self):
        self._last_id += 1
        return self._last_id


def _source_connection(public_pem: str, connection_id: int, estado: str, external_id: str, cliente: str) -> dict:
    return {
        "id": connection_id, "integration_slug": "amazon_ads", "cliente": cliente, "cuenta_externa_id": external_id,
        "nombre_externo": f"Usuario {connection_id}", "marketplace": "NA", "estado": estado,
        "conectado_por": "am.demo", "consent_date": "2026-08-01", "scopes": ["advertising::campaign_management"],
        "metadata": {"regions": ["NA"]}, "last_error": "",
        "refresh_token_sealed": crypto.seal(REFRESH_TOKENS[connection_id], public_pem),
    }


def _source_account(account_id: int, external_id: str, connection_id: int, cliente: str) -> dict:
    return {
        "id": account_id, "integration_slug": "amazon_ads", "cuenta_externa_id": external_id,
        "nombre_externo": f"Marca {account_id}", "tipo": "seller", "region": "NA", "marketplaces": ["US", "MX"],
        "cliente": cliente, "connection_id": connection_id, "first_seen_at": "2026-08-01T06:00:00+00:00",
        "profiles": [{"profile_id": f"90{account_id}", "country_code": "US"}],
        "last_seen_at": "2026-09-13T06:00:00+00:00",
    }


def _source_tables(source_public_pem: str, published_pem: str | None = None) -> dict:
    return {
        SETTINGS_TABLE: [{"clave": "sealing_public_key", "valor": published_pem or source_public_pem}],
        CREDENTIALS_TABLE: [
            {"id": 2, "integration_slug": "amazon_ads", "estado": "invalido", "label": "retirada",
             "public_fields": {}, "secret_sealed": crypto.seal("retired-secret", source_public_pem),
             "fingerprint": "old000"},
            {"id": 3, "integration_slug": "amazon_ads", "estado": "activo", "label": "Security profile demo",
             "public_fields": {"client_id": "amzn1.application-oa2-client.demo"},
             "secret_sealed": crypto.seal(CLIENT_SECRET, source_public_pem), "fingerprint": "a1b2c3"},
        ],
        CONNECTIONS_TABLE: [
            _source_connection(source_public_pem, 41, "activo", "amzn1.account.AAA", "demo-uno"),
            _source_connection(source_public_pem, 42, "activo", "amzn1.account.BBB", "demo-dos"),
            _source_connection(source_public_pem, 43, "needs_reauth", "amzn1.account.CCC", "demo-tres"),
        ],
        ACCOUNTS_TABLE: [
            _source_account(501, "ENTITY1", 41, "marca-uno"),
            _source_account(502, "ENTITY2", 42, "marca-dos"),
            _source_account(503, "ENTITY3", 42, "marca-tres"),
            _source_account(504, "ENTITY4", 43, "marca-cuatro"),
        ],
    }


def _local_tables(local_public_pem: str) -> dict:
    return {
        SETTINGS_TABLE: [{"clave": "sealing_public_key", "valor": local_public_pem}],
        CREDENTIALS_TABLE: [
            {"id": 1, "integration_slug": "amazon_ads", "estado": "activo", "label": "local",
             "public_fields": {"client_id": "local-client"}, "fingerprint": "loc123", "created_by": "dev"},
        ],
        CONNECTIONS_TABLE: [
            {"id": 7, "integration_slug": "amazon_ads", "cliente": "etiqueta-local",
             "cuenta_externa_id": "amzn1.account.BBB", "estado": "needs_reauth", "last_error": "invalid_grant",
             "metadata": {}},
            {"id": 8, "integration_slug": "mercado_libre", "cliente": "vendedor-demo", "cuenta_externa_id": "41",
             "estado": "activo", "metadata": {}},
        ],
        ACCOUNTS_TABLE: [
            {"id": 9, "integration_slug": "amazon_ads", "cuenta_externa_id": "ENTITY3",
             "cliente": "etiqueta-editada-local", "connection_id": 7, "profiles": []},
        ],
    }


def _export(source_keys, target_keys, tables=None, connection_ids=()):
    session = _ReadOnlySession(tables or _source_tables(source_keys[1]))
    rest = _Rest("http://rest-gateway", "worker-jwt", session=session)
    return bridge.export_bundle(rest, source_keys[0], target_keys[1], connection_ids, now=NOW), session


def _import(target_keys, bundle, tables=None):
    rest = _LocalRest(tables or _local_tables(target_keys[1]))
    return bridge.import_bundle(rest, target_keys[0], copy.deepcopy(bundle), NOW), rest


@pytest.fixture(scope="module")
def bundle(source_keys, target_keys):
    exported, _ = _export(source_keys, target_keys)
    return exported


@pytest.fixture
def forbidden_calls(monkeypatch):
    """Creating keys, rotating tokens or talking to Login with Amazon is never part of the bridge."""
    calls: list[str] = []

    def forbid(name):
        def call(*args, **kwargs):
            calls.append(name)
            raise AssertionError(f"the bridge called {name}")
        return call

    for owner, name in ((worker, "ensure_keys"), (worker, "_rotate_token"), (crypto, "load_or_create_private_key"),
                        (oauth, "refresh"), (oauth, "exchange_code")):
        monkeypatch.setattr(owner, name, forbid(name))
    return calls


def _run_export_command(monkeypatch, source_keys, target_keys):
    session = _ReadOnlySession(_source_tables(source_keys[1]))
    monkeypatch.setattr(worker, "_rest_worker", lambda: _Rest("http://rest-gateway", "worker-jwt", session=session))
    monkeypatch.setenv(crypto.PRIVATE_KEY_ENV, source_keys[0].replace("\n", "\\n"))
    monkeypatch.setenv(bridge.TARGET_KEY_ENV, base64.b64encode(target_keys[1].encode("ascii")).decode("ascii"))
    return bridge.main(["export"]), session


def test_key_fingerprint_is_the_first_12_hex_of_sha256_over_the_der_key(source_keys):
    der = serialization.load_pem_public_key(source_keys[1].encode("ascii")).public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)

    assert bridge.key_fingerprint(source_keys[1]) == hashlib.sha256(der).hexdigest()[:12]
    assert bridge.key_fingerprint(source_keys[1].replace("\n", "\r\n")) == bridge.key_fingerprint(source_keys[1])


def test_export_refuses_a_worker_key_the_source_database_did_not_publish(source_keys, target_keys, stray_keys):
    tables = _source_tables(source_keys[1], published_pem=stray_keys[1])

    with pytest.raises(bridge.BridgeError, match="not the key this database published"):
        _export(source_keys, target_keys, tables)


def test_export_refuses_when_the_source_database_published_no_key(source_keys, target_keys):
    tables = _source_tables(source_keys[1])
    tables[SETTINGS_TABLE] = []

    with pytest.raises(bridge.BridgeError, match="sealing_public_key is missing"):
        _export(source_keys, target_keys, tables)


def test_export_refuses_a_target_key_equal_to_the_source_key(source_keys):
    with pytest.raises(bridge.BridgeError, match="target key is the source key"):
        _export(source_keys, source_keys)


def test_export_reseals_so_only_the_target_key_opens_values(source_keys, target_keys, bundle):
    sealed_values = [bundle["credential"]["secret_sealed"]]
    sealed_values += [connection["refresh_token_sealed"] for connection in bundle["connections"]]

    assert [crypto.unseal(sealed, target_keys[0]) for sealed in sealed_values] == [
        CLIENT_SECRET, REFRESH_TOKENS[41], REFRESH_TOKENS[42]]
    for sealed in sealed_values:
        with pytest.raises(crypto.SealError):
            crypto.unseal(sealed, source_keys[0])
    assert bundle["format"] == "amazon_ads_bridge/v1"
    assert bundle["source_key_fp"] == bridge.key_fingerprint(source_keys[1])
    assert bundle["target_key_fp"] == bridge.key_fingerprint(target_keys[1])
    assert bundle["credential"]["fingerprint"] == "a1b2c3"


def test_export_carries_active_connections_and_only_their_accounts(bundle):
    assert [connection["id"] for connection in bundle["connections"]] == [41, 42]
    assert [account["cuenta_externa_id"] for account in bundle["accounts"]] == ["ENTITY1", "ENTITY2", "ENTITY3"]


def test_export_narrows_to_the_requested_connections(source_keys, target_keys):
    narrowed, _ = _export(source_keys, target_keys, connection_ids=(42,))

    assert [connection["id"] for connection in narrowed["connections"]] == [42]
    assert {account["connection_id"] for account in narrowed["accounts"]} == {42}


def test_export_refuses_a_requested_connection_that_is_not_active(source_keys, target_keys):
    with pytest.raises(bridge.BridgeError, match=r"not found or not active: \[43\]"):
        _export(source_keys, target_keys, connection_ids=(41, 43))


def test_export_command_only_reads_the_source_and_prints_one_json_line(
        monkeypatch, capsys, source_keys, target_keys, forbidden_calls):
    exit_code, session = _run_export_command(monkeypatch, source_keys, target_keys)

    out = capsys.readouterr().out
    assert exit_code == 0
    assert session.writes == []
    assert forbidden_calls == []
    assert len(out.splitlines()) == 1
    assert json.loads(out)["format"] == "amazon_ads_bridge/v1"


def test_export_command_runs_on_an_image_that_predates_this_ticket(
        monkeypatch, capsys, source_keys, target_keys, tmp_path):
    monkeypatch.delattr(crypto, "read_existing_private_key", raising=False)
    key_file = tmp_path / "sealing_private.pem"
    key_file.write_text(source_keys[0], encoding="ascii")
    monkeypatch.setenv(crypto.PRIVATE_KEY_FILE_ENV, str(key_file))
    session = _ReadOnlySession(_source_tables(source_keys[1]))
    monkeypatch.setattr(worker, "_rest_worker", lambda: _Rest("http://rest-gateway", "worker-jwt", session=session))
    monkeypatch.delenv(crypto.PRIVATE_KEY_ENV, raising=False)
    monkeypatch.setenv(bridge.TARGET_KEY_ENV, base64.b64encode(target_keys[1].encode("ascii")).decode("ascii"))

    assert bridge.main(["export"]) == 0
    assert json.loads(capsys.readouterr().out)["source_key_fp"] == bridge.key_fingerprint(source_keys[1])


def test_export_command_refuses_a_target_that_is_not_base64(monkeypatch, capsys, source_keys, target_keys):
    monkeypatch.setattr(worker, "_rest_worker", lambda: _Rest("http://rest-gateway", "worker-jwt",
                                                              session=_ReadOnlySession(_source_tables(source_keys[1]))))
    monkeypatch.setenv(crypto.PRIVATE_KEY_ENV, source_keys[0].replace("\n", "\\n"))
    monkeypatch.setenv(bridge.TARGET_KEY_ENV, target_keys[1])

    assert bridge.main(["export"]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert bridge.TARGET_KEY_ENV in captured.err


@pytest.mark.parametrize("flag", [None, "", "production", "1"])
def test_import_command_refuses_without_the_local_flag(monkeypatch, capsys, tmp_path, target_keys, bundle, flag):
    bundle_path = tmp_path / "bundle.json"
    bundle_path.write_text(json.dumps(bundle), encoding="utf-8")
    opened_databases = []
    monkeypatch.setattr(worker, "_rest_worker", lambda: opened_databases.append("rest") or _LocalRest({}))
    if flag is None:
        monkeypatch.delenv(bridge.ALLOW_IMPORT_ENV, raising=False)
    else:
        monkeypatch.setenv(bridge.ALLOW_IMPORT_ENV, flag)

    assert bridge.main(["import", "--bundle", str(bundle_path)]) == 2
    assert opened_databases == []
    assert "BRIDGE_ALLOW_IMPORT=local" in capsys.readouterr().err


def test_import_refuses_a_bundle_sealed_for_another_key(stray_keys, bundle):
    rest = _LocalRest(_local_tables(stray_keys[1]))

    with pytest.raises(bridge.BridgeError, match="the bundle is sealed for key"):
        bridge.import_bundle(rest, stray_keys[0], copy.deepcopy(bundle), NOW)
    assert rest.writes == []
    assert rest.audits == []


def test_import_refuses_when_the_local_key_is_not_the_published_one(target_keys, stray_keys, bundle):
    rest = _LocalRest(_local_tables(stray_keys[1]))

    with pytest.raises(bridge.BridgeError, match="not the key this database published"):
        bridge.import_bundle(rest, target_keys[0], copy.deepcopy(bundle), NOW)
    assert rest.writes == []


def test_import_refuses_to_write_into_the_source_stack(source_keys, bundle):
    forged = copy.deepcopy(bundle)
    forged["target_key_fp"] = forged["source_key_fp"]
    rest = _LocalRest(_local_tables(source_keys[1]))

    with pytest.raises(bridge.BridgeError, match="holds the source key"):
        bridge.import_bundle(rest, source_keys[0], forged, NOW)
    assert rest.writes == []


def test_import_refuses_a_value_the_local_key_cannot_open_before_writing(target_keys, stray_keys, bundle):
    tampered = copy.deepcopy(bundle)
    tampered["connections"][1]["refresh_token_sealed"] = crypto.seal("sealed-for-someone-else", stray_keys[1])
    rest = _LocalRest(_local_tables(target_keys[1]))

    with pytest.raises(bridge.BridgeError, match="does not open"):
        bridge.import_bundle(rest, target_keys[0], tampered, NOW)
    assert rest.writes == []


def test_import_refuses_an_unknown_bundle_format(target_keys, bundle):
    other = copy.deepcopy(bundle)
    other["format"] = "amazon_ads_bridge/v0"
    rest = _LocalRest(_local_tables(target_keys[1]))

    with pytest.raises(bridge.BridgeError, match="not an amazon_ads_bridge/v1 bundle"):
        bridge.import_bundle(rest, target_keys[0], other, NOW)
    assert rest.writes == []


def test_import_remaps_account_connection_ids_to_local_ids(target_keys, bundle):
    summary, rest = _import(target_keys, bundle)

    amazon_connections = {row["cuenta_externa_id"]: row for row in rest.tables[CONNECTIONS_TABLE]
                          if row["integration_slug"] == "amazon_ads"}
    new_local_id = amazon_connections["amzn1.account.AAA"]["id"]
    assert summary.connection_ids == {41: new_local_id, 42: 7}
    assert new_local_id not in (7, 8, 41, 42)
    accounts = {row["cuenta_externa_id"]: row for row in rest.tables[ACCOUNTS_TABLE]}
    assert accounts["ENTITY1"]["connection_id"] == new_local_id
    assert accounts["ENTITY2"]["connection_id"] == 7
    assert (accounts["ENTITY3"]["id"], accounts["ENTITY3"]["connection_id"]) == (9, 7)
    assert accounts["ENTITY3"]["cliente"] == "marca-tres"
    connection_payloads = [write[2] for write in rest.writes if write[:2] == ("upsert", CONNECTIONS_TABLE)]
    assert len(connection_payloads) == 2
    assert all("id" not in payload for payload in connection_payloads)


def test_import_tags_connections_as_bridged_and_keeps_them_usable(target_keys, bundle):
    _, rest = _import(target_keys, bundle)

    connection = next(row for row in rest.tables[CONNECTIONS_TABLE] if row["id"] == 7)
    assert connection["metadata"] == {
        "regions": ["NA"],
        "bridge": {"source": "vps", "source_connection_id": 42, "imported_at": NOW.isoformat()},
    }
    assert (connection["estado"], connection["last_error"], connection["cliente"]) == ("activo", "", "demo-dos")
    assert crypto.unseal(connection["refresh_token_sealed"], target_keys[0]) == REFRESH_TOKENS[42]


def test_import_retires_a_different_local_credential_for_the_bridged_one(target_keys, bundle):
    summary, rest = _import(target_keys, bundle)

    credentials = rest.tables[CREDENTIALS_TABLE]
    active = [row for row in credentials if row["estado"] == "activo"]
    retired = next(row for row in credentials if row["id"] == 1)
    assert summary.credential_action == "bridged"
    assert [(row["fingerprint"], row["created_by"]) for row in active] == [("a1b2c3", "bridge")]
    assert crypto.unseal(active[0]["secret_sealed"], target_keys[0]) == CLIENT_SECRET
    assert (retired["estado"], retired["rotated_by"]) == ("invalido", "bridge")


@pytest.mark.parametrize("stored_secret", ["sealed_for_another_key", "missing"])
def test_import_replaces_a_same_fingerprint_credential_the_local_key_cannot_open(
        target_keys, stray_keys, bundle, stored_secret):
    tables = _local_tables(target_keys[1])
    stale = tables[CREDENTIALS_TABLE][0]
    stale["fingerprint"] = bundle["credential"]["fingerprint"]
    if stored_secret == "sealed_for_another_key":
        stale["secret_sealed"] = crypto.seal(CLIENT_SECRET, stray_keys[1])

    summary, rest = _import(target_keys, bundle, tables)

    active = [row for row in rest.tables[CREDENTIALS_TABLE] if row["estado"] == "activo"]
    assert summary.credential_action == "bridged"
    assert len(active) == 1 and active[0]["created_by"] == "bridge"
    assert crypto.unseal(active[0]["secret_sealed"], target_keys[0]) == CLIENT_SECRET
    assert next(row for row in rest.tables[CREDENTIALS_TABLE] if row["id"] == 1)["estado"] == "invalido"


def test_import_keeps_a_same_fingerprint_credential_the_local_key_opens(target_keys, bundle):
    tables = _local_tables(target_keys[1])
    usable = tables[CREDENTIALS_TABLE][0]
    usable["fingerprint"] = bundle["credential"]["fingerprint"]
    usable["secret_sealed"] = crypto.seal(CLIENT_SECRET, target_keys[1])

    summary, rest = _import(target_keys, bundle, tables)

    assert summary.credential_action == "kept"
    assert not [write for write in rest.writes if write[1] == CREDENTIALS_TABLE]


def test_import_is_idempotent(target_keys, bundle):
    first, rest = _import(target_keys, bundle)
    tables_after_first = copy.deepcopy(rest.tables)

    second = bridge.import_bundle(rest, target_keys[0], copy.deepcopy(bundle), NOW)

    assert second.credential_action == "kept"
    assert second.connection_ids == first.connection_ids
    assert rest.tables == tables_after_first
    assert [row["estado"] for row in rest.tables[CREDENTIALS_TABLE]].count("activo") == 1


def test_import_writes_one_audit_row_without_secrets(target_keys, bundle):
    summary, rest = _import(target_keys, bundle)

    assert len(rest.audits) == 1
    audit = rest.audits[0]
    assert (audit["accion"], audit["integration_slug"], audit["actor"]) == ("bridge_import", "amazon_ads", "bridge")
    assert not AUDIT_FORBIDDEN_KEYS & set(audit["detalle"])
    assert audit["detalle"]["connections"] == {str(source): local for source, local in summary.connection_ids.items()}
    detail_text = json.dumps(audit["detalle"])
    assert CLIENT_SECRET not in detail_text
    assert bundle["credential"]["secret_sealed"] not in detail_text


def test_bridge_never_prints_or_logs_secrets(monkeypatch, capsys, caplog, tmp_path, source_keys, target_keys,
                                            forbidden_calls):
    caplog.set_level(logging.DEBUG)
    assert _run_export_command(monkeypatch, source_keys, target_keys)[0] == 0
    exported = capsys.readouterr()
    bundle_path = tmp_path / "bundle.json"
    bundle_path.write_text(exported.out, encoding="utf-8")
    monkeypatch.setattr(worker, "_rest_worker", lambda: _LocalRest(_local_tables(target_keys[1])))
    monkeypatch.setenv(crypto.PRIVATE_KEY_ENV, target_keys[0].replace("\n", "\\n"))
    monkeypatch.setenv(bridge.ALLOW_IMPORT_ENV, "local")

    assert bridge.main(["import", "--bundle", str(bundle_path)]) == 0
    imported = capsys.readouterr()

    written = json.loads(exported.out)
    ciphertexts = [written["credential"]["secret_sealed"]]
    ciphertexts += [connection["refresh_token_sealed"] for connection in written["connections"]]
    everything_but_the_bundle = exported.err + imported.out + imported.err + caplog.text
    for plaintext in (CLIENT_SECRET, *REFRESH_TOKENS.values()):
        assert plaintext not in exported.out + everything_but_the_bundle
    for ciphertext in ciphertexts:
        assert ciphertext not in everything_but_the_bundle
    assert "PRIVATE KEY" not in exported.out + everything_but_the_bundle
    assert len(imported.out.splitlines()) == 1
    assert written["target_key_fp"] in imported.out
    assert forbidden_calls == []


def test_load_bundle_reads_a_utf16_file_from_a_powershell_redirect(tmp_path, bundle):
    bundle_path = tmp_path / "bundle.json"
    bundle_path.write_bytes(json.dumps(bundle).encode("utf-16"))

    assert bridge.load_bundle(bundle_path) == bundle


def test_script_runs_when_piped_on_stdin():
    completed = subprocess.run(
        [sys.executable, "-", "--help"], input=SCRIPT.read_bytes(), cwd=REPO_ROOT, capture_output=True, timeout=120,
    )

    assert completed.returncode == 0, completed.stderr.decode(errors="replace")
    assert b"export" in completed.stdout
    assert b"import" in completed.stdout
