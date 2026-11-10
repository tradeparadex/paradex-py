"""Tests for SessionAccounts: one session key, a JWT, REST client and websocket per granted account."""

import asyncio
import base64
import json
import threading
import time
from collections.abc import Callable
from decimal import Decimal

import httpx
import pytest
from eth_account import Account as EthAccount
from eth_account.messages import encode_typed_data
from starknet_py.common import int_from_bytes
from starknet_py.hash.utils import verify_message_signature
from starknet_py.utils.typed_data import TypedData
from websockets.protocol import State

from paradex_py.api.http_client import HttpClient
from paradex_py.api.models import SystemConfig
from paradex_py.common.order import Order, OrderSide, OrderType
from paradex_py.environment import TESTNET
from paradex_py.message.auth import build_auth_message
from paradex_py.message.order import build_order_message
from paradex_py.message.session import Builder, Limits, SessionGrant
from paradex_py.session_accounts import (
    SESSION_AUTH_MAX_SECONDS,
    LocalOwnerSigner,
    SessionAccounts,
    SessionDroppedError,
    SessionRejectedError,
    SessionRevokeError,
    new_session_key,
    register_session,
)

CHAIN = "PRIVATE_SN_PARACLEAR_TESTNET"
CHAIN_ID = int_from_bytes(CHAIN.encode())
MAIN = "0xa1"
SUB_1 = "0xb1"
SUB_2 = "0xb2"
SESSION_PRIVATE, SESSION_PUBLIC = new_session_key()
REGISTERED_ID = "0x" + "ab" * 32  # what the fake server answers a registration with
LIMITS = Limits("25000", "100000", "500000", "5000", "10", ["BTC-USD-PERP"])

CONFIG = SystemConfig(
    starknet_fullnode_rpc_url="https://rpc.invalid",
    starknet_fullnode_rpc_base_url="https://rpc.invalid",
    starknet_chain_id=CHAIN,
    block_explorer_url="",
    paraclear_address="0x1",
    paraclear_decimals=8,
    paraclear_account_proxy_hash="0x1",
    paraclear_account_hash="0x1",
    oracle_address="0x1",
    bridged_tokens=[],
    l1_core_contract_address="0x1",
    l1_operator_address="0x1",
    l1_chain_id="1",
    liquidation_fee="0",
)


def _jwt(account: str, exp: float) -> str:
    def part(data: dict) -> str:
        return base64.urlsafe_b64encode(json.dumps(data).encode()).rstrip(b"=").decode()

    return f"{part({'alg': 'none'})}.{part({'sub': account, 'exp': exp})}.sig"


class FakeServer:
    """A mocked Paradex REST API that records requests and can refuse the session key."""

    def __init__(self):
        self.requests: list[httpx.Request] = []
        self.revoked: set[str] = set()
        self.refusal_error = "SESSION_REVOKED"
        self.refuse_orders_with: int | None = None
        self.auth_counts: dict[str, int] = {}
        self.grant_state = "active"
        self.status_code = 200
        self.delete_status = 204
        self.unknown_route = False
        self.auth_failure: str | None = None
        self.auth_threads: list[int] = []
        self.fail_connect_after: int | None = None
        self.after_login: Callable[[], None] | None = None
        self.owned_subaccounts = [SUB_1, SUB_2]
        self.listing_status = 200
        self.listing_body: object | None = None

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path
        if path.startswith("/v1/auth/"):
            account = request.headers["PARADEX-STARKNET-ACCOUNT"]
            self.auth_counts[account] = self.auth_counts.get(account, 0) + 1
            self.auth_threads.append(threading.get_ident())
            if self.auth_failure == "network":
                raise httpx.ConnectError("unreachable", request=request)
            if self.auth_failure == "rate-limited":
                return httpx.Response(429, json={"error": "RATE_LIMIT", "message": "slow down", "data": None})
            if account in self.revoked:
                # The 400 /auth answers a session key with for a revoked, expired or unknown grant.
                return httpx.Response(400, json={"error": self.refusal_error, "message": "refused", "data": None})
            if self.after_login:
                self.after_login()
            return httpx.Response(200, json={"jwt_token": _jwt(account, time.time() + SESSION_AUTH_MAX_SECONDS)})
        if path in ("/v1/orders", "/v1/orders/batch"):
            if self.refuse_orders_with:
                return httpx.Response(self.refuse_orders_with, json=self._error_body(self.refuse_orders_with))
            return httpx.Response(201, json={"id": "order-1"})
        if path.startswith("/v2/sessions"):
            return self._sessions(request)
        if path == "/v2/onboarding/subaccounts":
            return self._subaccounts(request)
        return httpx.Response(204)

    def _subaccounts(self, request: httpx.Request) -> httpx.Response:
        assert "Authorization" not in request.headers  # listed before the owner holds a JWT
        if self.listing_status != 200:
            return httpx.Response(self.listing_status, json={"message": "Not Found"})
        if self.listing_body is not None:
            return httpx.Response(200, json=self.listing_body)
        results = [{"address": address, "index": i} for i, address in enumerate(self.owned_subaccounts)]
        return httpx.Response(200, json={"results": results})

    def _sessions(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/status"):
            assert "Authorization" not in request.headers  # the status endpoint is unauthenticated
            if self.status_code == 0:
                raise httpx.ConnectError("unreachable", request=request)
            if self.status_code != 200:
                return httpx.Response(self.status_code, json=self._error_body(self.status_code))
            return httpx.Response(200, json={"state": self.grant_state})
        if request.method == "DELETE":
            if self.delete_status != 204:
                return httpx.Response(self.delete_status, json=self._error_body(self.delete_status))
            self.grant_state = "revoked"
            return httpx.Response(204)
        return httpx.Response(201, json={"grant_id": REGISTERED_ID, "expires_at": 1, "accounts": [MAIN]})

    def _error_body(self, status: int) -> dict:
        if status == 404 and self.unknown_route:
            return {"message": "Not Found"}  # a 404 page for a route the server doesn't serve
        if status == 404:
            return {"error": "NOT_FOUND", "message": "session not found"}
        if status == 400:
            return {"error": self.refusal_error, "message": "refused", "data": None}
        return {"error": "X", "message": "x", "data": None}

    def client(self) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(self.handler))

    def by_path(self, prefix: str) -> list[httpx.Request]:
        return [r for r in self.requests if r.url.path.startswith(prefix)]


