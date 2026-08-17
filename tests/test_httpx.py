
import pytest
import httpx
from datetime import datetime, timedelta, timezone

# Import shared test utilities
from .test_utils import httpx_client_patcher

from folioclient._httpx import FolioConnectionParameters, FolioAuth

# Dummy classes remain the same for backward compatibility


class DummyCookies(dict):
    def get(self, key, default=None):
        return super().get(key, default)


class DummyResponse:
    def __init__(self, cookies=None, json_data=None, status_code=200):
        self._cookies = DummyCookies(cookies or {})
        self._json = json_data or {}
        self.status_code = status_code

    @property
    def cookies(self):
        return self._cookies

    def json(self):
        return self._json

    def read(self):
        return b""

    async def aread(self):
        return b""

    def raise_for_status(self):
        if not (200 <= self.status_code < 300):
            raise httpx.HTTPStatusError("status", request=None, response=self)


class DummyClient:
    def __init__(self, response=None, *args, **kwargs):
        self._response = response

    def post(self, *args, **kwargs):
        return self._response

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class DummyAsyncClient(DummyClient):
    def __init__(self, response=None, *args, **kwargs):
        super().__init__(response)

    async def post(self, *args, **kwargs):
        return self._response

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    # Mimic async generator for async_auth_flow
    async def async_auth_flow(self, req):
        yield req


def make_params():
    return FolioConnectionParameters(
        gateway_url="https//folio",
        tenant_id="alpha",
        username="u",
        password="p",
        ssl_verify=False,
        timeout=httpx.Timeout(5.0),
    )


def test_do_sync_auth_and_token_properties(monkeypatch):
    params = make_params()
    now = datetime.now(tz=timezone.utc)
    expires = (now + timedelta(minutes=5)).isoformat()
    cookies = {"folioAccessToken": "token123", "folioRefreshToken": "rtoken"}
    resp = DummyResponse(cookies=cookies, json_data={"accessTokenExpiration": expires})

    class PatchedDummyClient(DummyClient):
        def post(self, url, *args, **kwargs):
            if "/authn/login-with-expiry" in url:
                return resp
            return DummyResponse(status_code=404)

    def dummy_client_factory(*args, **kwargs):
        return PatchedDummyClient()

    with httpx_client_patcher(dummy_client_factory):
        fa = FolioAuth(params)
        assert fa.folio_auth_token == "token123"
        assert fa.folio_refresh_token == "rtoken"


@pytest.mark.asyncio
async def test_do_async_auth_and_cookie_header(monkeypatch):
    params = make_params()
    now = datetime.now(tz=timezone.utc)
    expires = (now + timedelta(minutes=5)).isoformat()
    cookies = {"folioAccessToken": "async-token", "folioRefreshToken": "async-rtoken"}
    resp = DummyResponse(cookies=cookies, json_data={"accessTokenExpiration": expires})

    class PatchedDummyClient(DummyClient):
        def post(self, url, *args, **kwargs):
            if "/authn/login-with-expiry" in url:
                return resp
            return DummyResponse(status_code=404)

    class PatchedDummyAsyncClient(DummyAsyncClient):
        async def post(self, url, *args, **kwargs):
            if "/authn/login-with-expiry" in url:
                return resp
            return DummyResponse(status_code=404)

    def dummy_client_factory(*args, **kwargs):
        return PatchedDummyClient()
    def dummy_async_client_factory(*args, **kwargs):
        return PatchedDummyAsyncClient()

    with httpx_client_patcher(dummy_client_factory, dummy_async_client_factory):
        fa = FolioAuth(params)
        req = httpx.Request("GET", "https//folio/test")
        req.headers["Cookie"] = "other=1; folioAccessToken=old"
        fa._set_auth_cookies_on_request(req)
        assert "async-token" in req.headers["Cookie"]
        assert "other=1" in req.headers["Cookie"]


def test_token_is_expiring_and_reset_tenant(monkeypatch):
    params = make_params()
    # Create a FolioAuth with a token that's already expired
    cookies = {"folioAccessToken": "t", "folioRefreshToken": "r"}
    resp = DummyResponse(cookies=cookies, json_data={})



    class PatchedDummyClient(DummyClient):
        def post(self, url, *args, **kwargs):
            if "/authn/login-with-expiry" in url:
                return resp
            return DummyResponse(status_code=404)

    def dummy_client_factory(*args, **kwargs):
        return PatchedDummyClient()

    with httpx_client_patcher(dummy_client_factory):
        fa = FolioAuth(params)
        fa._token = FolioAuth._Token(auth_token="x", refresh_token=None, expires_at=datetime.now(tz=timezone.utc)-timedelta(minutes=1), refresh_token_expires_at=None, cookies=None)
        assert fa._token_is_expiring()
        fa.tenant_id = "other"
        fa.reset_tenant_id()
        assert fa.tenant_id == "alpha"


def test_sync_auth_flow_refresh_success(monkeypatch):
    params = make_params()
    # auth response for _do_sync_auth
    auth_cookies = {"folioAccessToken": "auth-t", "folioRefreshToken": "auth-r"}
    auth_resp = DummyResponse(cookies=auth_cookies, json_data={})



    class PatchedDummyClient(DummyClient):
        def post(self, url, *args, **kwargs):
            if "/authn/login-with-expiry" in url:
                return auth_resp
            return DummyResponse(status_code=404)

    def dummy_client_factory(*args, **kwargs):
        return PatchedDummyClient()

    with httpx_client_patcher(dummy_client_factory):
        fa = FolioAuth(params)
        req = httpx.Request("GET", "https//folio/resource")
        gen = fa.sync_auth_flow(req)
        yielded = next(gen)
        assert yielded is req
        yielded_after = gen.send(DummyResponse(status_code=401))
        assert yielded_after is req
        with pytest.raises(StopIteration):
            gen.send(DummyResponse(status_code=200))


