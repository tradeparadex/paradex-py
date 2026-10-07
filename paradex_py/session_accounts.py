"""Trade several accounts from one session key and its owner-signed grant.

.. warning::
    Experimental. Session keys are being rolled out on the server, and ``POST /v2/sessions``
    is coded to the published design, not to a live endpoint. Names and payloads may change.

A ``SessionGrant`` names an anchor account and, optionally, sub-accounts. The server keeps
one session row per listed account, so the session key authenticates to each one on its own:
``SessionAccounts`` mints and refreshes a JWT per account (``/auth`` with
``PARADEX-STARKNET-ACCOUNT`` set to that account, signed by the session key, at most 15
minutes and never past the session's expiry), keeps one REST client and one websocket per
account, and routes every call by account. Sessions never use ``on_behalf_of``.

Revocation is detected without polling. When ``/auth`` refuses the session key, or any call
returns 401, ``SessionAccounts`` asks ``GET /v2/sessions/{grant_id}`` once. If the grant is
``revoked`` or ``expired`` (or the status check is refused too), every account is dropped
together: JWTs are cleared, sockets closed, and further calls raise :class:`SessionDroppedError`.
Any other answer leaves the session live and surfaces the original error, so the caller can retry.
The session also drops itself at the grant's ``expiresAt``.
"""

from __future__ import annotations

import asyncio
import logging
import secrets
import time
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

import httpx
from eth_account import Account as EthAccount
from eth_account.messages import encode_typed_data
from starknet_py.constants import EC_ORDER
from starknet_py.net.signer.key_pair import KeyPair

from paradex_py.account.subkey_account import SubkeyAccount
from paradex_py.api.api_client import ParadexApiClient
from paradex_py.api.http_client import HttpClient, HttpMethod
from paradex_py.api.ws_client import ParadexWebsocketClient
from paradex_py.environment import Environment, _validate_env
from paradex_py.message.session import SessionGrant, grant_environment
from paradex_py.utils import raise_value_error

if TYPE_CHECKING:
    from paradex_py.api.models import SystemConfig
    from paradex_py.api.protocols import OwnerSigner, WebSocketConnector
    from paradex_py.common.order import Order

__all__ = [
    "LocalOwnerSigner",
    "SessionAccounts",
    "SessionDroppedError",
    "SessionRejectedError",
    "SessionWebsocketError",
    "new_session_key",
    "register_session",
]

# A session's /auth signature, and so its JWT, lives at most this long.
SESSION_AUTH_MAX_SECONDS = 15 * 60
# Grant statuses after which the session is gone for good.
_DEAD_STATUSES = frozenset({"revoked", "expired"})
# Query parameters a session must not set itself: token usage is decided by the server.
_FORBIDDEN_AUTH_PARAMS = frozenset({"token_usage"})
_FORBIDDEN_ORDER_FIELDS = frozenset({"on_behalf_of_account", "on_behalf_of"})


class SessionDroppedError(RuntimeError):
    """Raised when a call is made after the session was dropped (expired, revoked or closed)."""


class SessionRejectedError(ValueError):
    """The server refused the session key (HTTP 401 or 403)."""

    def __init__(self, status_code: int, body: str):
        super().__init__(f"HTTP {status_code}: {body[:200]}")
        self.status_code = status_code


class SessionWebsocketError(ConnectionError):
    """A session account's websocket did not connect."""

    def __init__(self, account: str):
        super().__init__(f"SessionAccounts: websocket for {account} did not connect")
        self.account = account


def new_session_key() -> tuple[str, str]:
    """Generate a fresh Stark session key; returns ``(private_key, public_key)`` as ``0x`` hex."""
    private_key = secrets.randbelow(EC_ORDER - 1) + 1
    return hex(private_key), hex(KeyPair.from_private_key(private_key).public_key)


class LocalOwnerSigner:
    """An :class:`~paradex_py.api.protocols.OwnerSigner` holding the owner's EVM key in process.

    Args:
        eth_private_key: The owner wallet's private key.
        signature_chain_id: The EVM chain to sign on. Defaults to Ethereum mainnet (1).
    """

    def __init__(self, eth_private_key: str, signature_chain_id: int = 1):
        self._eth_private_key = eth_private_key
        self._signature_chain_id = signature_chain_id
        self.address = EthAccount.from_key(eth_private_key).address

    @property
    def signature_chain_id(self) -> int:
        return self._signature_chain_id

    def sign_typed_data(self, typed_data: dict[str, Any]) -> str:
        signable = encode_typed_data(full_message=typed_data)
        signature = EthAccount.sign_message(signable, self._eth_private_key).signature.hex()
        return signature if signature.startswith("0x") else "0x" + signature