class FakeSocket:
    def __init__(self, url: str, headers: dict[str, str]):
        self.url = url
        self.headers = headers
        self.sent: list[dict] = []
        self.state = State.OPEN

    async def send(self, data: str) -> None:
        self.sent.append(json.loads(data))

    async def recv(self) -> str:
        await asyncio.sleep(0.01)  # idle traffic, so the reader regularly releases its lock
        return json.dumps({"jsonrpc": "2.0", "method": "heartbeat"})

    async def close(self) -> None:
        self.state = State.CLOSED


class FakeConnector:
    def __init__(self, fail: bool = False, fail_after: int | None = None):
        self.sockets: list[FakeSocket] = []
        self.fail = fail
        self.fail_after = fail_after

    async def __call__(self, url: str, headers: dict[str, str]) -> FakeSocket:
        if self.fail or (self.fail_after is not None and len(self.sockets) >= self.fail_after):
            raise OSError("refused")
        socket = FakeSocket(url, headers)
        self.sockets.append(socket)
        return socket


class Clock:
    def __init__(self):
        self.now = time.time()

    def __call__(self) -> float:
        return self.now


def _grant(clock: Clock, ttl: int = 3600, **overrides) -> SessionGrant:
    fields = {
        "paradex_chain": CHAIN,
        "environment": "testnet",
        "account": MAIN,
        "session_key": SESSION_PUBLIC,
        "label": "bot",
        "scopes": ["trade"],
        "limits": LIMITS,
        "subaccounts": [SUB_1, SUB_2],
        "issued_at": int(clock.now),
        "expires_at": int(clock.now) + ttl,
    }
    fields.update(overrides)
    return SessionGrant(**fields)


def _grant_id(grant: SessionGrant) -> str:
    return grant.grant_ids()[0]  # an EVM owner's grant


def _status_checks(server: FakeServer, session: SessionAccounts) -> list[httpx.Request]:
    return server.by_path(f"/v2/sessions/{session.grant_id}/status")


def _session(server: FakeServer, clock: Clock, grant: SessionGrant | None = None, **kwargs) -> SessionAccounts:
    kwargs.setdefault("ws_enabled", False)
    grant = grant or _grant(clock)
    kwargs.setdefault("grant_id", _grant_id(grant))
    kwargs.setdefault("sleep", lambda seconds: None)
    kwargs.setdefault("http_client_factory", server.client)
    return SessionAccounts(
        env=TESTNET,
        grant=grant,
        session_private_key=SESSION_PRIVATE,
        config=CONFIG,
        clock=clock,
        **kwargs,
    )


def _order() -> Order:
    return Order(
        market="BTC-USD-PERP",
        order_type=OrderType.Limit,
        order_side=OrderSide.Buy,
        size=Decimal("0.1"),
        limit_price=Decimal("50000"),
    )


def _verify(message, address: str, signature: list[str]) -> bool:
    message_hash = TypedData.from_dict(message).message_hash(int(address, 16))
    return verify_message_signature(message_hash, [int(x) for x in signature], int(SESSION_PUBLIC, 16))


# -- authentication ---------------------------------------------------------------------------


def test_mints_one_session_jwt_per_account():
    server, clock = FakeServer(), Clock()
    session = _session(server, clock)

    assert session.accounts == [MAIN, SUB_1, SUB_2]
    auths = server.by_path("/v1/auth/")
    assert [r.headers["PARADEX-STARKNET-ACCOUNT"] for r in auths] == [MAIN, SUB_1, SUB_2]
    for request in auths:
        # /auth names the session key, and the session key signs for the account in the header.
        assert request.url.path == f"/v1/auth/{SESSION_PUBLIC}"
        timestamp = int(request.headers["PARADEX-TIMESTAMP"])
        expiry = int(request.headers["PARADEX-SIGNATURE-EXPIRATION"])
        assert expiry - timestamp == SESSION_AUTH_MAX_SECONDS
        signature = json.loads(request.headers["PARADEX-STARKNET-SIGNATURE"])
        message = build_auth_message(CHAIN_ID, timestamp, expiry)
        assert _verify(message, request.headers["PARADEX-STARKNET-ACCOUNT"], signature)
        # token_usage is never self-declared.
        assert "token_usage" not in request.url.params
    for address in session.accounts:
        assert session.api(address).client.headers["Authorization"] == f"Bearer {_jwt_account(session, address)}"


def _jwt_account(session: SessionAccounts, address: str) -> str:
    return session.api(address).account.jwt_token


def test_auth_expiry_never_passes_session_expiry():
    server, clock = FakeServer(), Clock()
    grant = _grant(clock, ttl=120)
    _session(server, clock, grant=grant)

    for request in server.by_path("/v1/auth/"):
        assert int(request.headers["PARADEX-SIGNATURE-EXPIRATION"]) == grant.expires_at


def test_refreshes_expired_jwt_for_that_account_only():
    server, clock = FakeServer(), Clock()
    session = _session(server, clock)
    session.api(SUB_1)._token_exp = 0  # force expiry

    session.submit_order(SUB_1, _order())

    assert server.auth_counts == {MAIN: 1, SUB_1: 2, SUB_2: 1}


# -- routing -------------------------------------------------------------------------------------


def test_routes_orders_by_account_with_that_accounts_jwt():
    server, clock = FakeServer(), Clock()
    session = _session(server, clock)

    order = _order()
    session.submit_order("0x00B2", order)  # any hex spelling of a granted account

    (request,) = server.by_path("/v1/orders")
    assert request.headers["Authorization"] == f"Bearer {_jwt_account(session, SUB_2)}"
    body = json.loads(request.content)
    assert not {"on_behalf_of", "on_behalf_of_account"}.intersection(body)
    # The session key signs the order for the account it is routed to.
    assert _verify(build_order_message(CHAIN_ID, order), SUB_2, json.loads(body["signature"]))


def test_batch_modify_and_cancel_route_by_account():
    server, clock = FakeServer(), Clock()
    session = _session(server, clock)

    session.submit_orders_batch(SUB_1, [_order(), _order()])
    session.modify_order(MAIN, "order-1", _order())
    session.cancel_order(SUB_2, "order-1")
    session.cancel_all_orders(SUB_1, {"market": "BTC-USD-PERP"})

    sent = [(r.method, r.url.path, r.headers["Authorization"]) for r in server.requests if "/auth/" not in r.url.path]
    assert sent == [
        ("POST", "/v1/orders/batch", f"Bearer {_jwt_account(session, SUB_1)}"),
        ("PUT", "/v1/orders/order-1", f"Bearer {_jwt_account(session, MAIN)}"),
        ("DELETE", "/v1/orders/order-1", f"Bearer {_jwt_account(session, SUB_2)}"),
        ("DELETE", "/v1/orders", f"Bearer {_jwt_account(session, SUB_1)}"),
    ]