def test_sync_auth_flow_refresh_still_unauthorized(monkeypatch):
    params = make_params()
    auth_cookies = {"folioAccessToken": "auth-t", "folioRefreshToken": "auth-r"}
    auth_resp = DummyResponse(cookies=auth_cookies, json_data={})



    class PatchedDummyClient(DummyClient):
        def post(self, url, *args, **kwargs):
            if "/authn/login-with-expiry" in url:
                return auth_resp
            return DummyResponse(status_code=404)

    def dummy_client_factory(*args, **kwargs):
        return PatchedDummyClient()

    with httpx_client_patcher(dummy_client_factory):
        fa = FolioAuth(params)
        req = httpx.Request("GET", "https//folio/resource")
        gen = fa.sync_auth_flow(req)
        next(gen)
        gen.send(DummyResponse(status_code=401))
        with pytest.raises(httpx.HTTPStatusError):
            gen.send(DummyResponse(status_code=401))


@pytest.mark.asyncio
async def test_async_auth_flow_refresh_success(monkeypatch):
    params = make_params()
    auth_cookies = {"folioAccessToken": "aasync", "folioRefreshToken": "raasync"}
    auth_resp = DummyResponse(cookies=auth_cookies, json_data={})



    class PatchedDummyClient(DummyClient):
        def post(self, url, *args, **kwargs):
            if "/authn/login-with-expiry" in url:
                return auth_resp
            return DummyResponse(status_code=404)

    class PatchedDummyAsyncClient(DummyAsyncClient):
        async def post(self, url, *args, **kwargs):
            if "/authn/login-with-expiry" in url:
                return auth_resp
            return DummyResponse(status_code=404)

    def dummy_client_factory(*args, **kwargs):
        return PatchedDummyClient()
    def dummy_async_client_factory(*args, **kwargs):
        return PatchedDummyAsyncClient()

    with httpx_client_patcher(dummy_client_factory, dummy_async_client_factory):
        fa = FolioAuth(params)
        req = httpx.Request("GET", "https//folio/async")
        agen = fa.async_auth_flow(req)
        first = await agen.__anext__()
        assert first is req
        second = await agen.asend(DummyResponse(status_code=401))
        assert second is req
        with pytest.raises(StopAsyncIteration):
            await agen.asend(DummyResponse(status_code=200))


def test_set_auth_cookies_clears_only_folio_cookies(monkeypatch):
    params = make_params()
    # give an initial token so FolioAuth can construct successfully
    auth_resp = DummyResponse(cookies={"folioAccessToken": "init", "folioRefreshToken": "init-r"}, json_data={})

    def fake_client(*args, **kwargs):
        return DummyClient(auth_resp)

    with httpx_client_patcher(fake_client):
        fa = FolioAuth(params)
        fa._token = None
        req = httpx.Request("GET", "https//folio/some")
        req.headers["Cookie"] = "folioAccessToken=old"
        fa._set_auth_cookies_on_request(req)
        assert "Cookie" not in req.headers


def test_do_sync_auth_raises_when_no_token(monkeypatch):
    params = make_params()
    # auth response lacks folioAccessToken
    resp = DummyResponse(cookies={}, json_data={})

    def fake_client(*args, **kwargs):
        return DummyClient(resp)

    with httpx_client_patcher(fake_client):
        with pytest.raises(ValueError):
            FolioAuth(params)


def test_tenant_header_preserved_and_refresh_token_expiry(monkeypatch):
    params = make_params()
    # include refreshTokenExpiration as isoformat
    now = datetime.now(tz=timezone.utc)
    refresh_exp = (now + timedelta(hours=1)).isoformat()
    cookies = {"folioAccessToken": "t1", "folioRefreshToken": "rt1"}
    resp = DummyResponse(cookies=cookies, json_data={"refreshTokenExpiration": refresh_exp})

    def fake_client(*args, **kwargs):
        return DummyClient(resp)

    with httpx_client_patcher(fake_client):
        fa = FolioAuth(params)
        req = httpx.Request("GET", "https//folio/x")
        req.headers["x-okapi-tenant"] = "custom"
        gen = fa.sync_auth_flow(req)
        first = next(gen)
        assert first is req
        assert req.headers["x-okapi-tenant"] == "custom"


def test_folio_auth_token_refreshes_when_expired(monkeypatch):
    params = make_params()
    # initial client returns a token that expires immediately
    cookies = {"folioAccessToken": "old", "folioRefreshToken": "r-old"}
    now = datetime.now(tz=timezone.utc)
    resp = DummyResponse(cookies=cookies, json_data={"accessTokenExpiration": (now - timedelta(seconds=10)).isoformat()})

    def fake_client(*args, **kwargs):
        return DummyClient(resp)

    with httpx_client_patcher(fake_client):
        fa = FolioAuth(params)
        fa._token = FolioAuth._Token(auth_token="expired", refresh_token=None, expires_at=now - timedelta(seconds=10), refresh_token_expires_at=None, cookies=None)
        assert fa.folio_auth_token == "old"


def test_sync_401_skips_reauth_when_token_replaced_concurrently(monkeypatch):
    """A 401 must NOT re-authenticate if another caller already replaced our token.

    De-duplication is by token identity, so retrying with the newer token is enough.
    """
    params = make_params()
    now = datetime.now(tz=timezone.utc)
    resp = DummyResponse(cookies={"folioAccessToken": "init", "folioRefreshToken": "init-r"}, json_data={"accessTokenExpiration": (now + timedelta(hours=1)).isoformat()})

    def fake_client(*args, **kwargs):
        return DummyClient(resp)

    with httpx_client_patcher(fake_client):
        fa = FolioAuth(params)
        req = httpx.Request("GET", "https//folio/resource")
        gen = fa.sync_auth_flow(req)
        next(gen)
        # Simulate another thread refreshing while our request was in flight
        fa._token = make_token("newer")
        fa._do_sync_auth = lambda: (_ for _ in ()).throw(RuntimeError("should not refresh"))
        yielded = gen.send(DummyResponse(status_code=401))
        assert yielded is req
        with pytest.raises(StopIteration):
            gen.send(DummyResponse(status_code=200))


