"""Asymmetric sealing for system credentials.

The Agency OS app seals a secret with a public key and can never open it again:
only the worker holds the private key. This is stronger than the symmetric scheme
on `feat/ads-api-str-ingestion`, where whoever could encrypt could also decrypt —
there, the app simply never wrote secrets at all.

Ciphertext is `v1:<base64 RSA-OAEP-SHA256>`. The version prefix exists so a key
rotation can leave both generations readable instead of requiring one atomic
sweep of every row.
"""
from __future__ import annotations

import base64
import logging
import os
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

SEAL_VERSION = "v1"
KEY_SIZE_BITS = 4096

PUBLIC_KEY_ENV = "INTEGRATIONS_PUBLIC_KEY"
PRIVATE_KEY_ENV = "INTEGRATIONS_PRIVATE_KEY"
PRIVATE_KEY_FILE_ENV = "INTEGRATIONS_KEY_FILE"
# Lives in a volume only the worker mounts; the app container never sees it.
DEFAULT_PRIVATE_KEY_FILE = "/app/data/integrations/sealing_private.pem"

log = logging.getLogger(__name__)

_OAEP = padding.OAEP(
    mgf=padding.MGF1(algorithm=hashes.SHA256()),
    algorithm=hashes.SHA256(),
    label=None,
)


class SealError(RuntimeError):
    """Sealing or unsealing failed."""


def generate_keypair() -> tuple[str, str]:
    """A fresh (private_pem, public_pem) pair for `worker.py keys`."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=KEY_SIZE_BITS)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("ascii")
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("ascii")
    return private_pem, public_pem


def seal(plaintext: str, public_pem: str) -> str:
    if not plaintext:
        raise SealError("nothing to seal")
    try:
        public_key = serialization.load_pem_public_key(public_pem.encode("ascii"))
        sealed = public_key.encrypt(plaintext.encode("utf-8"), _OAEP)
    except SealError:
        raise
    except Exception as exc:
        raise SealError(f"could not seal the secret: {exc}") from exc
    return f"{SEAL_VERSION}:{base64.b64encode(sealed).decode('ascii')}"


def unseal(ciphertext: str, private_pem: str) -> str:
    version, _, payload = ciphertext.partition(":")
    if version != SEAL_VERSION or not payload:
        raise SealError(f"unknown ciphertext version: {version!r}")
    try:
        private_key = serialization.load_pem_private_key(
            private_pem.encode("ascii"), password=None
        )
        opened = private_key.decrypt(base64.b64decode(payload), _OAEP)
    except Exception as exc:
        raise SealError(f"could not open the secret: {exc}") from exc
    return opened.decode("utf-8")


def public_key_from_env() -> str | None:
    """The sealing key. Safe to ship in the app's environment: it only seals."""
    key = os.environ.get(PUBLIC_KEY_ENV, "").strip()
    return key.replace("\\n", "\n") if key else None


def private_key_from_env() -> str:
    """The opening key. Worker-only — the app container must never carry it."""
    key = os.environ.get(PRIVATE_KEY_ENV, "").strip()
    if not key:
        raise SealError(f"{PRIVATE_KEY_ENV} is not set — this is worker-only code")
    return key.replace("\\n", "\n")


def private_key_path() -> Path:
    return Path(os.environ.get(PRIVATE_KEY_FILE_ENV, DEFAULT_PRIVATE_KEY_FILE))


def load_or_create_private_key() -> tuple[str, str, bool]:
    """The worker's own keypair, generated on first run. → (private, public, created).

    Nobody types or pastes this: asking a person to carry a key between a browser
    and a server is the chore the portal exists to remove. The env var still wins
    when it is set, for deployments that inject secrets from outside.
    """
    from_env = os.environ.get(PRIVATE_KEY_ENV, "").strip()
    if from_env:
        private_pem = from_env.replace("\\n", "\n")
        return private_pem, public_from_private(private_pem), False

    target = private_key_path()
    if target.is_file():
        private_pem = target.read_text(encoding="ascii")
        return private_pem, public_from_private(private_pem), False

    private_pem, public_pem = generate_keypair()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(private_pem, encoding="ascii")
    try:
        target.chmod(0o600)
    except OSError:
        log.warning("could not tighten permissions on %s", target)
    return private_pem, public_pem, True


def public_from_private(private_pem: str) -> str:
    try:
        private_key = serialization.load_pem_private_key(private_pem.encode("ascii"), password=None)
    except Exception as exc:
        raise SealError(f"could not read the private key: {exc}") from exc
    return private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("ascii")