def register_session(
    env: Environment,
    grant: SessionGrant,
    owner_signer: OwnerSigner,
    http_client: HttpClient | None = None,
    api_base_url: str | None = None,
) -> dict:
    """Have the owner sign ``grant`` and register it with ``POST /v2/sessions``.

    .. warning::
        Experimental: the endpoint is coded to the published design and is not live yet.

    Args:
        env: Environment.
        grant: The grant to register. Its ``environment`` must match ``env``.
        owner_signer: Signs the EIP-712 grant; the owner's key never reaches the SDK.
        http_client: Optional HTTP client.
        api_base_url: Optional ``/v1`` base URL override; ``/v2`` is derived from it.

    Returns:
        The server's response: ``grant_id``, ``expires_at`` (milliseconds) and the ``accounts`` covered.
        Pass ``grant_id`` to :class:`SessionAccounts`.
    """
    _validate_env(env, "register_session")
    _check_grant_environment(env, grant)
    chain_id = owner_signer.signature_chain_id
    typed_data = grant.eip712_typed_data(chain_id)
    signature = owner_signer.sign_typed_data(typed_data)
    client = http_client or HttpClient()
    base = api_base_url or f"https://api.{env}.paradex.trade/v1"
    return client.request(
        url=f"{base.replace('/v1', '/v2')}/sessions",
        http_method=HttpMethod.POST,
        payload={
            "grant": typed_data["message"],
            "signature": signature,
            "signature_type": "eip712",
            "signature_chain_id": chain_id,
        },
        headers=client.client.headers,
    )


def _check_grant_environment(env: Environment, grant: SessionGrant) -> None:
    if grant.environment != grant_environment(env):
        raise_value_error(f"grant is for {grant.environment!r}, not the {env!r} environment")


class _SessionKeyAccount(SubkeyAccount):
    """A session key acting for one listed account; ``/auth`` expiry is capped for sessions."""

    def __init__(self, owner: SessionAccounts, config: SystemConfig, session_private_key: str, address: str):
        self._owner = owner
        super().__init__(config=config, l2_private_key=session_private_key, l2_address=address)

    def auth_headers(self) -> dict:
        self._owner._ensure_live()
        timestamp = int(self._owner._clock())
        expiry = min(timestamp + SESSION_AUTH_MAX_SECONDS, self._owner.grant.expires_at)
        return {
            "PARADEX-STARKNET-ACCOUNT": hex(self.l2_address),
            "PARADEX-STARKNET-SIGNATURE": self.auth_signature(timestamp, expiry),
            "PARADEX-TIMESTAMP": str(timestamp),
            "PARADEX-SIGNATURE-EXPIRATION": str(expiry),
        }


class _SessionApiClient(ParadexApiClient):
    """REST client for one account of a session: refuses calls once the session is dropped."""

    classname = "SessionApiClient"

    def __init__(self, owner: SessionAccounts, **kwargs: Any):
        self._owner = owner
        super().__init__(**kwargs)

    def _handle_response(self, res: httpx.Response, url: str, http_method: HttpMethod) -> Any:
        if res.status_code in (401, 403):
            raise SessionRejectedError(res.status_code, res.text)
        return super()._handle_response(res, url, http_method)

    def request(self, url: str, http_method: HttpMethod, *args: Any, **kwargs: Any):
        try:
            return super().request(url, http_method, *args, **kwargs)
        except SessionRejectedError as e:
            # A refused login, or a 401 anywhere, may mean the grant was revoked. A 403 on any other
            # call is a refused action (e.g. a scope the grant lacks) and leaves the session alone.
            if e.status_code == 401 or "/auth/" in url:
                self._owner._check_grant(self, e)
            raise

    def auth(self, params: dict | None = None):
        self._owner._ensure_live()
        super().auth(params=params)

    def fetch_grant_status(self) -> str | None:
        """``GET /v2/sessions/{grant_id}``: ``active``, ``revoked`` or ``expired``."""
        res = super().request(
            url=f"{self._v2_api_url}/sessions/{self._owner.grant_id}",
            http_method=HttpMethod.GET,
            headers=self.client.headers,
        )
        return res.get("status") if isinstance(res, dict) else None

    def _validate_auth(self):
        self._owner._ensure_live()
        super()._validate_auth()