@pytest.mark.parametrize("account", ["0xc1", "not-hex", ""])
def test_refuses_accounts_outside_the_grant(account):
    session = _session(FakeServer(), Clock())
    with pytest.raises(ValueError, match=r"not covered|invalid account"):
        session.api(account)


@pytest.mark.parametrize("key", ["on_behalf_of_account", "on_behalf_of"])
def test_never_acts_on_behalf_of(key):
    server = FakeServer()
    session = _session(server, Clock())
    with pytest.raises(ValueError, match="on_behalf_of"):
        session.cancel_all_orders(MAIN, {key: SUB_1})
    assert not server.by_path("/v1/orders")


def test_forbidden_request_does_not_drop_the_session():
    server, clock = FakeServer(), Clock()
    session = _session(server, clock)
    server.refuse_orders_with = 403  # e.g. a scope the grant does not carry

    with pytest.raises(SessionRejectedError) as excinfo:
        session.submit_order(MAIN, _order())

    assert excinfo.value.status_code == 403
    assert session.is_live
    assert server.auth_counts[MAIN] == 1  # no fresh login either: only a 401 means the JWT may be stale
    assert not _status_checks(server, session)  # a refused action is not a revocation signal


def test_refused_login_with_an_active_grant_retries_then_raises():
    server, clock = FakeServer(), Clock()
    sleeps = []
    session = _session(server, clock, sleep=sleeps.append)
    server.revoked.add(SUB_1)  # e.g. a transient refusal; the grant itself is still active
    session.api(SUB_1)._token_exp = 0

    with pytest.raises(SessionRejectedError):
        session.submit_order(SUB_1, _order())

    assert session.is_live
    assert server.auth_counts[SUB_1] == 4  # the first login, then three refused attempts
    assert sleeps == [0.5, 1.0]  # backoff between attempts
    # The state is asked once per refusal, without a login; no polling.
    assert len(_status_checks(server, session)) == 3
    server.revoked.clear()
    session.submit_order(SUB_1, _order())  # the caller can retry


@pytest.mark.parametrize("error", ["SESSION_REVOKED", "SESSION_EXPIRED", "INVALID_SUBKEY"])
def test_session_error_from_login_checks_the_grant_and_drops(error):
    server, clock = FakeServer(), Clock()
    reasons = []
    session = _session(server, clock, on_dropped=reasons.append)
    server.revoked.add(SUB_1)
    server.refusal_error = error
    server.grant_state = "revoked"
    session.api(SUB_1)._token_exp = 0

    with pytest.raises(SessionDroppedError, match="revoked"):
        session.submit_order(SUB_1, _order())
    assert not session.is_live
    assert reasons == [f"grant {session.grant_id} is revoked"]
    assert len(_status_checks(server, session)) == 1


def test_other_400_from_login_is_not_a_session_refusal():
    server, clock = FakeServer(), Clock()
    session = _session(server, clock)
    server.revoked.add(SUB_1)
    server.refusal_error = "VALIDATION_ERROR"
    session.api(SUB_1)._token_exp = 0

    with pytest.raises(ValueError) as raised:
        session.submit_order(SUB_1, _order())
    assert not isinstance(raised.value, SessionRejectedError)
    assert session.is_live
    assert not _status_checks(server, session)


def test_session_error_on_a_call_logs_in_again_and_drops_a_revoked_grant():
    server, clock = FakeServer(), Clock()
    session = _session(server, clock)
    server.refuse_orders_with = 400
    server.revoked.add(MAIN)
    server.grant_state = "revoked"

    with pytest.raises(SessionDroppedError, match="revoked"):
        session.submit_order(MAIN, _order())
    assert not session.is_live


def test_revoke_refused_with_a_session_error_for_a_grant_revoked_elsewhere_drops():
    server, clock = FakeServer(), Clock()
    session = _session(server, clock)
    server.delete_status = 400
    server.grant_state = "revoked"

    with pytest.raises(SessionDroppedError, match="revoked"):
        session.revoke()
    assert not session.is_live


def test_401_on_a_call_with_a_revoked_grant_drops_everything():
    server, clock = FakeServer(), Clock()
    session = _session(server, clock)
    server.refuse_orders_with = 401
    server.revoked.add(MAIN)
    server.grant_state = "revoked"

    with pytest.raises(SessionDroppedError, match="revoked"):
        session.submit_order(MAIN, _order())
    assert not session.is_live


def test_401_on_a_call_logs_in_again_and_raises_when_the_login_works():
    server, clock = FakeServer(), Clock()
    session = _session(server, clock)
    server.refuse_orders_with = 401  # e.g. the JWT went stale between the check and the call

    with pytest.raises(SessionRejectedError):
        session.submit_order(MAIN, _order())

    assert session.is_live
    assert server.auth_counts[MAIN] == 2
    assert not _status_checks(server, session)  # the login worked, so the grant is fine


def test_unknown_grant_state_does_not_drop():
    server, clock = FakeServer(), Clock()
    session = _session(server, clock)
    server.revoked.add(SUB_1)
    server.status_code = 503  # the state cannot be learned
    session.api(SUB_1)._token_exp = 0

    with pytest.raises(SessionRejectedError):
        session.submit_order(SUB_1, _order())
    assert session.is_live


def test_revoked_before_the_first_login_drops_and_closes_clients():
    server, clock = FakeServer(), Clock()
    server.revoked.add(MAIN)
    server.grant_state = "revoked"
    created = []

    def factory():
        created.append(server.client())
        return created[-1]

    grant = _grant(clock)
    with pytest.raises(SessionDroppedError, match="revoked"):
        _session(server, clock, grant=grant, http_client_factory=factory)

    # No JWT exists yet; the unauthenticated status endpoint still answers.
    assert len(server.by_path(f"/v2/sessions/{_grant_id(grant)}/status")) == 1
    assert all(client.is_closed for client in created)


def test_unreachable_status_does_not_drop():
    server, clock = FakeServer(), Clock()
    session = _session(server, clock)
    server.revoked.add(SUB_2)
    server.status_code = 0
    session.api(SUB_2)._token_exp = 0

    with pytest.raises(SessionRejectedError):
        session.submit_order(SUB_2, _order())
    assert session.is_live


