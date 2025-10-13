
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


def test_sync_auth_flow_pass_branch_no_refresh(monkeypatch):
    params = make_params()
    # initial auth response with future expiration
    now = datetime.now(tz=timezone.utc)
    resp = DummyResponse(cookies={"folioAccessToken": "init", "folioRefreshToken": "init-r"}, json_data={"accessTokenExpiration": (now + timedelta(hours=1)).isoformat()})

    def fake_client(*args, **kwargs):
        return DummyClient(resp)

    with httpx_client_patcher(fake_client):
        fa = FolioAuth(params)
        fa._do_sync_auth = lambda: (_ for _ in ()).throw(RuntimeError("should not refresh"))
        req = httpx.Request("GET", "https//folio/resource")
        gen = fa.sync_auth_flow(req)
        next(gen)
        yielded = gen.send(DummyResponse(status_code=401))
        assert yielded is req
        with pytest.raises(StopIteration):
            gen.send(DummyResponse(status_code=200))


@pytest.mark.asyncio
async def test_async_auth_flow_pass_branch_no_refresh(monkeypatch):
    params = make_params()
    now = datetime.now(tz=timezone.utc)
    resp = DummyResponse(cookies={"folioAccessToken": "i2", "folioRefreshToken": "r2"}, json_data={"accessTokenExpiration": (now + timedelta(hours=1)).isoformat()})

    def fake_client(*args, **kwargs):
        return DummyClient(resp)
    def fake_async_client(*args, **kwargs):
        return DummyAsyncClient(resp)

    with httpx_client_patcher(fake_client, fake_async_client):
        fa = FolioAuth(params)
        async def should_not_call():
            raise RuntimeError("should not be called")
        fa._do_async_auth = should_not_call
        req = httpx.Request("GET", "https//folio/asyncpass")
        agen = fa.async_auth_flow(req)
        first = await agen.__anext__()
        assert first is req
        second = await agen.asend(DummyResponse(status_code=401))
        assert second is req
        with pytest.raises(StopAsyncIteration):
            await agen.asend(DummyResponse(status_code=200))


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
