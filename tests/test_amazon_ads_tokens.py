"""TokenManager: per-connection cache, forced refresh, needs_reauth marking. Fake rest, fake LwA refresh, no network."""
from __future__ import annotations

import pytest

from core.amazon_ads.tokens import EXPIRY_MARGIN_SECONDS, ConnectionUnavailable, TokenManager
from core.integrations import crypto, oauth
from core.integrations.store import CONNECTIONS_TABLE, CREDENTIALS_TABLE


@pytest.fixture(scope="module")
def keypair():
    return crypto.generate_keypair()


class _FakeRest:
    def __init__(self, public_pem: str, connections: list[dict]):
        self._public_pem = public_pem
        self._connections = connections
        self.credential: dict | None = None
        self.save_credential("amzn-client", "client-secret-value")
        self.selects = []
        self.updates = []
        self.audits = []

    def save_credential(self, client_id: str, client_secret: str) -> None:
        self.credential = {"public_fields": {"client_id": client_id},
                           "secret_sealed": crypto.seal(client_secret, self._public_pem)}

    def select(self, table, params):
        self.selects.append((table, params))
        if table == CREDENTIALS_TABLE:
            return [dict(self.credential)] if self.credential else []
        if table == CONNECTIONS_TABLE:
            wanted = params["id"].removeprefix("eq.")
            return [dict(row) for row in self._connections if str(row["id"]) == wanted]
        raise AssertionError(f"unexpected table {table}")

    def update(self, table, params, changes, stamp=True):
        self.updates.append((table, params, changes))

    def audit(self, action, *, slug=None, actor="", detail=None):
        self.audits.append((action, slug, detail))


class _FakeRefresh:
    def __init__(self, expires_in: int = 3600, error: Exception | None = None):
        self.expires_in = expires_in
        self.error = error
        self.calls = []

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return oauth.TokenSet(
            access_token=f"access-{len(self.calls)}",
            refresh_token=kwargs["refresh_token"],
            expires_in=self.expires_in,
            scopes=(),
            user_id="",
        )


class _Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def _connection(public_pem: str, connection_id: int = 7, estado: str = "activo") -> dict:
    return {
        "id": connection_id,
        "integration_slug": "amazon_ads",
        "cliente": "cliente-demo",
        "estado": estado,
        "refresh_token_sealed": crypto.seal(f"refresh-{connection_id}", public_pem),
    }


def _manager(keypair, connections, monkeypatch, refresh=None):
    private_pem, public_pem = keypair
    rest = _FakeRest(public_pem, connections)
    refresh = refresh or _FakeRefresh()
    monkeypatch.setattr(oauth, "refresh", refresh)
    clock = _Clock()
    return TokenManager(rest, private_pem, clock=clock), rest, refresh, clock


def test_refresh_uses_opened_secrets_without_rotation(keypair, monkeypatch):
    manager, _, refresh, _ = _manager(keypair, [_connection(keypair[1])], monkeypatch)

    assert manager.access_token(7) == "access-1"

    call = refresh.calls[0]
    assert call["token_url"] == "https://api.amazon.com/auth/o2/token"
    assert call["client_id"] == "amzn-client"
    assert call["client_secret"] == "client-secret-value"
    assert call["refresh_token"] == "refresh-7"
    assert call["rotates"] is False


def test_token_is_cached_until_expiry_margin(keypair, monkeypatch):
    manager, _, refresh, clock = _manager(keypair, [_connection(keypair[1])], monkeypatch)

    manager.access_token(7)
    clock.now += 3600 - EXPIRY_MARGIN_SECONDS - 1
    assert manager.access_token(7) == "access-1"
    assert len(refresh.calls) == 1

    clock.now += 1
    assert manager.access_token(7) == "access-2"
    assert len(refresh.calls) == 2


def test_force_refresh_bypasses_the_cache(keypair, monkeypatch):
    manager, _, refresh, _ = _manager(keypair, [_connection(keypair[1])], monkeypatch)

    manager.access_token(7)
    assert manager.access_token(7, force_refresh=True) == "access-2"
    assert len(refresh.calls) == 2


def test_token_source_passes_the_force_flag(keypair, monkeypatch):
    manager, _, refresh, _ = _manager(keypair, [_connection(keypair[1])], monkeypatch)
    source = manager.token_source(7)

    assert source(False) == "access-1"
    assert source(False) == "access-1"
    assert source(True) == "access-2"
    assert len(refresh.calls) == 2


def test_each_connection_has_its_own_cached_token(keypair, monkeypatch):
    connections = [_connection(keypair[1], 7), _connection(keypair[1], 8)]
    manager, _, refresh, _ = _manager(keypair, connections, monkeypatch)

    manager.access_token(7)
    manager.access_token(8)
    manager.access_token(7)

    assert [call["refresh_token"] for call in refresh.calls] == ["refresh-7", "refresh-8"]


def test_client_credential_is_read_on_every_real_refresh_but_not_for_a_cached_token(keypair, monkeypatch):
    connections = [_connection(keypair[1], 7), _connection(keypair[1], 8)]
    manager, rest, _, _ = _manager(keypair, connections, monkeypatch)

    manager.access_token(7)
    manager.access_token(7)
    manager.access_token(8, force_refresh=True)

    assert manager.client_id() == "amzn-client"
    assert [table for table, _ in rest.selects].count(CREDENTIALS_TABLE) == 2