def test_unknown_grant_drops_everything():
    server, clock = FakeServer(), Clock()
    session = _session(server, clock)
    server.revoked.add(SUB_2)
    server.status_code = 404
    session.api(SUB_2)._token_exp = 0

    with pytest.raises(SessionDroppedError, match=f"{session.grant_id} is unknown"):
        session.submit_order(SUB_2, _order())
    assert not session.is_live


def test_auth_keeps_auth_params_when_refreshed_without_them():
    server, clock = FakeServer(), Clock()
    session = _session(server, clock, auth_params={"flag": "x"})
    session.api(MAIN).auth()  # what the websocket refresh path calls
    assert all(r.url.params.get("flag") == "x" for r in server.by_path("/v1/auth/"))


def test_factory_must_build_a_client_per_account():
    server, clock = FakeServer(), Clock()
    shared = server.client()
    with pytest.raises(ValueError, match="new client per account"):
        _session(server, clock, http_client_factory=lambda: shared)


def test_revoke_deletes_the_grant_and_drops_everything():
    server, clock = FakeServer(), Clock()
    reasons = []
    session = _session(server, clock, on_dropped=reasons.append)
    jwt = _jwt_account(session, MAIN)

    session.revoke()

    (request,) = [r for r in server.requests if r.method == "DELETE"]
    assert request.url.path == f"/v2/sessions/{session.grant_id}"
    assert request.url.params["cancel_orders"] == "true"  # otherwise a self-revoke leaves orders working
    assert request.headers["Authorization"] == f"Bearer {jwt}"
    assert reasons == ["revoked by this session"]
    assert not session.is_live


def test_a_call_whose_login_overlaps_a_drop_is_not_sent():
    server, clock = FakeServer(), Clock()
    session = _session(server, clock)
    session.api(MAIN)._token_exp = 0
    server.after_login = lambda: session.drop("revoked by this session")  # e.g. revoke() on another thread

    with pytest.raises(SessionDroppedError):
        session.submit_order(MAIN, _order())
    assert not server.by_path("/v1/orders")


def test_session_restarts_from_a_saved_grant():
    server, clock = FakeServer(), Clock()
    grant = _grant(clock)
    saved = json.loads(json.dumps({"grant": grant.to_message(), "grant_id": _grant_id(grant)}))

    session = _session(server, clock, grant=SessionGrant.from_message(saved["grant"]), grant_id=saved["grant_id"])
    session.submit_order(MAIN, _order())
    assert session.grant_id == _grant_id(grant)


def test_a_grant_rebuilt_with_a_new_nonce_is_refused_for_the_saved_id():
    server, clock = FakeServer(), Clock()
    grant = _grant(clock)
    with pytest.raises(ValueError, match="is not this grant's id"):
        _session(server, clock, grant=_grant(clock), grant_id=_grant_id(grant))


def test_session_accepts_a_stark_owners_grant_id():
    server, clock = FakeServer(), Clock()
    grant = _grant(clock)
    session = _session(server, clock, grant=grant, grant_id=grant.grant_ids()[1])
    assert session.grant_id == f"0x{grant.snip12_hash():064x}"


@pytest.mark.parametrize("status", [500, 503])
def test_revoke_failing_on_the_server_says_the_owner_must_cancel(status):
    server, clock = FakeServer(), Clock()
    session = _session(server, clock)
    server.delete_status = status

    with pytest.raises(SessionRevokeError, match="cancel_orders=true"):
        session.revoke()
    assert session.is_live


def test_revoke_refused_by_the_client_side_does_not_mention_orders():
    server, clock = FakeServer(), Clock()
    session = _session(server, clock)
    server.delete_status = 409

    with pytest.raises(SessionRevokeError) as raised:
        session.revoke()
    assert "cancel_orders" not in str(raised.value)


def test_revoke_can_keep_orders_working():
    server, clock = FakeServer(), Clock()
    session = _session(server, clock)

    session.revoke(cancel_orders=False)

    (request,) = [r for r in server.requests if r.method == "DELETE"]
    assert "cancel_orders" not in request.url.params
    assert not session.is_live


# -- dropping ------------------------------------------------------------------------------------


def test_revoked_at_start_drops_everything():
    server, clock = FakeServer(), Clock()
    server.revoked.add(SUB_1)
    server.grant_state = "revoked"
    reasons = []

    grant = _grant(clock)
    with pytest.raises(SessionDroppedError, match=f"{_grant_id(grant)} is revoked"):
        _session(server, clock, grant=grant, on_dropped=reasons.append)

    assert len(reasons) == 1
    assert SUB_2 not in server.auth_counts  # no further account is authenticated


def test_revoked_at_refresh_drops_every_account():
    server, clock = FakeServer(), Clock()
    reasons = []
    session = _session(server, clock, on_dropped=reasons.append)
    server.revoked.add(SUB_2)
    server.grant_state = "expired"
    session.api(SUB_2)._token_exp = 0

    with pytest.raises(SessionDroppedError):
        session.submit_order(SUB_2, _order())

    assert not session.is_live
    assert reasons == [session.dropped_reason]
    for address in (MAIN, SUB_1, SUB_2):
        with pytest.raises(SessionDroppedError):
            session.submit_order(address, _order())
    assert not server.by_path("/v1/orders")
    for client in session._clients.values():
        assert "Authorization" not in client.client.headers
        assert client.account.jwt_token == ""


def test_expiry_drops_every_account():
    server, clock = FakeServer(), Clock()
    reasons = []
    session = _session(server, clock, on_dropped=reasons.append)
    clock.now = session.grant.expires_at

    with pytest.raises(SessionDroppedError, match="expired"):
        session.submit_order(MAIN, _order())
    with pytest.raises(SessionDroppedError):
        session.api(SUB_1)

    assert reasons == ["session expired"]
    assert not server.by_path("/v1/orders")


def test_drop_is_idempotent():
    reasons = []
    session = _session(FakeServer(), Clock(), on_dropped=reasons.append)
    session.drop("first")
    session.drop("second")
    assert reasons == ["first"]
    assert session.dropped_reason == "first"


