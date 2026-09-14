"""Asymmetric sealing for system credentials.

The Agency OS app seals a secret with a public key and can never open it again:
only the worker holds the private key. This is stronger than the symmetric scheme
on `feat/ads-api-str-ingestion`, where whoever could encrypt could also decrypt —
there, the app simply never wrote secrets at all.

Two ciphertext generations coexist, told apart by their prefix:

  v1:<base64 RSA-OAEP-SHA256>              raw RSA over the plaintext. Capped at
                                           446 bytes for a 4096-bit key, which
                                           fits a Mercado Libre token (40 chars)
                                           and not a Login with Amazon one
                                           (up to 2048 bytes).
  v2:<base64 wrapped key>.<base64 payload>  hybrid: a random AES-256-GCM data key
                                           encrypts the plaintext, RSA-OAEP wraps
                                           the data key. No size ceiling.

`seal` always writes v2; `unseal` opens both, so rows sealed before the change
keep working without a sweep — the version prefix existed for exactly this.
"""
from __future__ import annotations

import base64
import logging
import os
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

SEAL_VERSION = "v2"
LEGACY_SEAL_VERSION = "v1"
KEY_SIZE_BITS = 4096
_DATA_KEY_BITS = 256
_GCM_NONCE_BYTES = 12

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
        data_key = AESGCM.generate_key(bit_length=_DATA_KEY_BITS)
        nonce = os.urandom(_GCM_NONCE_BYTES)
        payload = nonce + AESGCM(data_key).encrypt(nonce, plaintext.encode("utf-8"), None)
        wrapped_key = public_key.encrypt(data_key, _OAEP)
    except SealError:
        raise
    except Exception as exc:
        raise SealError(f"could not seal the secret: {exc}") from exc
    return f"{SEAL_VERSION}:{_b64(wrapped_key)}.{_b64(payload)}"


def unseal(ciphertext: str, private_pem: str) -> str:
    version, _, payload = ciphertext.partition(":")
    if not payload or version not in (SEAL_VERSION, LEGACY_SEAL_VERSION):
        raise SealError(f"unknown ciphertext version: {version!r}")
    try:
        private_key = serialization.load_pem_private_key(
            private_pem.encode("ascii"), password=None
        )
        if version == LEGACY_SEAL_VERSION:
            opened = private_key.decrypt(base64.b64decode(payload), _OAEP)
        else:
            opened = _open_envelope(payload, private_key)
    except Exception as exc:
        raise SealError(f"could not open the secret: {exc}") from exc
    return opened.decode("utf-8")


def _open_envelope(payload: str, private_key) -> bytes:
    wrapped_key_b64, _, body_b64 = payload.partition(".")
    if not body_b64:
        raise ValueError("envelope without payload")
    data_key = private_key.decrypt(base64.b64decode(wrapped_key_b64), _OAEP)
    body = base64.b64decode(body_b64)
    nonce, encrypted = body[:_GCM_NONCE_BYTES], body[_GCM_NONCE_BYTES:]
    return AESGCM(data_key).decrypt(nonce, encrypted, None)


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


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