def test_a_rotated_client_secret_is_used_by_the_next_refresh_without_a_restart(keypair, monkeypatch):
    manager, rest, refresh, clock = _manager(keypair, [_connection(keypair[1])], monkeypatch)
    manager.access_token(7)

    rest.save_credential("amzn-client", "rotated-secret-value")
    clock.now += 3600
    manager.access_token(7)

    assert [call["client_secret"] for call in refresh.calls] == ["client-secret-value", "rotated-secret-value"]


def test_client_id_follows_the_credential_of_the_latest_refresh(keypair, monkeypatch):
    manager, rest, _, clock = _manager(keypair, [_connection(keypair[1])], monkeypatch)
    manager.access_token(7)

    rest.save_credential("amzn-client-2", "client-secret-value")
    assert manager.client_id() == "amzn-client"
    clock.now += 3600
    manager.access_token(7)

    assert manager.client_id() == "amzn-client-2"


def test_a_removed_credential_makes_the_connection_unavailable_and_drops_its_token(keypair, monkeypatch):
    manager, rest, refresh, _ = _manager(keypair, [_connection(keypair[1])], monkeypatch)
    manager.access_token(7)
    saved_credential = rest.credential

    rest.credential = None
    with pytest.raises(ConnectionUnavailable, match="no active system credential"):
        manager.access_token(7, force_refresh=True)

    rest.credential = saved_credential
    assert manager.access_token(7) == "access-2"
    assert len(refresh.calls) == 2


def test_forget_drops_a_cached_token(keypair, monkeypatch):
    manager, _, refresh, _ = _manager(keypair, [_connection(keypair[1])], monkeypatch)
    manager.access_token(7)

    manager.forget(7)
    manager.forget(99)

    assert manager.access_token(7) == "access-2"
    assert len(refresh.calls) == 2


def test_dead_refresh_token_marks_connection_needs_reauth_and_reraises(keypair, monkeypatch):
    refresh = _FakeRefresh(error=oauth.NeedsReauth("invalid_grant: token revoked"))
    manager, rest, _, _ = _manager(keypair, [_connection(keypair[1])], monkeypatch, refresh=refresh)

    with pytest.raises(oauth.NeedsReauth):
        manager.access_token(7)

    assert rest.updates == [
        (CONNECTIONS_TABLE, {"id": "eq.7"}, {"estado": "needs_reauth", "last_error": "invalid_grant: token revoked"})
    ]
    assert rest.audits == [("token_refresh_failed", "amazon_ads", {"cliente": "cliente-demo"})]


def test_needs_reauth_drops_the_cached_token(keypair, monkeypatch):
    refresh = _FakeRefresh()
    manager, _, _, _ = _manager(keypair, [_connection(keypair[1])], monkeypatch, refresh=refresh)
    manager.access_token(7)

    refresh.error = oauth.NeedsReauth("revoked")
    with pytest.raises(oauth.NeedsReauth):
        manager.access_token(7, force_refresh=True)

    refresh.error = None
    assert manager.access_token(7) == "access-3"


def test_missing_connection_is_unavailable(keypair, monkeypatch):
    manager, rest, refresh, _ = _manager(keypair, [], monkeypatch)

    with pytest.raises(ConnectionUnavailable):
        manager.access_token(99)

    assert refresh.calls == []
    assert rest.updates == []


def test_inactive_connection_is_unavailable(keypair, monkeypatch):
    manager, rest, refresh, _ = _manager(keypair, [_connection(keypair[1], estado="needs_reauth")], monkeypatch)

    with pytest.raises(ConnectionUnavailable):
        manager.access_token(7)

    assert refresh.calls == []
    assert rest.updates == []


def test_read_existing_private_key_prefers_the_env_var(monkeypatch, tmp_path):
    key_file = tmp_path / "sealing_private.pem"
    key_file.write_text("FILE-KEY", encoding="ascii")
    monkeypatch.setenv(crypto.PRIVATE_KEY_FILE_ENV, str(key_file))
    monkeypatch.setenv(crypto.PRIVATE_KEY_ENV, "LINE-1\\nLINE-2")

    assert crypto.read_existing_private_key() == "LINE-1\nLINE-2"


def test_read_existing_private_key_falls_back_to_the_key_file(monkeypatch, tmp_path):
    key_file = tmp_path / "sealing_private.pem"
    key_file.write_text("FILE-KEY", encoding="ascii")
    monkeypatch.setenv(crypto.PRIVATE_KEY_FILE_ENV, str(key_file))
    monkeypatch.delenv(crypto.PRIVATE_KEY_ENV, raising=False)

    assert crypto.read_existing_private_key() == "FILE-KEY"


def test_read_existing_private_key_never_creates_a_key(monkeypatch, tmp_path):
    key_file = tmp_path / "keys" / "sealing_private.pem"
    monkeypatch.setenv(crypto.PRIVATE_KEY_FILE_ENV, str(key_file))
    monkeypatch.delenv(crypto.PRIVATE_KEY_ENV, raising=False)

    with pytest.raises(crypto.SealError):
        crypto.read_existing_private_key()

    assert not key_file.exists()
    assert not key_file.parent.exists()


def test_connection_is_filtered_by_amazon_slug(keypair, monkeypatch):
    manager, rest, _, _ = _manager(keypair, [_connection(keypair[1])], monkeypatch)

    manager.access_token(7)

    connection_params = [params for table, params in rest.selects if table == CONNECTIONS_TABLE][0]
    assert connection_params["integration_slug"] == "eq.amazon_ads"
    assert connection_params["id"] == "eq.7"
