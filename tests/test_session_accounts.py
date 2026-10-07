"""Tests for SessionAccounts: one session key, a JWT, REST client and websocket per granted account."""

import asyncio
import base64
import json
import time
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
    new_session_key,
    register_session,
)

CHAIN = "PRIVATE_SN_PARACLEAR_TESTNET"
CHAIN_ID = int_from_bytes(CHAIN.encode())
MAIN = "0xa1"
SUB_1 = "0xb1"
SUB_2 = "0xb2"
SESSION_PRIVATE, SESSION_PUBLIC = new_session_key()
GRANT_ID = "g-1"
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
        self.refuse_orders_with: int | None = None
        self.auth_counts: dict[str, int] = {}
        self.grant_status = "active"
        self.refuse_status = False

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path
        if path.startswith("/v1/auth/"):
            account = request.headers["PARADEX-STARKNET-ACCOUNT"]
            self.auth_counts[account] = self.auth_counts.get(account, 0) + 1
            if account in self.revoked:
                return httpx.Response(401, json={"error": "INVALID_SUBKEY", "message": "subkey revoked", "data": None})
            return httpx.Response(200, json={"jwt_token": _jwt(account, time.time() + SESSION_AUTH_MAX_SECONDS)})
        if path in ("/v1/orders", "/v1/orders/batch"):
            if self.refuse_orders_with:
                return httpx.Response(
                    self.refuse_orders_with, json={"error": "FORBIDDEN", "message": "no", "data": None}
                )
            return httpx.Response(201, json={"id": "order-1"})
        if path == "/v2/sessions":
            return httpx.Response(201, json={"grant_id": GRANT_ID, "expires_at": 1, "accounts": [MAIN]})
        if path == f"/v2/sessions/{GRANT_ID}" and request.method == "GET":
            if self.refuse_status:
                return httpx.Response(401, json={"error": "UNAUTHORIZED", "message": "no", "data": None})
            return httpx.Response(200, json={"grant_id": GRANT_ID, "status": self.grant_status})
        if path == f"/v2/sessions/{GRANT_ID}" and request.method == "DELETE":
            self.grant_status = "revoked"
            return httpx.Response(204)
        return httpx.Response(204)

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
        await asyncio.sleep(3600)
        return ""

    async def close(self) -> None:
        self.state = State.CLOSED


class FakeConnector:
    def __init__(self, fail: bool = False):
        self.sockets: list[FakeSocket] = []
        self.fail = fail

    async def __call__(self, url: str, headers: dict[str, str]) -> FakeSocket:
        if self.fail:
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


def _session(server: FakeServer, clock: Clock, grant: SessionGrant | None = None, **kwargs) -> SessionAccounts:
    kwargs.setdefault("ws_enabled", False)
    kwargs.setdefault("grant_id", GRANT_ID)
    return SessionAccounts(
        env=TESTNET,
        grant=grant or _grant(clock),
        session_private_key=SESSION_PRIVATE,
        config=CONFIG,
        http_client_factory=server.client,
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
    assert not server.by_path("/v2/sessions")  # a refused action is not a revocation signal


def test_refused_login_with_an_active_grant_keeps_the_session():
    server, clock = FakeServer(), Clock()
    session = _session(server, clock)
    server.revoked.add(SUB_1)  # e.g. a transient refusal; the grant itself is still active
    session.api(SUB_1)._token_exp = 0

    with pytest.raises(SessionRejectedError):
        session.submit_order(SUB_1, _order())

    assert session.is_live
    assert len(server.by_path(f"/v2/sessions/{GRANT_ID}")) == 1  # checked once, no polling
    server.revoked.clear()
    session.submit_order(SUB_1, _order())  # the caller can retry


def test_401_on_a_call_with_a_revoked_grant_drops_everything():
    server, clock = FakeServer(), Clock()
    session = _session(server, clock)
    server.refuse_orders_with = 401
    server.grant_status = "revoked"

    with pytest.raises(SessionDroppedError, match="revoked"):
        session.submit_order(MAIN, _order())
    assert not session.is_live


def test_refused_status_check_drops_everything():
    server, clock = FakeServer(), Clock()
    session = _session(server, clock)
    server.refuse_orders_with = 401
    server.refuse_status = True

    with pytest.raises(SessionDroppedError, match="refused"):
        session.submit_order(MAIN, _order())
    assert not session.is_live


def test_revoke_deletes_the_grant_and_drops_everything():
    server, clock = FakeServer(), Clock()
    reasons = []
    session = _session(server, clock, on_dropped=reasons.append)
    jwt = _jwt_account(session, MAIN)

    session.revoke()

    (request,) = [r for r in server.requests if r.method == "DELETE"]
    assert request.url.path == f"/v2/sessions/{GRANT_ID}"
    assert request.headers["Authorization"] == f"Bearer {jwt}"
    assert reasons == ["revoked by this session"]
    assert not session.is_live


# -- dropping ------------------------------------------------------------------------------------


def test_revoked_at_start_drops_everything():
    server, clock = FakeServer(), Clock()
    server.revoked.add(SUB_1)
    server.grant_status = "revoked"
    reasons = []

    with pytest.raises(SessionDroppedError, match="g-1 is revoked"):
        _session(server, clock, on_dropped=reasons.append)

    assert len(reasons) == 1
    assert SUB_2 not in server.auth_counts  # no further account is authenticated


def test_revoked_at_refresh_drops_every_account():
    server, clock = FakeServer(), Clock()
    reasons = []
    session = _session(server, clock, on_dropped=reasons.append)
    server.revoked.add(SUB_2)
    server.grant_status = "expired"
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
        ({"environment": "nightly"}, {}, "not the 'testnet' environment"),
        ({"paradex_chain": "PRIVATE_SN_PARACLEAR_MAINNET"}, {}, "grant is for chain"),
        ({}, {"auth_params": {"token_usage": "interactive"}}, "set by the server"),
        ({}, {"grant_id": ""}, "grant_id is required"),
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

    session = SessionAccounts(
        env=TESTNET,
        grant=_grant(clock),
        session_private_key=SESSION_PRIVATE,
        grant_id=GRANT_ID,
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
    server, clock = FakeServer(), Clock()
    async with _session(server, clock) as session:
        assert session.is_live
    assert session.dropped_reason == "closed"


# -- registration and the owner-signature hook ---------------------------------------------------


def test_register_session_signs_through_the_owner_hook():
    server, clock = FakeServer(), Clock()
    owner = EthAccount.create()
    signer = LocalOwnerSigner(owner.key.hex(), signature_chain_id=42161)
    grant = _grant(clock)

    result = register_session(TESTNET, grant, signer, http_client=HttpClient(http_client=server.client()))

    assert result["grant_id"] == GRANT_ID
    (request,) = server.requests
    assert str(request.url) == "https://api.testnet.paradex.trade/v2/sessions"
    body = json.loads(request.content)
    assert body["grant"] == grant.to_message()
    assert body["signature_type"] == "eip712"
    assert body["signature_chain_id"] == 42161
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
        register_session(TESTNET, _grant(Clock()), signer, http_client=client)


def test_new_session_key_is_a_matching_pair():
    from starknet_py.net.signer.key_pair import KeyPair

    private, public = new_session_key()
    assert hex(KeyPair.from_private_key(int(private, 16)).public_key) == public
    assert new_session_key()[0] != private