# -- construction refusals -----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("overrides", "kwargs", "error"),
    [
        ({"session_key": "0x1234"}, {}, "does not match grant.session_key"),
        ({"environment": "mainnet"}, {}, "the 'testnet' environment needs 'testnet'"),
        ({"paradex_chain": "PRIVATE_SN_PARACLEAR_MAINNET"}, {}, "grant is for chain"),
        ({}, {"auth_params": {"token_usage": "interactive"}}, "set by the server"),
        ({}, {"grant_id": ""}, "is not this grant's id"),
        ({}, {"grant_id": REGISTERED_ID}, "is not this grant's id"),  # well formed, but another grant's
        ({"scopes": ["withdraw:owner"]}, {}, "reserved and refused"),
        ({"builder": Builder("0xbb", "0.0005"), "limits": Limits("", "", "", "", "", [])}, {}, "maxOrderNotional"),
    ],
)
def test_construction_refusals(overrides, kwargs, error):
    server, clock = FakeServer(), Clock()
    with pytest.raises(ValueError, match=error):
        _session(server, clock, grant=_grant(clock, **overrides), **kwargs)
    assert not server.requests


def test_expired_grant_is_refused_before_any_request():
    server, clock = FakeServer(), Clock()
    grant = _grant(clock)
    clock.now = grant.expires_at + 1
    with pytest.raises(SessionDroppedError, match="expired"):
        _session(server, clock, grant=grant)
    assert not server.requests


def test_fetches_config_once_when_not_given():
    server, clock = FakeServer(), Clock()
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/system/config":
            calls.append(request)
            return httpx.Response(200, json={**CONFIG.__dict__, "bridged_tokens": []})
        return server.handler(request)

    grant = _grant(clock)
    session = SessionAccounts(
        env=TESTNET,
        grant=grant,
        session_private_key=SESSION_PRIVATE,
        grant_id=_grant_id(grant),
        http_client_factory=lambda: httpx.Client(transport=httpx.MockTransport(handler)),
        ws_enabled=False,
        clock=clock,
    )
    assert len(calls) == 1
    assert session.config.starknet_chain_id == CHAIN


# -- websockets ----------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_one_websocket_per_account_authenticated_as_that_account():
    server, clock, connector = FakeServer(), Clock(), FakeConnector()
    session = _session(server, clock, ws_enabled=True, ws_connector=connector)

    await session.connect_ws()

    assert len(connector.sockets) == 3
    for address, socket in zip(session.accounts, connector.sockets, strict=True):
        jwt = _jwt_account(session, address)
        assert socket.headers["Authorization"] == f"Bearer {jwt}"
        assert socket.sent[0]["method"] == "auth"
        assert socket.sent[0]["params"] == {"bearer": jwt}
        assert session.ws(address).ws is socket
    await session.close()


@pytest.mark.asyncio
async def test_drop_closes_every_socket_and_stops_reconnects():
    server, clock, connector = FakeServer(), Clock(), FakeConnector()
    session = _session(server, clock, ws_enabled=True, ws_connector=connector)
    await session.connect_ws()

    session.drop("revoked")
    await asyncio.gather(*session._close_tasks)

    assert all(socket.state == State.CLOSED for socket in connector.sockets)
    assert all(ws.disable_reconnect for ws in session._sockets.values())
    with pytest.raises(SessionDroppedError):
        session.ws(MAIN)
    await session.close()


@pytest.mark.asyncio
async def test_sockets_drop_at_session_expiry():
    server, clock, connector = FakeServer(), Clock(), FakeConnector()
    grant = _grant(clock)
    session = _session(server, clock, grant=grant, ws_enabled=True, ws_connector=connector)
    await session.connect_ws()

    clock.now = grant.expires_at - 0.05  # the watcher sleeps for what remains
    session._expiry_task.cancel()
    session._expiry_task = asyncio.get_running_loop().create_task(session._drop_at_expiry())
    await asyncio.sleep(0.2)

    assert session.dropped_reason == "session expired"
    await asyncio.gather(*session._close_tasks)
    assert all(socket.state == State.CLOSED for socket in connector.sockets)
    await session.close()


def test_connect_ws_after_a_closed_loop_restarts_the_expiry_timer():
    server, clock, connector = FakeServer(), Clock(), FakeConnector()
    grant = _grant(clock)
    session = _session(server, clock, grant=grant, ws_enabled=True, ws_connector=connector)
    first = asyncio.new_event_loop()
    first.run_until_complete(session.connect_ws())
    first.close()  # unlike asyncio.run, this leaves the expiry timer pending, never done
    assert not session._expiry_task.done()

    async def second_loop() -> None:
        clock.now = grant.expires_at - 0.05
        await session.connect_ws()
        await asyncio.sleep(0.2)
        assert session.dropped_reason == "session expired"
        await asyncio.gather(*session._close_tasks)
        await session.close()

    asyncio.run(second_loop())


def test_connect_ws_on_a_new_loop_restarts_the_expiry_timer():
    server, clock, connector = FakeServer(), Clock(), FakeConnector()
    grant = _grant(clock)
    session = _session(server, clock, grant=grant, ws_enabled=True, ws_connector=connector)
    asyncio.run(session.connect_ws())  # the loop ends, cancelling its expiry timer

    async def second_loop() -> None:
        clock.now = grant.expires_at - 0.05
        await session.connect_ws()
        await asyncio.sleep(0.2)
        assert session.dropped_reason == "session expired"
        await asyncio.gather(*session._close_tasks)
        await session.close()

    asyncio.run(second_loop())
    assert all(socket.state == State.CLOSED for socket in connector.sockets[3:])


@pytest.mark.asyncio
async def test_refused_websocket_login_with_a_revoked_grant_drops_without_reconnecting():
    server, clock, connector = FakeServer(), Clock(), FakeConnector()
    session = _session(server, clock, ws_enabled=True, ws_connector=connector)
    await session.connect_ws()
    server.revoked.add(SUB_1)
    server.grant_state = "revoked"

    await session._sockets[SUB_1]._reconnect_with_auth_refresh()
    await asyncio.sleep(0.05)  # the drop ran on the login thread, which hands the closes to the loop

    assert session.dropped_reason == f"grant {session.grant_id} is revoked"
    assert len(connector.sockets) == 3  # no new socket was opened
    assert all(socket.state == State.CLOSED for socket in connector.sockets)
    await session.close()


@pytest.mark.asyncio
async def test_refused_websocket_login_with_a_live_grant_reconnects():
    server, clock, connector = FakeServer(), Clock(), FakeConnector()
    session = _session(server, clock, ws_enabled=True, ws_connector=connector)
    await session.connect_ws()

    await session._sockets[SUB_1]._reconnect_with_auth_refresh()

    assert session.is_live
    assert len(connector.sockets) == 4
    assert connector.sockets[-1].sent[0]["params"] == {"bearer": _jwt_account(session, SUB_1)}
    await session.close()


