"""Role resolution for the integrations portal.

Two sources, in order:
  1. the `role` key of the user in `secrets.toml`;
  2. the `AGENCY_OS_LOCAL_ADMIN` env var, dev-only.

`AGENCY_OS_LOCAL_MODE` (which turns login off entirely) does NOT grant admin
on purpose: treating that flag as admin would leave the portal wide open to
anyone that starts the app with the flag set.
"""
from __future__ import annotations

import os

ADMIN = "admin"
USER = "usuario"


def _declared_role(username: str) -> str | None:
    if not username:
        return None
    try:
        # Deferred import: core/ must load without Streamlit present.
        import streamlit as st

        users = st.secrets["credentials"]["usernames"]
        entry = users.get(username.lower().strip())
    except Exception:
        return None
    if not isinstance(entry, dict):
        try:
            entry = dict(entry)
        except Exception:
            return None
    role = str(entry.get("role", "")).strip().lower()
    return role if role in (ADMIN, USER) else None


def resolve_role(username: str) -> str:
    """Effective role. Falls back to `usuario` on any doubt."""
    declared = _declared_role(username)
    if declared:
        return declared
    if os.environ.get("AGENCY_OS_LOCAL_ADMIN") == "1":
        return ADMIN
    return USER


def is_admin(role: str) -> bool:
    return role == ADMIN