def test_sync_401_reauths_even_when_token_looks_valid(monkeypatch):
    """A 401 is authoritative: refresh even when the token is nowhere near expiry.

    Covers revocation, Keycloak key rotation and clock skew, where the local expiry
    check cannot tell that the server has stopped accepting the token.
    """
    params = make_params()
    now = datetime.now(tz=timezone.utc)
    resp = DummyResponse(cookies={"folioAccessToken": "init", "folioRefreshToken": "init-r"}, json_data={"accessTokenExpiration": (now + timedelta(hours=1)).isoformat()})

    def fake_client(*args, **kwargs):
        return DummyClient(resp)

    with httpx_client_patcher(fake_client):
        fa = FolioAuth(params)
        assert fa._token_is_expiring() is False  # looks perfectly good locally
        calls = []

        def refreshed():
            calls.append(1)
            return make_token("refreshed")

        fa._do_sync_auth = refreshed
        req = httpx.Request("GET", "https//folio/resource")
        gen = fa.sync_auth_flow(req)
        next(gen)
        yielded = gen.send(DummyResponse(status_code=401))
        assert yielded is req
        assert calls == [1], "expected exactly one re-authentication"
        assert fa._token.auth_token == "refreshed"
        with pytest.raises(StopIteration):
            gen.send(DummyResponse(status_code=200))


def test_sync_401_retry_carries_the_new_token_cookies(monkeypatch):
    """The retry must actually be sent with the refreshed cookies, not the stale ones."""
    params = make_params()
    # Future expiry, so the proactive check does not refresh before the first request.
    resp = DummyResponse(
        cookies={"folioAccessToken": "stale", "folioRefreshToken": "stale-r"},
        json_data={
            "accessTokenExpiration": (
                datetime.now(tz=timezone.utc) + timedelta(hours=1)
            ).isoformat()
        },
    )

    with httpx_client_patcher(lambda *a, **k: DummyClient(resp)):
        fa = FolioAuth(params)
        fresh = httpx.Cookies()
        fresh.set("folioAccessToken", "fresh-token")
        fa._do_sync_auth = lambda: FolioAuth._Token(
            auth_token="fresh-token",
            refresh_token="fresh-r",
            expires_at=datetime.now(tz=timezone.utc) + timedelta(hours=1),
            refresh_token_expires_at=None,
            cookies=fresh,
        )
        req = httpx.Request("GET", "https//folio/resource")
        gen = fa.sync_auth_flow(req)
        next(gen)
        assert "stale" in req.headers["Cookie"]
        gen.send(DummyResponse(status_code=401))
        assert "fresh-token" in req.headers["Cookie"]
        assert "stale" not in req.headers["Cookie"]


@pytest.mark.asyncio
async def test_async_401_skips_reauth_when_token_replaced_concurrently(monkeypatch):
    """Async: a 401 must NOT re-authenticate if the token was already replaced."""
    params = make_params()
    now = datetime.now(tz=timezone.utc)
    resp = DummyResponse(cookies={"folioAccessToken": "i2", "folioRefreshToken": "r2"}, json_data={"accessTokenExpiration": (now + timedelta(hours=1)).isoformat()})

    def fake_client(*args, **kwargs):
        return DummyClient(resp)
    def fake_async_client(*args, **kwargs):
        return DummyAsyncClient(resp)

    with httpx_client_patcher(fake_client, fake_async_client):
        fa = FolioAuth(params)
        req = httpx.Request("GET", "https//folio/asyncpass")
        agen = fa.async_auth_flow(req)
        first = await agen.__anext__()
        assert first is req
        fa._token = make_token("newer")

        async def should_not_call():
            raise RuntimeError("should not be called")

        fa._do_async_auth = should_not_call
        second = await agen.asend(DummyResponse(status_code=401))
        assert second is req
        with pytest.raises(StopAsyncIteration):
            await agen.asend(DummyResponse(status_code=200))


@pytest.mark.asyncio
async def test_async_401_reauths_even_when_token_looks_valid(monkeypatch):
    """Async: a 401 re-authenticates even when the token is nowhere near expiry."""
    params = make_params()
    now = datetime.now(tz=timezone.utc)
    resp = DummyResponse(cookies={"folioAccessToken": "i2", "folioRefreshToken": "r2"}, json_data={"accessTokenExpiration": (now + timedelta(hours=1)).isoformat()})

    def fake_client(*args, **kwargs):
        return DummyClient(resp)
    def fake_async_client(*args, **kwargs):
        return DummyAsyncClient(resp)

    with httpx_client_patcher(fake_client, fake_async_client):
        fa = FolioAuth(params)
        assert fa._token_is_expiring() is False
        calls = []

        async def refreshed():
            calls.append(1)
            return make_token("refreshed")

        fa._do_async_auth = refreshed
        req = httpx.Request("GET", "https//folio/asyncpass")
        agen = fa.async_auth_flow(req)
        await agen.__anext__()
        second = await agen.asend(DummyResponse(status_code=401))
        assert second is req
        assert calls == [1], "expected exactly one re-authentication"
        with pytest.raises(StopAsyncIteration):
            await agen.asend(DummyResponse(status_code=200))