@pytest.mark.asyncio
async def test_dropped_sockets_do_not_connect():
    server, clock, connector = FakeServer(), Clock(), FakeConnector()
    session = _session(server, clock, ws_enabled=True, ws_connector=connector)
    await session.connect_ws()
    session.drop("revoked")

    assert await session._sockets[MAIN].connect() is False
    await session._sockets[MAIN]._reconnect()
    assert len(connector.sockets) == 3
    await session.close()


@pytest.mark.asyncio
async def test_drop_from_another_thread_closes_sockets():
    server, clock, connector = FakeServer(), Clock(), FakeConnector()
    session = _session(server, clock, ws_enabled=True, ws_connector=connector)
    await session.connect_ws()

    await asyncio.to_thread(session.drop, "revoked")  # e.g. a REST call run in a worker thread
    await asyncio.sleep(0.05)

    assert all(socket.state == State.CLOSED for socket in connector.sockets)
    assert session._expiry_task.cancelled()
    await session.close()


@pytest.mark.asyncio
async def test_connect_ws_closes_connected_sockets_when_one_fails():
    connector = FakeConnector(fail_after=1)
    session = _session(FakeServer(), Clock(), ws_enabled=True, ws_connector=connector)
    with pytest.raises(ConnectionError, match="did not connect"):
        await session.connect_ws()
    assert connector.sockets[0].state == State.CLOSED
    assert session._expiry_task is not None
    await session.close()


@pytest.mark.asyncio
async def test_connect_ws_raises_when_a_socket_fails():
    session = _session(FakeServer(), Clock(), ws_enabled=True, ws_connector=FakeConnector(fail=True))
    with pytest.raises(ConnectionError, match="did not connect"):
        await session.connect_ws()
    await session.close()


def test_ws_disabled():
    session = _session(FakeServer(), Clock())
    with pytest.raises(ValueError, match="websockets are disabled"):
        session.ws(MAIN)


@pytest.mark.asyncio
async def test_async_context_manager_closes():
    server, clock, connector = FakeServer(), Clock(), FakeConnector()
    async with _session(server, clock, ws_enabled=True, ws_connector=connector) as session:
        await session.connect_ws()
        assert session.is_live
    assert session.dropped_reason == "closed"
    assert all(client.client.is_closed for client in session._clients.values())
    assert session._expiry_task.cancelled()
    assert all(socket.state == State.CLOSED for socket in connector.sockets)


# -- registration and the owner-signature hook ---------------------------------------------------


def test_register_session_signs_through_the_owner_hook():
    server, clock = FakeServer(), Clock()
    owner = EthAccount.create()
    signer = LocalOwnerSigner(owner.key.hex(), signature_chain_id=42161)
    grant = _grant(clock)

    result = register_session(TESTNET, grant, signer, http_client=HttpClient(http_client=server.client()))

    assert result["grant_id"] == REGISTERED_ID
    listing, request = server.requests
    assert (
        str(listing.url) == f"https://api.testnet.paradex.trade/v2/onboarding/subaccounts?eth_address={owner.address}"
    )
    assert str(request.url) == "https://api.testnet.paradex.trade/v2/sessions"
    assert "PARADEX-PRIVY-ACCESS-TOKEN" not in request.headers
    body = json.loads(request.content)
    assert body["grant"] == grant.to_message()
    assert body["signature_type"] == "eip712"
    assert body["signature_chain_id"] == 42161
    assert not {"referral_code", "marketing_code", "utm"} & body.keys()
    signable = encode_typed_data(full_message=grant.eip712_typed_data(42161))
    assert EthAccount.recover_message(signable, signature=body["signature"]) == owner.address


def test_register_session_with_an_external_signer():
    """An MPC or hardware signer only ever sees the typed data, never a key."""

    class ExternalSigner:
        signature_chain_id = 8453

        def __init__(self):
            self.seen = []

        def sign_typed_data(self, typed_data):
            self.seen.append(typed_data)
            return "0x" + "00" * 65

    server, clock = FakeServer(), Clock()
    signer = ExternalSigner()
    grant = _grant(clock)
    register_session(TESTNET, grant, signer, http_client=HttpClient(http_client=server.client()))

    (typed_data,) = signer.seen
    assert typed_data["domain"] == {"name": "Paradex Session", "version": "1", "chainId": 8453}
    assert typed_data["primaryType"] == "SessionGrant"


def test_register_session_refuses_a_mismatched_environment():
    server, clock = FakeServer(), Clock()
    signer = LocalOwnerSigner(EthAccount.create().key.hex())
    with pytest.raises(ValueError, match="environment"):
        register_session("prod", _grant(clock), signer, http_client=HttpClient(http_client=server.client()))
    assert not server.requests


