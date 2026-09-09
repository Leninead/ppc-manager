"""Meli API package: transport (Fase B) + ingest & worker (Fase C).

* ``transport`` — resilient HTTP client (``MeliClient``).
* ``ingest``    — hydrate identities, snapshot items, aggregate visits & orders.
* ``worker``    — command-line entry that wires OAuth → transport → ingest.

Higher-level code (``modules/mercado_libre``) is intentionally kept out of
this package: parsing Excel exports and rendering UIs is the responsibility
of Fase D.
"""

from .transport import (
    AuthExpired,
    MeliClient,
    MeliClientError,
    NotFound,
    RateLimited,
    ServerError,
)

__all__ = [
    "AuthExpired",
    "MeliClient",
    "MeliClientError",
    "NotFound",
    "RateLimited",
    "ServerError",
]