def test_concurrent_threads_401_trigger_one_reauth(monkeypatch):
    """N sync threads all seeing a 401 on the same token must produce one login.

    The first thread to take the lock refreshes; the rest see a different token
    identity and retry with it instead of logging in again.
    """
    import threading
    import time

    params = make_params()
    resp = DummyResponse(cookies={"folioAccessToken": "shared", "folioRefreshToken": "r"})

    with httpx_client_patcher(lambda *a, **k: DummyClient(resp)):
        fa = FolioAuth(params)
        calls = []
        calls_guard = threading.Lock()

        def slow_login():
            with calls_guard:
                calls.append(1)
            time.sleep(0.05)  # the network round trip
            return make_token(f"tok{len(calls)}")

        started = threading.Barrier(8)

        def one_request():
            gen = fa.sync_auth_flow(httpx.Request("GET", "https//folio/x"))
            next(gen)
            started.wait()  # all threads hold the same token before any sees a 401
            fa._do_sync_auth = slow_login
            try:
                gen.send(DummyResponse(status_code=401))
                gen.send(DummyResponse(status_code=200))
            except StopIteration:
                pass

        threads = [threading.Thread(target=one_request) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(calls) == 1, f"expected 1 login for 8 threads on one token, got {len(calls)}"


@pytest.mark.asyncio
async def test_do_async_auth_raises_and_parses_expirations(monkeypatch):
    params = make_params()
    # make __init__ succeed
    init_resp = DummyResponse(cookies={"folioAccessToken": "ok", "folioRefreshToken": "rok"}, json_data={})
    with httpx_client_patcher(lambda *a, **k: DummyClient(init_resp)):
        fa = FolioAuth(params)
        def fake_async_client_no_token(*args, **kwargs):
            return DummyAsyncClient(DummyResponse(cookies={}, json_data={}))
        with httpx_client_patcher(lambda *a, **k: DummyClient(init_resp), fake_async_client_no_token):
            with pytest.raises(ValueError):
                await fa._do_async_auth()
        now = datetime.now(tz=timezone.utc)
        ad = (now + timedelta(minutes=10)).isoformat()
        rd = (now + timedelta(hours=1)).isoformat()
        def fake_async_client_with_exp(*args, **kwargs):
            return DummyAsyncClient(DummyResponse(cookies={"folioAccessToken": "tok"}, json_data={"accessTokenExpiration": ad, "refreshTokenExpiration": rd}))
        with httpx_client_patcher(lambda *a, **k: DummyClient(init_resp), fake_async_client_with_exp):
            token = await fa._do_async_auth()
            assert token.expires_at is not None
            assert token.refresh_token_expires_at is not None


@pytest.mark.asyncio
async def test_async_auth_flow_refresh_still_unauthorized(monkeypatch):
    params = make_params()
    auth_cookies = {"folioAccessToken": "auth-a", "folioRefreshToken": "auth-ar"}
    auth_resp = DummyResponse(cookies=auth_cookies, json_data={})

    def fake_client(*args, **kwargs):
        return DummyClient(auth_resp)

    def fake_async_client(*args, **kwargs):
        return DummyAsyncClient(auth_resp)

    with httpx_client_patcher(fake_client, fake_async_client):
        fa = FolioAuth(params)
        req = httpx.Request("GET", "https//folio/asyncfail")
        agen = fa.async_auth_flow(req)
        await agen.__anext__()
        await agen.asend(DummyResponse(status_code=401))
        with pytest.raises(httpx.HTTPStatusError):
            await agen.asend(DummyResponse(status_code=401))


def test_folio_refresh_token_refreshes_when_expired(monkeypatch):
    params = make_params()
    # client will return new tokens
    cookies = {"folioAccessToken": "newt", "folioRefreshToken": "newr"}
    resp = DummyResponse(cookies=cookies, json_data={})

    def fake_client(*args, **kwargs):
        return DummyClient(resp)

    with httpx_client_patcher(fake_client):
        fa = FolioAuth(params)
        now = datetime.now(tz=timezone.utc)
        fa._token = FolioAuth._Token(auth_token="expired", refresh_token="old", expires_at=now - timedelta(seconds=10), refresh_token_expires_at=None, cookies=None)
        assert fa.folio_refresh_token == "newr"


def test_sync_auth_flow_403_retry_success(monkeypatch):
    """403 Forbidden on first attempt should retry, and succeed if retry returns 200."""
    params = make_params()
    auth_cookies = {"folioAccessToken": "auth-t", "folioRefreshToken": "auth-r"}
    auth_resp = DummyResponse(cookies=auth_cookies, json_data={})

    def fake_client(*args, **kwargs):
        return DummyClient(auth_resp)

    with httpx_client_patcher(fake_client):
        fa = FolioAuth(params)
        req = httpx.Request("GET", "https//folio/resource")
        gen = fa.sync_auth_flow(req)
        next(gen)
        # First response is 403 — triggers retry
        yielded = gen.send(DummyResponse(status_code=403))
        assert yielded is req
        # Retry succeeds with 200
        with pytest.raises(StopIteration):
            gen.send(DummyResponse(status_code=200))


def test_sync_auth_flow_403_retry_still_forbidden(monkeypatch):
    """403 on both attempts should raise HTTPStatusError."""
    params = make_params()
    auth_cookies = {"folioAccessToken": "auth-t", "folioRefreshToken": "auth-r"}
    auth_resp = DummyResponse(cookies=auth_cookies, json_data={})

    def fake_client(*args, **kwargs):
        return DummyClient(auth_resp)

    with httpx_client_patcher(fake_client):
        fa = FolioAuth(params)
        req = httpx.Request("GET", "https//folio/resource")
        gen = fa.sync_auth_flow(req)
        next(gen)
        # First response is 403 — triggers retry
        gen.send(DummyResponse(status_code=403))
        # Retry also returns 403 — should raise
        with pytest.raises(httpx.HTTPStatusError):
            gen.send(DummyResponse(status_code=403))


@pytest.mark.asyncio
async def test_async_auth_flow_403_retry_success(monkeypatch):
    """Async: 403 Forbidden on first attempt should retry, and succeed if retry returns 200."""
    params = make_params()
    auth_cookies = {"folioAccessToken": "auth-t", "folioRefreshToken": "auth-r"}
    auth_resp = DummyResponse(cookies=auth_cookies, json_data={})

    def fake_client(*args, **kwargs):
        return DummyClient(auth_resp)

    def fake_async_client(*args, **kwargs):
        return DummyAsyncClient(auth_resp)

    with httpx_client_patcher(fake_client, fake_async_client):
        fa = FolioAuth(params)
        req = httpx.Request("GET", "https//folio/async-resource")
        agen = fa.async_auth_flow(req)
        first = await agen.__anext__()
        assert first is req
        # First response is 403 — triggers retry
        yielded = await agen.asend(DummyResponse(status_code=403))
        assert yielded is req
        # Retry succeeds with 200
        with pytest.raises(StopAsyncIteration):
            await agen.asend(DummyResponse(status_code=200))


@pytest.mark.asyncio
async def test_async_auth_flow_403_retry_still_forbidden(monkeypatch):
    """Async: 403 on both attempts should raise HTTPStatusError."""
    params = make_params()
    auth_cookies = {"folioAccessToken": "auth-t", "folioRefreshToken": "auth-r"}
    auth_resp = DummyResponse(cookies=auth_cookies, json_data={})

    def fake_client(*args, **kwargs):
        return DummyClient(auth_resp)

    def fake_async_client(*args, **kwargs):
        return DummyAsyncClient(auth_resp)

    with httpx_client_patcher(fake_client, fake_async_client):
        fa = FolioAuth(params)
        req = httpx.Request("GET", "https//folio/async-resource")
        agen = fa.async_auth_flow(req)
        await agen.__anext__()
        # First response is 403 — triggers retry
        await agen.asend(DummyResponse(status_code=403))
        # Retry also returns 403 — should raise
        with pytest.raises(httpx.HTTPStatusError):
            await agen.asend(DummyResponse(status_code=403))


# --- Token expiration parsing ---------------------------------------------------


@pytest.mark.parametrize(
    "value",
    [
        "2030-01-01T12:00:00.000Z",  # FOLIO's real format; fromisoformat < 3.11 rejects 'Z'
        "2030-01-01T12:00:00Z",
        "2030-01-01T12:00:00+00:00",
        "2030-01-01T12:00:00+0000",  # offset written without a colon
    ],
)
def test_parse_expiration_accepts_folio_formats(value):
    """Every form FOLIO is known to emit must parse, and must come back tz-aware."""
    parsed = FolioAuth._parse_expiration(value)
    assert parsed is not None
    assert parsed.tzinfo is not None, "naive result would make _token_is_expiring raise TypeError"


def test_parse_expiration_coerces_naive_to_utc():
    parsed = FolioAuth._parse_expiration("2030-01-01T12:00:00")
    assert parsed is not None and parsed.utcoffset() == timedelta(0)


@pytest.mark.parametrize("value", [None, "", "not-a-timestamp", "2030-13-45T99:99:99Z"])
def test_parse_expiration_returns_none_for_unusable_values(value):
    """Unparseable expirations must not raise -- that would break authentication."""
    assert FolioAuth._parse_expiration(value) is None


def test_expiring_check_tolerates_real_folio_timestamp(monkeypatch):
    """End-to-end: a real FOLIO 'Z' timestamp parses and compares without raising."""
    params = make_params()
    resp = DummyResponse(
        cookies={"folioAccessToken": "t", "folioRefreshToken": "r"},
        json_data={
            "accessTokenExpiration": "2030-01-01T12:00:00.000Z",
            "refreshTokenExpiration": "2030-01-02T12:00:00.000Z",
        },
    )
    with httpx_client_patcher(lambda *a, **k: DummyClient(resp)):
        fa = FolioAuth(params)
        assert fa._token.expires_at is not None
        assert fa._token.refresh_token_expires_at is not None
        assert fa._token_is_expiring() is False  # would raise TypeError if naive


class ReadTrackingResponse(DummyResponse):
    """DummyResponse that records whether the body was read before being raised.

    httpx hands the auth flow an *unread* response and only calls response.read()
    if the flow yields again; on an exception it calls response.close(). So the flow
    must read the body itself before raising, or callers inspecting
    exception.response.text get ResponseNotRead.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.read_called = False

    def read(self):
        self.read_called = True
        return super().read()

    async def aread(self):
        self.read_called = True
        return await super().aread()


def test_401_retry_body_is_read_before_raising(monkeypatch):
    """exception.response.text must be usable after auth fails post-refresh."""
    params = make_params()
    auth_resp = DummyResponse(cookies={"folioAccessToken": "t", "folioRefreshToken": "r"})

    with httpx_client_patcher(lambda *a, **k: DummyClient(auth_resp)):
        fa = FolioAuth(params)
        gen = fa.sync_auth_flow(httpx.Request("GET", "https//folio/x"))
        next(gen)
        gen.send(DummyResponse(status_code=401))
        final = ReadTrackingResponse(status_code=401)
        with pytest.raises(httpx.HTTPStatusError):
            gen.send(final)
        assert final.read_called, "body must be read before raising, or .text is unavailable"


@pytest.mark.asyncio
async def test_async_401_retry_body_is_read_before_raising(monkeypatch):
    params = make_params()
    auth_resp = DummyResponse(cookies={"folioAccessToken": "t", "folioRefreshToken": "r"})

    def fake_client(*args, **kwargs):
        return DummyClient(auth_resp)

    def fake_async_client(*args, **kwargs):
        return DummyAsyncClient(auth_resp)

    with httpx_client_patcher(fake_client, fake_async_client):
        fa = FolioAuth(params)
        agen = fa.async_auth_flow(httpx.Request("GET", "https//folio/x"))
        await agen.__anext__()
        await agen.asend(DummyResponse(status_code=401))
        final = ReadTrackingResponse(status_code=401)
        with pytest.raises(httpx.HTTPStatusError):
            await agen.asend(final)
        assert final.read_called


def test_403_retry_body_is_read_before_raising(monkeypatch):
    """Parity check: the 403 path already did this (b579e7b); keep it covered."""
    params = make_params()
    auth_resp = DummyResponse(cookies={"folioAccessToken": "t", "folioRefreshToken": "r"})

    with httpx_client_patcher(lambda *a, **k: DummyClient(auth_resp)):
        fa = FolioAuth(params)
        gen = fa.sync_auth_flow(httpx.Request("GET", "https//folio/x"))
        next(gen)
        gen.send(DummyResponse(status_code=403))
        final = ReadTrackingResponse(status_code=403)
        with pytest.raises(httpx.HTTPStatusError):
            gen.send(final)
        assert final.read_called


def make_token(auth_token="tok", expires_in=timedelta(hours=1)):
    """Build a _Token that is not near expiry."""
    return FolioAuth._Token(
        auth_token=auth_token,
        refresh_token=f"{auth_token}-r",
        expires_at=datetime.now(tz=timezone.utc) + expires_in,
        refresh_token_expires_at=None,
        cookies=None,
    )


# --- Async lock registry ---------------------------------------------------------
# These cover the parts of _get_async_lock that are easy to break by accident.


@pytest.mark.asyncio
async def test_concurrent_async_flows_authenticate_once(monkeypatch):
    """The core guarantee: concurrent coroutines share one login.

    A threading.RLock cannot do this -- it is reentrant on the event loop's thread,
    so every coroutine acquires it and they all authenticate.
    """
    import asyncio

    params = make_params()
    resp = DummyResponse(cookies={"folioAccessToken": "t", "folioRefreshToken": "r"})

    with httpx_client_patcher(
        lambda *a, **k: DummyClient(resp), lambda *a, **k: DummyAsyncClient(resp)
    ):
        fa = FolioAuth(params)
        fa._token = None  # force every flow to want a token
        calls = []

        async def slow_auth():
            calls.append(1)
            await asyncio.sleep(0.01)  # the network round trip
            return make_token("shared")

        fa._do_async_auth = slow_auth

        async def one_request():
            agen = fa.async_auth_flow(httpx.Request("GET", "https//folio/x"))
            await agen.__anext__()
            with pytest.raises(StopAsyncIteration):
                await agen.asend(DummyResponse(status_code=200))

        await asyncio.gather(*(one_request() for _ in range(10)))
        assert calls == [1], f"expected 1 login for 10 concurrent flows, got {len(calls)}"


@pytest.mark.asyncio
async def test_async_lock_is_stable_within_one_loop(monkeypatch):
    """Repeated calls on the same loop must return the identical lock object.

    If this returns a fresh lock each time, mutual exclusion silently disappears.
    """
    params = make_params()
    resp = DummyResponse(cookies={"folioAccessToken": "t"})
    with httpx_client_patcher(lambda *a, **k: DummyClient(resp)):
        fa = FolioAuth(params)
        first = fa._get_async_lock()
        assert all(fa._get_async_lock() is first for _ in range(5))


def test_concurrent_event_loops_each_keep_their_own_lock(monkeypatch):
    """Two live loops in two threads must not clobber each other's lock.

    A single cached lock rebuilt on loop change thrashes here: each loop replaces the
    other's lock, so coroutines within one loop end up holding different objects.
    """
    import asyncio
    import threading

    params = make_params()
    resp = DummyResponse(cookies={"folioAccessToken": "t"})
    with httpx_client_patcher(lambda *a, **k: DummyClient(resp)):
        fa = FolioAuth(params)
        seen = {}
        seen_guard = threading.Lock()

        async def worker(tag):
            for _ in range(20):
                obj = fa._get_async_lock()
                with seen_guard:
                    seen.setdefault(tag, set()).add(id(obj))
                await asyncio.sleep(0.001)

        async def main(tag):
            await asyncio.gather(worker(tag), worker(tag))

        threads = [
            threading.Thread(target=lambda t=tag: asyncio.run(main(t)))
            for tag in ("loopA", "loopB")
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert set(seen) == {"loopA", "loopB"}
        for tag, ids in seen.items():
            assert len(ids) == 1, f"{tag} saw {len(ids)} lock objects; exclusion is broken"
        assert seen["loopA"] != seen["loopB"], "different loops must not share a lock"


def test_async_lock_survives_sequential_event_loops(monkeypatch):
    """A client reused across asyncio.run() calls must work under contention.

    A single cached asyncio.Lock raises "is bound to a different event loop" here --
    but only once there is contention, which is why this test forces two waiters.
    """
    import asyncio

    params = make_params()
    resp = DummyResponse(cookies={"folioAccessToken": "t"})
    with httpx_client_patcher(lambda *a, **k: DummyClient(resp)):
        fa = FolioAuth(params)

        async def contended():
            async def hold():
                async with fa._get_async_lock():
                    await asyncio.sleep(0.01)

            await asyncio.gather(hold(), hold())

        asyncio.run(contended())
        asyncio.run(contended())  # must not raise


def test_async_lock_registry_does_not_leak(monkeypatch):
    """Finished loops must drop out of the registry, or long-lived clients leak."""
    import asyncio
    import gc

    params = make_params()
    resp = DummyResponse(cookies={"folioAccessToken": "t"})
    with httpx_client_patcher(lambda *a, **k: DummyClient(resp)):
        fa = FolioAuth(params)

        async def touch():
            fa._get_async_lock()

        for _ in range(5):
            asyncio.run(touch())
        gc.collect()
        assert len(fa._async_locks) == 0, "WeakKeyDictionary should release dead loops"


def test_get_async_lock_requires_a_running_loop(monkeypatch):
    """Documented precondition: it is an async-only helper."""
    params = make_params()
    resp = DummyResponse(cookies={"folioAccessToken": "t"})
    with httpx_client_patcher(lambda *a, **k: DummyClient(resp)):
        fa = FolioAuth(params)
        with pytest.raises(RuntimeError):
            fa._get_async_lock()


def test_async_lock_guard_is_not_the_sync_lock(monkeypatch):
    """The registry guard must be distinct from _lock, which is held across network I/O.

    If they were the same lock, a sync login in another thread would stall the whole
    event loop for the duration of that login (unbounded when timeout is None).
    """
    params = make_params()
    resp = DummyResponse(cookies={"folioAccessToken": "t"})
    with httpx_client_patcher(lambda *a, **k: DummyClient(resp)):
        fa = FolioAuth(params)
        assert fa._async_locks_guard is not fa._lock


def test_event_loop_not_stalled_while_sync_login_holds_lock(monkeypatch):
    """A thread holding _lock across a slow login must not block the event loop."""
    import asyncio
    import threading
    import time

    params = make_params()
    resp = DummyResponse(cookies={"folioAccessToken": "t"})
    with httpx_client_patcher(lambda *a, **k: DummyClient(resp)):
        fa = FolioAuth(params)
        released = threading.Event()

        def hog():
            with fa._lock:  # mimics sync_auth_flow / FolioClient.login
                time.sleep(0.4)  # a slow /authn/login-with-expiry
            released.set()

        async def main():
            t = threading.Thread(target=hog)
            t.start()
            time.sleep(0.05)  # let the thread take _lock first
            start = time.perf_counter()
            fa._get_async_lock()  # must not wait on _lock
            elapsed = time.perf_counter() - start
            t.join()
            return elapsed

        elapsed = asyncio.run(main())
        assert released.is_set()
        assert elapsed < 0.2, f"_get_async_lock blocked for {elapsed:.3f}s on the sync lock"


# --- 403 retry: replayability and delay ------------------------------------------


@pytest.fixture(autouse=True)
def _no_forbidden_retry_delay(monkeypatch):
    """Neutralize the 403 retry delay for the whole module so tests stay fast.

    Tests that care about the delay set the variable themselves. The default value is
    asserted separately in test_forbidden_retry_delay_default, so this fixture cannot
    hide a change to it.
    """
    monkeypatch.setenv("FOLIOCLIENT_FORBIDDEN_RETRY_DELAY", "0")


def test_forbidden_retry_delay_default(monkeypatch):
    monkeypatch.delenv("FOLIOCLIENT_FORBIDDEN_RETRY_DELAY", raising=False)
    assert FolioAuth._forbidden_retry_delay() == 1.0


@pytest.mark.parametrize(
    "raw,expected",
    [("0", 0.0), ("0.25", 0.25), ("2.5", 2.5), ("-5", 0.0), ("bogus", 1.0), ("", 1.0)],
)
def test_forbidden_retry_delay_from_env(monkeypatch, raw, expected):
    monkeypatch.setenv("FOLIOCLIENT_FORBIDDEN_RETRY_DELAY", raw)
    assert FolioAuth._forbidden_retry_delay() == expected


def test_403_retry_waits_before_replaying(monkeypatch):
    """A masked transient 403 needs time to clear; an instant replay is unlikely to help."""
    import time

    monkeypatch.setenv("FOLIOCLIENT_FORBIDDEN_RETRY_DELAY", "0.2")
    params = make_params()
    resp = DummyResponse(cookies={"folioAccessToken": "t", "folioRefreshToken": "r"})

    with httpx_client_patcher(lambda *a, **k: DummyClient(resp)):
        fa = FolioAuth(params)
        gen = fa.sync_auth_flow(httpx.Request("GET", "https//folio/x"))
        next(gen)
        start = time.perf_counter()
        gen.send(DummyResponse(status_code=403))  # triggers the delayed retry
        elapsed = time.perf_counter() - start
        assert elapsed >= 0.2, f"retry replayed after only {elapsed:.3f}s"


@pytest.mark.asyncio
async def test_async_403_retry_waits_before_replaying(monkeypatch):
    import time

    monkeypatch.setenv("FOLIOCLIENT_FORBIDDEN_RETRY_DELAY", "0.2")
    params = make_params()
    resp = DummyResponse(cookies={"folioAccessToken": "t", "folioRefreshToken": "r"})

    def fake_client(*a, **k):
        return DummyClient(resp)

    def fake_async_client(*a, **k):
        return DummyAsyncClient(resp)

    with httpx_client_patcher(fake_client, fake_async_client):
        fa = FolioAuth(params)
        agen = fa.async_auth_flow(httpx.Request("GET", "https//folio/x"))
        await agen.__anext__()
        start = time.perf_counter()
        await agen.asend(DummyResponse(status_code=403))
        elapsed = time.perf_counter() - start
        assert elapsed >= 0.2


def test_403_retry_delay_of_zero_does_not_sleep(monkeypatch):
    """Setting the delay to 0 must restore immediate-replay behavior."""
    import time

    monkeypatch.setenv("FOLIOCLIENT_FORBIDDEN_RETRY_DELAY", "0")
    params = make_params()
    resp = DummyResponse(cookies={"folioAccessToken": "t", "folioRefreshToken": "r"})

    with httpx_client_patcher(lambda *a, **k: DummyClient(resp)):
        fa = FolioAuth(params)
        gen = fa.sync_auth_flow(httpx.Request("GET", "https//folio/x"))
        next(gen)
        start = time.perf_counter()
        gen.send(DummyResponse(status_code=403))
        assert time.perf_counter() - start < 0.1


# --- Request replayability -------------------------------------------------------


def _generator_body():
    yield b'{"record": "important"}'


def test_in_memory_bodies_are_replayable():
    assert FolioAuth._request_is_replayable(httpx.Request("GET", "https//folio/x"))
    assert FolioAuth._request_is_replayable(
        httpx.Request("POST", "https//folio/x", json={"a": 1})
    )
    assert FolioAuth._request_is_replayable(
        httpx.Request("POST", "https//folio/x", content=b"raw-bytes")
    )
    assert FolioAuth._request_is_replayable(
        httpx.Request("POST", "https//folio/x", data={"a": "1"})
    )


def test_multipart_is_replayable(tmp_path):
    """files= produces a MultipartStream with no _content, but it IS replayable.

    httpx seeks each file field back to 0 on every render, so testing _content alone
    would wrongly drop the retry for every file upload.
    """
    f = tmp_path / "record.mrc"
    f.write_bytes(b"RECORD-DATA")
    req = httpx.Request("POST", "https//folio/x", files={"file": f.open("rb")})
    assert not hasattr(req, "_content"), "precondition: multipart is not materialized"
    assert FolioAuth._request_is_replayable(req)


def test_multipart_bodies_really_do_replay_identically(tmp_path):
    """Verify the assumption behind the multipart allowlist entry."""
    f = tmp_path / "record.mrc"
    f.write_bytes(b"RECORD-DATA")
    req = httpx.Request("POST", "https//folio/x", files={"file": f.open("rb")})
    first = b"".join(req.stream)
    second = b"".join(req.stream)
    assert first == second and b"RECORD-DATA" in first


@pytest.mark.parametrize("body_kind", ["generator", "filehandle"])
def test_streaming_bodies_are_not_replayable(tmp_path, body_kind):
    if body_kind == "generator":
        body = _generator_body()
    else:
        f = tmp_path / "record.mrc"
        f.write_bytes(b"RECORD-DATA")
        body = f.open("rb")
    req = httpx.Request("POST", "https//folio/x", content=body)
    assert not FolioAuth._request_is_replayable(req)


def test_multipart_403_is_retried(tmp_path):
    """End-to-end: a file upload must still get its 403 retry."""
    f = tmp_path / "record.mrc"
    f.write_bytes(b"RECORD-DATA")
    params = make_params()
    resp = DummyResponse(cookies={"folioAccessToken": "t", "folioRefreshToken": "r"})

    with httpx_client_patcher(lambda *a, **k: DummyClient(resp)):
        fa = FolioAuth(params)
        req = httpx.Request("POST", "https//folio/x", files={"file": f.open("rb")})
        gen = fa.sync_auth_flow(req)
        next(gen)
        retried = gen.send(DummyResponse(status_code=403))
        assert retried is req, "multipart uploads must be retried on 403"


def test_streaming_403_is_not_retried(tmp_path):
    """A consumed stream must surface the 403 rather than a silently-emptied retry."""
    params = make_params()
    resp = DummyResponse(cookies={"folioAccessToken": "t", "folioRefreshToken": "r"})

    with httpx_client_patcher(lambda *a, **k: DummyClient(resp)):
        fa = FolioAuth(params)
        req = httpx.Request("POST", "https//folio/x", content=_generator_body())
        gen = fa.sync_auth_flow(req)
        next(gen)
        with pytest.raises(StopIteration):
            gen.send(DummyResponse(status_code=403))


def test_streaming_401_still_refreshes_the_token(tmp_path):
    """We cannot retry a consumed stream, but the rejected token must still be replaced.

    Otherwise every later request keeps using a token the server has rejected -- and
    with an unknown expiry the client would never recover on its own.
    """
    params = make_params()
    resp = DummyResponse(
        cookies={"folioAccessToken": "stale", "folioRefreshToken": "r"},
        json_data={
            "accessTokenExpiration": (
                datetime.now(tz=timezone.utc) + timedelta(hours=1)
            ).isoformat()
        },
    )

    with httpx_client_patcher(lambda *a, **k: DummyClient(resp)):
        fa = FolioAuth(params)
        assert fa._token.auth_token == "stale"
        fa._do_sync_auth = lambda: make_token("refreshed")
        req = httpx.Request("POST", "https//folio/x", content=_generator_body())
        gen = fa.sync_auth_flow(req)
        next(gen)
        with pytest.raises(StopIteration):
            gen.send(DummyResponse(status_code=401))
        assert fa._token.auth_token == "refreshed", "token must be refreshed for later requests"


@pytest.mark.asyncio
async def test_async_streaming_401_still_refreshes_the_token():
    params = make_params()
    resp = DummyResponse(
        cookies={"folioAccessToken": "stale", "folioRefreshToken": "r"},
        json_data={
            "accessTokenExpiration": (
                datetime.now(tz=timezone.utc) + timedelta(hours=1)
            ).isoformat()
        },
    )

    def fake_client(*a, **k):
        return DummyClient(resp)

    def fake_async_client(*a, **k):
        return DummyAsyncClient(resp)

    with httpx_client_patcher(fake_client, fake_async_client):
        fa = FolioAuth(params)

        async def refreshed():
            return make_token("refreshed")

        fa._do_async_auth = refreshed
        req = httpx.Request("POST", "https//folio/x", content=_generator_body())
        agen = fa.async_auth_flow(req)
        await agen.__anext__()
        with pytest.raises(StopAsyncIteration):
            await agen.asend(DummyResponse(status_code=401))
        assert fa._token.auth_token == "refreshed"


# --- Sync lock reentrancy --------------------------------------------------------


class ReentrancyDetectingLock:
    """RLock wrapper that raises if one thread acquires it while already holding it.

    FolioAuth._lock is an RLock so that unexpected nesting degrades to a redundant
    login rather than hanging a caller's process on a lock held across network I/O.
    That safety net must not silently excuse real nesting, so we assert here what
    RLock permits at runtime.
    """

    def __init__(self):
        import threading

        self._real = threading.RLock()
        self._state = threading.local()
        self.acquisitions = 0

    def __enter__(self):
        depth = getattr(self._state, "depth", 0)
        if depth:
            raise AssertionError(f"_lock acquired reentrantly (depth {depth + 1})")
        self._state.depth = depth + 1
        self.acquisitions += 1
        return self._real.__enter__()

    def __exit__(self, *exc):
        self._state.depth -= 1
        return self._real.__exit__(*exc)


def test_reentrancy_detector_actually_detects():
    """Guard the guard: a detector that never fires would make the test below vacuous."""
    lock = ReentrancyDetectingLock()
    with lock:
        with pytest.raises(AssertionError, match="reentrantly"):
            with lock:
                pass


def test_sync_lock_is_never_acquired_reentrantly(monkeypatch):
    """No sync path may acquire _lock while already holding it.

    Covers the proactive refresh, the token properties, the 401 re-authentication and
    the 403 retry. If a future change puts an access_token / folio_auth_token read
    inside a locked region, this fails instead of deadlocking a user in production.
    """
    params = make_params()
    resp = DummyResponse(cookies={"folioAccessToken": "t", "folioRefreshToken": "r"})

    with httpx_client_patcher(lambda *a, **k: DummyClient(resp)):
        fa = FolioAuth(params)
        detector = ReentrancyDetectingLock()
        fa._lock = detector

        # Proactive refresh via _ensure_sync_token, plus both token properties.
        fa._token = None
        assert fa.folio_auth_token == "t"
        assert fa.folio_refresh_token == "r"

        # Proactive refresh inside sync_auth_flow, then the 401 re-authentication.
        fa._token = make_token("current", expires_in=-timedelta(minutes=5))
        gen = fa.sync_auth_flow(httpx.Request("GET", "https//folio/x"))
        next(gen)
        gen.send(DummyResponse(status_code=401))
        with pytest.raises(StopIteration):
            gen.send(DummyResponse(status_code=200))

        # The 403 retry path (does not lock, but must not start doing so reentrantly).
        gen2 = fa.sync_auth_flow(httpx.Request("GET", "https//folio/x"))
        next(gen2)
        gen2.send(DummyResponse(status_code=403))
        with pytest.raises(StopIteration):
            gen2.send(DummyResponse(status_code=200))

        assert detector.acquisitions >= 3, (
            f"expected the locked paths to be exercised, saw {detector.acquisitions}"
        )