def test_register_session_surfaces_server_refusal():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": "INVALID_GRANT", "message": "bad", "data": None})

    signer = LocalOwnerSigner(EthAccount.create().key.hex())
    client = HttpClient(http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    with pytest.raises(ValueError, match="INVALID_GRANT"):
        register_session(TESTNET, _grant(Clock(), subaccounts=[]), signer, http_client=client)


class _CountingSigner:
    """An external signer with no address, returning a canned signature."""

    signature_chain_id = 1

    def __init__(self, signature: str = "0x" + "00" * 65):
        self.signature = signature
        self.calls = 0

    def sign_typed_data(self, typed_data):
        self.calls += 1
        return self.signature


def test_register_session_sends_the_new_account_fields():
    """A first grant that opens an account carries the onboarding fields and the Privy header, unsigned."""
    server, clock = FakeServer(), Clock()
    grant = _grant(clock, subaccounts=[])
    register_session(
        TESTNET,
        grant,
        _CountingSigner(),
        http_client=HttpClient(http_client=server.client()),
        referral_code="cryptofox8",
        marketing_code="abcd:code1",
        utm={"source": "google", "campaign": "launch"},
        privy_access_token="privy-token",  # noqa: S106
    )

    (request,) = server.requests
    assert request.headers["PARADEX-PRIVY-ACCESS-TOKEN"] == "privy-token"
    body = json.loads(request.content)
    assert body["referral_code"] == "cryptofox8"
    assert body["marketing_code"] == "abcd:code1"
    assert body["utm"] == {"source": "google", "campaign": "launch"}
    assert body["grant"] == grant.to_message()  # none of them is part of what the owner signs


def test_register_session_refuses_a_contract_wallet_signature():
    server, clock = FakeServer(), Clock()
    signer = _CountingSigner("0x" + "11" * 66)
    with pytest.raises(ValueError, match="contract wallets"):
        register_session(
            TESTNET, _grant(clock, subaccounts=[]), signer, http_client=HttpClient(http_client=server.client())
        )
    assert not server.by_path("/v2/sessions")


def test_register_session_refuses_unlisted_subaccounts_before_signing():
    """The server answers ACCOUNT_NOT_ELIGIBLE for a sub-account that is not the wallet's own EVM child."""
    server, clock = FakeServer(), Clock()
    server.owned_subaccounts = [SUB_1]
    signer = _CountingSigner()
    with pytest.raises(ValueError, match="0xb2"):
        register_session(
            TESTNET,
            _grant(clock),
            signer,
            http_client=HttpClient(http_client=server.client()),
            owner_address="0x" + "aa" * 20,
        )
    assert signer.calls == 0
    assert not server.by_path("/v2/sessions")


def test_register_session_accepts_listed_subaccounts_in_any_hex_form():
    server, clock = FakeServer(), Clock()
    server.owned_subaccounts = ["0x00b1", "0xB2"]
    register_session(
        TESTNET,
        _grant(clock),
        _CountingSigner(),
        http_client=HttpClient(http_client=server.client()),
        owner_address="0xa",
    )
    assert len(server.by_path("/v2/sessions")) == 1


@pytest.mark.parametrize("kwargs", [{}, {"owner_address": "0xa", "check_subaccounts": False}])
def test_register_session_skips_the_subaccount_check(kwargs):
    """Without the owner's address (an external signer), or when turned off, nothing is listed."""
    server, clock = FakeServer(), Clock()
    server.owned_subaccounts = []
    register_session(
        TESTNET, _grant(clock), _CountingSigner(), http_client=HttpClient(http_client=server.client()), **kwargs
    )
    assert not server.by_path("/v2/onboarding/subaccounts")
    assert len(server.by_path("/v2/sessions")) == 1


def test_new_session_key_is_a_matching_pair():
    from starknet_py.net.signer.key_pair import KeyPair

    private, public = new_session_key()
    assert hex(KeyPair.from_private_key(int(private, 16)).public_key) == public
    assert new_session_key()[0] != private


@pytest.mark.parametrize(
    ("params", "payload"),
    [
        ({"on_behalf_of_account": SUB_1}, None),
        (None, {"market": "BTC-USD-PERP", "on_behalf_of_account": SUB_1}),
        (None, [{"market": "BTC-USD-PERP"}, {"on_behalf_of": SUB_1}]),
    ],
)
def test_raw_client_refuses_on_behalf_of(params, payload):
    server = FakeServer()
    session = _session(server, Clock())
    with pytest.raises(ValueError, match="on_behalf_of"):
        session.api(MAIN)._post_authorized(path="orders", payload=payload, params=params)
    assert not server.by_path("/v1/orders")


def test_revoke_keeps_the_session_when_the_server_does_not_confirm():
    server, clock = FakeServer(), Clock()
    session = _session(server, clock)
    server.delete_status = 500

    with pytest.raises(SessionRevokeError) as excinfo:
        session.revoke()

    assert excinfo.value.status_code == 500
    assert session.is_live
    server.delete_status = 204
    session.revoke()  # the call can be retried
    assert not session.is_live


def test_revoke_of_a_grant_the_server_no_longer_has_drops():
    server, clock = FakeServer(), Clock()
    session = _session(server, clock)
    server.delete_status = 404
    session.revoke()
    assert session.dropped_reason == "revoked by this session"


@pytest.mark.asyncio
async def test_refused_websocket_login_with_an_active_grant_keeps_the_session_and_reconnects():
    server, clock, connector = FakeServer(), Clock(), FakeConnector()
    session = _session(server, clock, ws_enabled=True, ws_connector=connector)
    await session.connect_ws()
    server.revoked.add(SUB_1)  # the login is refused, but the grant is still active

    await session._sockets[SUB_1]._reconnect_with_auth_refresh()

    assert session.is_live
    assert server.auth_counts[SUB_1] == 1 + 3  # the first login, then three refused attempts
    assert len(_status_checks(server, session)) == 3
    assert len(connector.sockets) == 4  # it still reconnected
    await session.close()


@pytest.mark.asyncio
async def test_reconnect_with_an_expired_jwt_logs_in_again_first():
    server, clock, connector = FakeServer(), Clock(), FakeConnector()
    session = _session(server, clock, ws_enabled=True, ws_connector=connector)
    await session.connect_ws()
    ws = session._sockets[MAIN]
    ws.account.set_jwt_token(_jwt(MAIN, time.time() - 1))

    await ws._reconnect()

    assert server.auth_counts[MAIN] == 2
    assert connector.sockets[-1].sent[0]["params"]["bearer"] == _jwt_account(session, MAIN)
    await session.close()


@pytest.mark.asyncio
async def test_failed_construction_stops_websocket_readers():
    server, clock = FakeServer(), Clock()
    server.revoked.add(SUB_1)
    server.grant_state = "revoked"

    with pytest.raises(SessionDroppedError):
        _session(server, clock, ws_enabled=True, ws_connector=FakeConnector())
    await asyncio.sleep(0)

    readers = [t for t in asyncio.all_tasks() if "_read_messages" in repr(t.get_coro())]
    assert all(t.cancelled() or t.done() for t in readers)


def test_a_404_page_is_not_an_unknown_grant():
    server, clock = FakeServer(), Clock()
    session = _session(server, clock)
    server.revoked.add(SUB_2)
    server.status_code = 404
    server.unknown_route = True  # e.g. the status route is missing, not the grant
    session.api(SUB_2)._token_exp = 0

    with pytest.raises(SessionRejectedError):
        session.submit_order(SUB_2, _order())
    assert session.is_live


def test_revoke_does_not_drop_on_a_404_page():
    server, clock = FakeServer(), Clock()
    session = _session(server, clock)
    server.delete_status = 404
    server.unknown_route = True

    with pytest.raises(SessionRevokeError) as excinfo:
        session.revoke()
    assert excinfo.value.status_code == 404
    assert session.is_live


@pytest.mark.asyncio
async def test_refused_reconnect_login_never_logs_in_on_the_loop():
    server, clock, connector = FakeServer(), Clock(), FakeConnector()
    session = _session(server, clock, ws_enabled=True, ws_connector=connector)
    await session.connect_ws()
    ws = session._sockets[MAIN]
    ws.account.set_jwt_token(_jwt(MAIN, time.time() - 1))
    server.revoked.add(MAIN)  # the login is refused, but the grant is still active

    await ws._reconnect()

    # Only the threaded attempts: the reconnect itself does not log in again with blocking sleeps.
    assert server.auth_counts[MAIN] == 1 + 3
    assert len(connector.sockets) == 4
    await session.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["network", "rate-limited"])