class SessionAccounts:
    """One session key, its grant, and a JWT, REST client and websocket per listed account.

    .. warning::
        Experimental; see the module docstring.

    Args:
        env: Environment.
        grant: The owner-signed grant (already registered with the server).
        session_private_key: The session's Stark private key; its public key must be ``grant.session_key``.
        grant_id: The id ``register_session`` returned; used to check and revoke the grant.
        config: Pre-fetched system configuration; fetched once if omitted.
        logger: Logger.
        auth_params: Extra ``/auth`` query parameters. ``token_usage`` is refused: the server decides it.
        http_client_factory: Builds the HTTP client for each account (each holds its own JWT header).
        ws_enabled: Whether to create a websocket client per account.
        ws_connector: Optional websocket connector, passed to every websocket client.
        on_dropped: Called once with the reason when the session is dropped.
        clock: Time source in seconds, for tests.

    Examples:
        >>> grant_id = register_session(TESTNET, grant, owner_signer)["grant_id"]
        >>> session = SessionAccounts(env=TESTNET, grant=grant, session_private_key=key, grant_id=grant_id)
        >>> session.submit_order(sub_account, order)          # routed to that account's JWT
        >>> await session.connect_ws()                        # one socket per account
        >>> await session.ws(sub_account).subscribe(...)
    """

    def __init__(
        self,
        env: Environment,
        grant: SessionGrant,
        session_private_key: str,
        grant_id: str,
        *,
        config: SystemConfig | None = None,
        logger: logging.Logger | None = None,
        auth_params: dict | None = None,
        http_client_factory: Callable[[], httpx.Client] | None = None,
        ws_enabled: bool = True,
        ws_connector: WebSocketConnector | None = None,
        on_dropped: Callable[[str], None] | None = None,
        clock: Callable[[], float] = time.time,
    ):
        _validate_env(env, "SessionAccounts")
        _check_grant_environment(env, grant)
        if auth_params and _FORBIDDEN_AUTH_PARAMS.intersection(auth_params):
            raise_value_error(f"SessionAccounts: {sorted(_FORBIDDEN_AUTH_PARAMS)} is set by the server, not the client")
        if not grant_id:
            raise_value_error("SessionAccounts: grant_id is required")
        self.accounts: list[str] = grant.accounts  # validates the grant
        public_key = KeyPair.from_private_key(int(session_private_key, 16)).public_key
        if public_key != int(grant.session_key, 16):
            raise_value_error("SessionAccounts: session_private_key does not match grant.session_key")

        self.env = env
        self.grant = grant
        self.grant_id = grant_id
        self.logger = logger or logging.getLogger(__name__)
        self._clock = clock
        self._on_dropped = on_dropped
        self.dropped_reason: str | None = None
        self._expiry_task: asyncio.Task | None = None
        self._close_tasks: list[asyncio.Task] = []

        self._clients: dict[str, _SessionApiClient] = {}
        self._sockets: dict[str, ParadexWebsocketClient] = {}
        for address in self.accounts:
            self._clients[address] = _SessionApiClient(
                owner=self,
                env=env,
                logger=logger,
                http_client=http_client_factory() if http_client_factory else None,
                auth_params=auth_params,
            )
        self._ensure_live()
        if config is None:
            config = self._clients[self.accounts[0]].fetch_system_config()
        if config.starknet_chain_id != grant.paradex_chain:
            raise_value_error(
                f"SessionAccounts: grant is for chain {grant.paradex_chain!r}, "
                f"the server is {config.starknet_chain_id!r}"
            )
        self.config = config

        for address in self.accounts:
            account = _SessionKeyAccount(self, config, session_private_key, address)
            client = self._clients[address]
            if ws_enabled:
                ws = ParadexWebsocketClient(env=env, logger=logger, api_client=client, connector=ws_connector)
                ws.init_account(account)
                self._sockets[address] = ws
            client.init_account(account)  # mints the account's first JWT

    # -- lifecycle -----------------------------------------------------------------------------

    @property
    def is_live(self) -> bool:
        """Whether the session is neither dropped nor past its expiry."""
        return self.dropped_reason is None and self._clock() < self.grant.expires_at

    def _ensure_live(self) -> None:
        if self.dropped_reason is None and self._clock() >= self.grant.expires_at:
            self.drop("session expired")
        if self.dropped_reason is not None:
            raise SessionDroppedError(self.dropped_reason)

    def _check_grant(self, client: _SessionApiClient, error: SessionRejectedError) -> None:
        """After the server refused the session, drop every account if the grant is gone."""
        if self.dropped_reason is not None:
            raise SessionDroppedError(self.dropped_reason) from error
        try:
            status = client.fetch_grant_status()
        except SessionRejectedError:
            status = "refused"  # the server refuses even the grant's status to this key
        if status in _DEAD_STATUSES or status == "refused":
            self.drop(f"grant {self.grant_id} is {status} ({error})")
            raise SessionDroppedError(self.dropped_reason) from error
        self.logger.warning(f"SessionAccounts: refused ({error}) but grant {self.grant_id} is {status!r}; not dropping")

    def revoke(self) -> None:
        """Revoke the grant on the server (``DELETE /v2/sessions/{grant_id}``), then drop every account."""
        client = self._clients[self.accounts[0]]
        client._validate_auth()
        try:
            client.delete(api_url=client._v2_api_url, path=f"sessions/{self.grant_id}")
        finally:
            self.drop("revoked by this session")

    def drop(self, reason: str) -> None:
        """Drop every account at once: clear JWTs, close sockets, refuse further calls. Idempotent."""
        if self.dropped_reason is not None:
            return
        self.dropped_reason = reason
        self.logger.warning(f"SessionAccounts: dropping {len(self.accounts)} account(s): {reason}")
        for client in self._clients.values():
            client.client.headers.pop("Authorization", None)
            client._token_exp = 0
            if client.account is not None:
                client.account.set_jwt_token("")
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        for ws in self._sockets.values():
            # The socket's reconnect path carries on after a failed refresh; a dropped session must not.
            ws.disable_reconnect = True
            if loop is not None:
                self._close_tasks.append(loop.create_task(ws.close()))
        if self._expiry_task is not None and loop is not None and self._expiry_task is not asyncio.current_task(loop):
            self._expiry_task.cancel()
        if self._on_dropped is not None:
            self._on_dropped(reason)

    async def close(self) -> None:
        """Drop the session (if live) and release every connection."""
        self.drop("closed")
        if self._close_tasks:
            await asyncio.gather(*self._close_tasks, return_exceptions=True)
        for ws in self._sockets.values():
            await ws.close()
        for client in self._clients.values():
            client.client.close()

    async def __aenter__(self) -> SessionAccounts:
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> bool:
        await self.close()
        return False

    async def _drop_at_expiry(self) -> None:
        delay = self.grant.expires_at - self._clock()
        if delay > 0:
            await asyncio.sleep(delay)
        self.drop("session expired")

    # -- routing -------------------------------------------------------------------------------

    def _address(self, account: str) -> str:
        self._ensure_live()
        try:
            address = hex(int(account, 16))
        except (TypeError, ValueError):
            raise_value_error(f"SessionAccounts: invalid account {account!r}")
        if address not in self._clients:
            raise_value_error(f"SessionAccounts: {address} is not covered by this session's grant")
        return address

    def api(self, account: str) -> ParadexApiClient:
        """The REST client authenticated as ``account``."""
        return self._clients[self._address(account)]

    def ws(self, account: str) -> ParadexWebsocketClient:
        """The websocket client authenticated as ``account``."""
        address = self._address(account)
        if address not in self._sockets:
            raise_value_error("SessionAccounts: websockets are disabled (ws_enabled=False)")
        return self._sockets[address]

    async def connect_ws(self) -> None:
        """Connect and authenticate one websocket per account, and drop everything at expiry."""
        for address, ws in self._sockets.items():
            self._clients[address]._validate_auth()  # fresh JWT before the socket authenticates
            if not await ws.connect():
                raise SessionWebsocketError(address)
        if self._expiry_task is None:
            self._expiry_task = asyncio.get_running_loop().create_task(self._drop_at_expiry())

    def submit_order(self, account: str, order: Order) -> dict:
        """Sign ``order`` with the session key and submit it as ``account``."""
        return self.api(account).submit_order(order)

    def submit_orders_batch(self, account: str, orders: list[Order]) -> dict:
        return self.api(account).submit_orders_batch(orders)

    def modify_order(self, account: str, order_id: str, order: Order) -> dict:
        return self.api(account).modify_order(order_id, order)

    def cancel_order(self, account: str, order_id: str) -> None:
        self.api(account).cancel_order(order_id)

    def cancel_all_orders(self, account: str, params: dict | None = None) -> None:
        if params and _FORBIDDEN_ORDER_FIELDS.intersection(params):
            raise_value_error("SessionAccounts: sessions never act on_behalf_of another account")
        self.api(account).cancel_all_orders(params)