async def test_a_failed_relogin_still_reconnects(failure):
    server, clock, connector = FakeServer(), Clock(), FakeConnector()
    session = _session(server, clock, ws_enabled=True, ws_connector=connector)
    await session.connect_ws()
    ws = session._sockets[MAIN]
    ws.account.set_jwt_token(_jwt(MAIN, time.time() - 1))
    server.auth_failure = failure

    await ws._reconnect()
    await ws._reconnect_with_auth_refresh()

    assert session.is_live
    assert len(connector.sockets) == 3 + 2  # both paths reconnected
    await session.close()


@pytest.mark.asyncio
async def test_relogin_runs_off_the_event_loop_thread():
    server, clock, connector = FakeServer(), Clock(), FakeConnector()
    session = _session(server, clock, ws_enabled=True, ws_connector=connector)
    await session.connect_ws()
    ws = session._sockets[MAIN]
    ws.account.set_jwt_token(_jwt(MAIN, time.time() - 1))
    server.auth_threads.clear()

    await ws._reconnect()

    assert server.auth_threads
    assert threading.get_ident() not in server.auth_threads
    await session.close()


def test_revoke_refused_for_a_grant_revoked_elsewhere_drops():
    server, clock = FakeServer(), Clock()
    session = _session(server, clock)
    server.delete_status = 401
    server.grant_state = "revoked"  # e.g. the owner revoked it from another device

    with pytest.raises(SessionDroppedError, match="revoked"):
        session.revoke()
    assert not session.is_live


def test_revoke_refused_with_an_active_grant_stays_live():
    server, clock = FakeServer(), Clock()
    session = _session(server, clock)
    server.delete_status = 401

    with pytest.raises(SessionRevokeError):
        session.revoke()
    assert session.is_live


@pytest.mark.asyncio
async def test_connect_ws_refreshes_a_stale_jwt_before_connecting():
    server, clock, connector = FakeServer(), Clock(), FakeConnector()
    session = _session(server, clock, ws_enabled=True, ws_connector=connector)
    session.api(MAIN)._token_exp = 0

    await session.connect_ws()

    assert server.auth_counts[MAIN] == 2
    assert connector.sockets[0].sent[0]["params"]["bearer"] == _jwt_account(session, MAIN)
    await session.close()


@pytest.mark.asyncio
async def test_a_drop_during_connect_closes_the_new_socket():
    server, clock = FakeServer(), Clock()

    class DroppingConnector(FakeConnector):
        async def __call__(self, url, headers):
            socket = await super().__call__(url, headers)
            session.drop("revoked")
            return socket

    connector = DroppingConnector()
    session = _session(server, clock, ws_enabled=True, ws_connector=connector)

    assert await session._sockets[MAIN].connect() is False
    assert connector.sockets[0].state == State.CLOSED
    await session.close()


def test_client_options_reach_every_account():
    from paradex_py.api.protocols import DefaultRetryStrategy

    server, clock = FakeServer(), Clock()
    strategy = DefaultRetryStrategy(max_retries=1)
    session = _session(server, clock, api_base_url="https://api.example.test/v1", retry_strategy=strategy)

    assert {r.url.host for r in server.by_path("/v1/auth/")} == {"api.example.test"}
    assert all(client.retry_strategy is strategy for client in session._clients.values())


@pytest.mark.parametrize("status", [404, 429, 503])
def test_register_session_registers_when_the_listing_fails(status):
    """The server re-checks sub-accounts, so an unreadable listing must not block the registration."""
    server, clock = FakeServer(), Clock()
    server.listing_status = status
    register_session(
        TESTNET,
        _grant(clock),
        _CountingSigner(),
        http_client=HttpClient(http_client=server.client()),
        owner_address="0xa",
    )
    assert len(server.by_path("/v2/sessions")) == 1


@pytest.mark.parametrize(
    ("kwargs", "error"),
    [
        ({"marketing_code": "abcd"}, "campaign:code"),
        ({"marketing_code": "abcd:"}, "campaign:code"),
        ({"marketing_code": "a:b:c"}, "campaign:code"),
        ({"utm": {"source": "google"}}, "source and campaign"),
    ],
)
def test_register_session_refuses_bad_onboarding_fields_before_signing(kwargs, error):
    server, clock = FakeServer(), Clock()
    signer = _CountingSigner()
    with pytest.raises(ValueError, match=error):
        register_session(
            TESTNET,
            _grant(clock, subaccounts=[]),
            signer,
            http_client=HttpClient(http_client=server.client()),
            **kwargs,
        )
    assert signer.calls == 0
    assert not server.requests


def test_register_session_redacts_the_privy_token_from_request_hooks():
    seen = []

    class Hook:
        def on_request(self, method, url, headers):
            seen.append(headers)

        def on_response(self, *args):
            pass

    server, clock = FakeServer(), Clock()
    client = HttpClient(http_client=server.client(), request_hook=Hook())
    register_session(
        TESTNET,
        _grant(clock, subaccounts=[]),
        _CountingSigner(),
        http_client=client,
        privy_access_token="privy-token",  # noqa: S106
    )
    assert seen[-1]["PARADEX-PRIVY-ACCESS-TOKEN"] == "[REDACTED]"
    assert server.requests[-1].headers["PARADEX-PRIVY-ACCESS-TOKEN"] == "privy-token"


@pytest.mark.parametrize("body", [{}, {"results": None}, []])
def test_register_session_registers_when_the_listing_is_unreadable(body):
    server, clock = FakeServer(), Clock()
    server.listing_body = body
    register_session(
        TESTNET,
        _grant(clock),
        _CountingSigner(),
        http_client=HttpClient(http_client=server.client()),
        owner_address="0xa",
    )
    assert len(server.by_path("/v2/sessions")) == 1


def test_register_session_ignores_malformed_listing_entries():
    """A listed entry without a hex address covers nothing, so the sub-account is still refused."""
    server, clock = FakeServer(), Clock()
    server.listing_body = {"results": [{"address": SUB_1}, {"address": "not-hex"}, {"index": 3}, "0xb2"]}
    signer = _CountingSigner()
    with pytest.raises(ValueError, match="0xb2"):
        register_session(
            TESTNET, _grant(clock), signer, http_client=HttpClient(http_client=server.client()), owner_address="0xa"
        )
    assert signer.calls == 0
