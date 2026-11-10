"""Trade several accounts from one session key and its owner-signed grant.

.. warning::
    Experimental. The session endpoints are live, but this SDK API may still change.

A ``SessionGrant`` names an anchor account and, optionally, sub-accounts. The server keeps
one session row per listed account, so the session key authenticates to each one on its own:
``SessionAccounts`` mints and refreshes a JWT per account (``/auth`` with
``PARADEX-STARKNET-ACCOUNT`` set to that account, signed by the session key, at most 15
minutes and never past the session's expiry), keeps one REST client and one websocket per
account, and routes every call by account. Sessions never use ``on_behalf_of``.

Revocation is detected without polling. When ``/auth`` or a websocket login refuses the session
key, or any call returns 401, ``SessionAccounts`` checks the grant's ``state`` with the
unauthenticated ``GET /v2/sessions/{grant_id}/status``. If it is ``revoked`` or ``expired``, or the
server does not know the grant (404), every account is dropped
together: JWTs are cleared, sockets closed, and further calls raise :class:`SessionDroppedError`.
Any other answer (including no answer) keeps the session: ``/auth`` is retried with a short backoff,
then the refusal is raised for the caller to retry later. The session also drops itself at the
grant's ``expiresAt``.
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
from starknet_py.constants import EC_ORDER
from starknet_py.net.signer.key_pair import KeyPair

from paradex_py.account.subkey_account import SubkeyAccount
from paradex_py.api.api_client import ParadexApiClient
from paradex_py.api.http_client import HttpClient, HttpMethod
from paradex_py.api.ws_client import ParadexWebsocketClient
from paradex_py.environment import Environment, _validate_env
from paradex_py.message.session import SessionGrant, grant_environment, sign_eip712_typed_data
from paradex_py.utils import raise_value_error

if TYPE_CHECKING:
    from paradex_py.api.models import SystemConfig
    from paradex_py.api.protocols import OwnerSigner, RetryStrategy, WebSocketConnector
    from paradex_py.common.order import Order

__all__ = [
    "LocalOwnerSigner",
    "SessionAccounts",
    "SessionDroppedError",
    "SessionRejectedError",
    "SessionRevokeError",
    "SessionWebsocketError",
    "new_session_key",
    "register_session",
]

# A session's /auth signature, and so its JWT, lives at most this long.
SESSION_AUTH_MAX_SECONDS = 15 * 60
# Grant states after which the session is gone for good.
_DEAD_STATES = frozenset({"revoked", "expired", "unknown"})
# The 400 errors /auth answers a session key with for a revoked, expired or unknown grant.
_SESSION_REFUSAL_ERRORS = frozenset({"SESSION_REVOKED", "SESSION_EXPIRED", "INVALID_SUBKEY"})
# /auth attempts while the grant is not known to be gone, and the first backoff between them.
_AUTH_ATTEMPTS = 3
_AUTH_BACKOFF_SECONDS = 0.5
# An EOA's EIP-712 signature: 0x and 65 bytes of hex. The server refuses longer ones (contract wallets).
_EOA_SIGNATURE_HEX_LENGTH = 2 + 2 * 65
# Header carrying a Privy access token for the wallet whose first grant opens its account.
PRIVY_ACCESS_TOKEN_HEADER = "PARADEX-PRIVY-ACCESS-TOKEN"  # noqa: S105 -- a header name, not a secret
# Query parameters a session must not set itself: token usage is decided by the server.
_FORBIDDEN_AUTH_PARAMS = frozenset({"token_usage"})
_FORBIDDEN_ORDER_FIELDS = frozenset({"on_behalf_of_account", "on_behalf_of"})


class SessionDroppedError(RuntimeError):
    """Raised when a call is made after the session was dropped (expired, revoked or closed)."""


class SessionRejectedError(ValueError):
    """The server refused the session key (HTTP 401 or 403, or a 400 naming a session error)."""

    def __init__(self, status_code: int, body: str):
        super().__init__(f"HTTP {status_code}: {body[:200]}")
        self.status_code = status_code


class SessionRevokeError(RuntimeError):
    """The server did not confirm revoking the grant; the session is still live.

    After a 5xx the server may have revoked the grant without cancelling its orders. A retry from this
    session is then refused and drops it; only the owner's ``DELETE /v2/sessions/{grant_id}`` with
    ``cancel_orders=true`` cancels them.
    """

    def __init__(self, status_code: int, body: str):
        message = f"revoke failed: HTTP {status_code}: {body[:200]}"
        if status_code >= 500:
            message += (
                "; the grant may already be revoked with its orders still working. If a retry drops the"
                " session, the owner must revoke it with cancel_orders=true to cancel them"
            )
        super().__init__(message)
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
        return sign_eip712_typed_data(typed_data, self._eth_private_key)


def register_session(
    env: Environment,
    grant: SessionGrant,
    owner_signer: OwnerSigner,
    http_client: HttpClient | None = None,
    api_base_url: str | None = None,
    *,
    referral_code: str | None = None,
    marketing_code: str | None = None,
    utm: dict[str, str] | None = None,
    privy_access_token: str | None = None,
    owner_address: str | None = None,
    check_subaccounts: bool = True,
) -> dict:
    """Have an EVM owner sign ``grant`` (EIP-712) and register it with ``POST /v2/sessions``.

    .. warning::
        Experimental: this SDK API may still change.

    A wallet with no Paradex account can open one with its first grant: name the account the wallet
    would onboard to (``ParadexApiClient.fetch_onboarding({"account_signer_type": "eip191",
    "eth_address": wallet})["address"]``) and list no sub-accounts. Only an EOA can do this; the account
    is deployed when it is first funded. Such a request is checked as onboarding is, so it can also be
    refused with the onboarding errors (``INSUFFICIENT_MIN_CHAIN_BALANCE``, ``INVALID_MARKETING_CODE``,
    ``ETHEREUM_ADDRESS_BLOCKED``, ``PARENT_ADDRESS_ALREADY_ONBOARDED``, or HTTP 429
    ``ONBOARDING_RATE_LIMITED``). ``SESSIONS_DISABLED`` comes only after the signature verifies.

    Args:
        env: Environment.
        grant: The grant to register. Its ``environment`` must match ``env``.
        owner_signer: Signs the EIP-712 grant; the owner's key never reaches the SDK.
        http_client: Optional HTTP client.
        api_base_url: Optional ``/v1`` base URL override; ``/v2`` is derived from it.
        referral_code: Referral code for an account this grant opens. Not signed; ignored otherwise,
            and for a grant that approves a builder.
        marketing_code: Marketing code (``campaign:code``) for an account this grant opens, as above.
        utm: UTM parameters (``source``, ``campaign`` and optionally ``type``) for an account this grant
            opens, as above.
        privy_access_token: A Privy access token for the signing wallet; sent as the
            ``PARADEX-PRIVY-ACCESS-TOKEN`` header and used only when the grant opens an account.
        owner_address: The owner wallet's address, for the sub-account check. Defaults to
            ``owner_signer.address`` when the signer has one (``LocalOwnerSigner`` does).
        check_subaccounts: Before the owner signs, refuse sub-accounts the server would refuse with
            ``ACCOUNT_NOT_ELIGIBLE``: a grant may list only the wallet's own EVM sub-accounts, as
            ``fetch_evm_subaccounts`` lists them. Skipped when the owner's address is not known.

    Returns:
        The server's response: ``grant_id``, ``expires_at`` (milliseconds) and the ``accounts`` covered.
        Pass ``grant_id`` to :class:`SessionAccounts`.
    """
    _validate_env(env, "register_session")
    _check_grant_environment(env, grant)
    client = http_client or HttpClient()
    base = api_base_url or f"https://api.{env}.paradex.trade/v1"
    v2_base = base.replace("/v1", "/v2")
    _check_onboarding_fields(marketing_code, utm)
    try:
        if check_subaccounts and grant.subaccounts:
            address = owner_address or getattr(owner_signer, "address", None)
            if address:
                _check_subaccounts_listed(client, v2_base, address, grant)
        chain_id = owner_signer.signature_chain_id
        typed_data = grant.eip712_typed_data(chain_id)
        signature = owner_signer.sign_typed_data(typed_data)
        if isinstance(signature, str) and len(signature) > _EOA_SIGNATURE_HEX_LENGTH:
            raise_value_error(
                "register_session: the signature is longer than an EOA's 65 bytes; contract wallets cannot"
                " sign session grants"
            )
        payload: dict[str, Any] = {
            "grant": typed_data["message"],
            "signature": signature,
            "signature_type": "eip712",
            "signature_chain_id": chain_id,
        }
        if referral_code:
            payload["referral_code"] = referral_code
        if marketing_code:
            payload["marketing_code"] = marketing_code
        if utm:
            payload["utm"] = dict(utm)
        headers = dict(client.client.headers)
        if privy_access_token:
            headers[PRIVY_ACCESS_TOKEN_HEADER] = privy_access_token
        return client.request(
            url=f"{v2_base}/sessions",
            http_method=HttpMethod.POST,
            payload=payload,
            headers=headers,
        )
    finally:
        if http_client is None:
            client.client.close()


def _check_onboarding_fields(marketing_code: str | None, utm: dict[str, str] | None) -> None:
    """Refuse the onboarding fields the server refuses, before the owner signs."""
    if marketing_code:
        parts = marketing_code.split(":")
        if len(parts) != 2 or not all(parts):
            raise_value_error(f"register_session: marketing_code must be 'campaign:code', got {marketing_code!r}")
    if utm and not (utm.get("source") and utm.get("campaign")):
        raise_value_error("register_session: utm must have both source and campaign")


def _check_subaccounts_listed(client: HttpClient, v2_base: str, owner_address: str, grant: SessionGrant) -> None:
    """Refuse sub-accounts that are not the owner wallet's own EVM sub-accounts, before it signs.

    The server checks every listed sub-account again, so when the listing cannot be read the check is
    skipped rather than blocking the registration.
    """
    try:
        listed = client.request(
            url=f"{v2_base}/onboarding/subaccounts",
            http_method=HttpMethod.GET,
            params={"eth_address": owner_address},
            headers=client.client.headers,
        )
    except Exception as e:
        logging.getLogger(__name__).warning(f"register_session: sub-account listing unavailable, not checked: {e}")
        return
    results = listed.get("results") if isinstance(listed, dict) else None
    if not isinstance(results, list):
        logging.getLogger(__name__).warning("register_session: sub-account listing unreadable, not checked")
        return
    owned = {int(entry["address"], 16) for entry in results if isinstance(entry, dict) and "address" in entry}
    unknown = [address for address in grant.to_message()["subaccounts"] if int(address, 16) not in owned]
    if unknown:
        raise_value_error(
            f"register_session: {unknown} are not sub-accounts of {owner_address}'s account; a grant may list"
            " only the owner wallet's own EVM sub-accounts (see fetch_evm_subaccounts)"
        )


def _check_grant_environment(env: Environment, grant: SessionGrant) -> None:
    expected = grant_environment(env)
    if grant.environment != expected:
        raise_value_error(f"grant environment is {grant.environment!r}; the {env!r} environment needs {expected!r}")


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


def _refuse_on_behalf_of(params: Any, payload: Any) -> None:
    bodies = payload if isinstance(payload, list) else [payload]
    for fields in (params, *bodies):
        if isinstance(fields, dict) and _FORBIDDEN_ORDER_FIELDS.intersection(fields):
            raise_value_error("SessionAccounts: sessions never act on_behalf_of another account")


def _error_code(res: httpx.Response) -> str | None:
    """The ``error`` code of an API error body, or None if the body is not one."""
    try:
        body = res.json()
    except ValueError:
        return None
    return body.get("error") if isinstance(body, dict) else None


def _session_refusal(res: httpx.Response) -> bool:
    """A 400 whose ``error`` says the session key's grant is revoked, expired or unknown."""
    return res.status_code == 400 and _error_code(res) in _SESSION_REFUSAL_ERRORS


def _grant_not_found(res: httpx.Response) -> bool:
    """Whether the server says the grant does not exist, as opposed to a 404 for an unknown route."""
    return res.status_code == 404 and _error_code(res) == "NOT_FOUND"


class _SessionApiClient(ParadexApiClient):
    """REST client for one account of a session: refuses calls once the session is dropped."""

    classname = "SessionApiClient"

    def __init__(self, owner: SessionAccounts, **kwargs: Any):
        self._owner = owner
        super().__init__(**kwargs)

    def _handle_response(self, res: httpx.Response, url: str, http_method: HttpMethod) -> Any:
        if res.status_code in (401, 403) or _session_refusal(res):
            raise SessionRejectedError(res.status_code, res.text)
        return super()._handle_response(res, url, http_method)

    def request(self, url: str, http_method: HttpMethod, *args: Any, **kwargs: Any):
        _refuse_on_behalf_of(kwargs.get("params"), kwargs.get("payload"))
        try:
            return super().request(url, http_method, *args, **kwargs)
        except SessionRejectedError as e:
            # A 401 (or a session error) may only mean this JWT went stale, so log in again first:
            # auth() checks the grant if that is refused too. A 403 is a refused action (e.g. a scope
            # the grant lacks), and refusals of /auth itself are handled by auth().
            if e.status_code != 403 and "/auth/" not in url:
                self.auth()
            raise

    def auth(self, params: dict | None = None):
        """Log in as this account, retrying with backoff while the grant is not known to be gone."""
        params = self.auth_params if params is None else params
        for attempt in range(_AUTH_ATTEMPTS):
            self._owner._ensure_live()
            try:
                super().auth(params=params)
            except SessionRejectedError as e:
                self._owner._on_refused(e)  # drops and raises if the grant is revoked or expired
                if attempt == _AUTH_ATTEMPTS - 1:
                    raise
                self._owner._sleep(_AUTH_BACKOFF_SECONDS * 2**attempt)
            else:
                return

    def fetch_grant_state(self) -> str | None:
        """``GET /v2/sessions/{grant_id}/status``: ``active``, ``revoked``, ``expired``, or ``unknown`` on 404.

        The endpoint needs no login, so it answers even when the session's own JWTs are refused. The
        request is sent without the ``Authorization`` header. Returns None when there is no usable answer.
        """
        # build_request() applies the client's timeout and headers; the login header is then removed.
        request = self.client.build_request("GET", f"{self._v2_api_url}/sessions/{self._owner.grant_id}/status")
        request.headers.pop("Authorization", None)
        res = self.client.send(request)
        if _grant_not_found(res):
            return "unknown"
        if res.status_code != 200:
            return None
        state = res.json().get("state")
        return state if isinstance(state, str) else None

    def _validate_auth(self):
        self._owner._ensure_live()
        super()._validate_auth()
        self._owner._ensure_live()  # a drop while this thread logged in (e.g. revoke()) stops the call


class _SessionWebsocketClient(ParadexWebsocketClient):
    """Websocket for one account of a session: never reconnects or logs in once the session is dropped."""

    def __init__(self, owner: SessionAccounts, api_client: _SessionApiClient, **kwargs: Any):
        self._owner = owner
        self._session_client = api_client
        super().__init__(api_client=api_client, **kwargs)

    async def connect(self) -> bool:
        if not self._owner.is_live:
            return False
        connected = await super().connect()
        if connected and not self._owner.is_live:  # dropped while connecting
            await self._close_connection()
            return False
        return connected

    async def _reconnect(self):
        if not self._owner.is_live:
            return
        if self._is_token_expired() and not await self._relogin():
            return
        if self._owner.is_live and not self.disable_reconnect:
            # The base reconnect would log in again, on the loop, if the JWT is still stale; reconnect
            # directly instead and let the server refuse a stale token.
            try:
                async with self._recv_lock:
                    await self._close_connection()
                    await self.connect()
                await self._resubscribe()
            except Exception:
                self.logger.exception(f"{self.classname}: Reconnect failed")

    async def _reconnect_with_auth_refresh(self):
        # The server refused this socket's login: log in again over REST, which checks the grant
        # and drops every account if it is revoked or expired.
        if not self._owner.is_live or self.disable_reconnect:
            return
        if await self._relogin():
            await self._reconnect()

    async def _relogin(self) -> bool:
        """Log in again on a thread (a session login may back off with blocking sleeps).

        Returns False once the session is dropped. Any other failure (refused with the grant still
        active, a network error, a 429) is logged and the reconnect goes ahead, as in the base client,
        so the socket's reader keeps running.
        """
        try:
            await asyncio.to_thread(self._session_client.auth)
        except SessionDroppedError:
            return False
        except Exception:
            self.logger.warning(f"{self.classname}: session login failed; reconnecting anyway", exc_info=True)
        return True


class SessionAccounts:
    """One session key, its grant, and a JWT, REST client and websocket per listed account.

    .. warning::
        Experimental; see the module docstring.

    Args:
        env: Environment.
        grant: The owner-signed grant (already registered with the server).
        session_private_key: The session's Stark private key; its public key must be ``grant.session_key``.
        grant_id: The id ``register_session`` returned for ``grant`` (a hash of it, so it is checked);
            used to check and revoke the grant.
        config: Pre-fetched system configuration; fetched once if omitted.
        logger: Logger.
        auth_params: Extra ``/auth`` query parameters. ``token_usage`` is refused: the server decides it.
        http_client_factory: Builds the HTTP client for each account (each holds its own JWT header).
        api_base_url: Optional ``/v1`` base URL override for every account's client, as in ``register_session``.
        retry_strategy: Optional retry strategy for every account's client (e.g. ``DefaultRetryStrategy``).
        ws_enabled: Whether to create a websocket client per account.
        ws_connector: Optional websocket connector, passed to every websocket client.
        on_dropped: Called once with the reason when the session is dropped.
        clock: Time source in seconds, for tests.
        sleep: Blocking sleep used between ``/auth`` retries, for tests.

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
        api_base_url: str | None = None,
        retry_strategy: RetryStrategy | None = None,
        ws_enabled: bool = True,
        ws_connector: WebSocketConnector | None = None,
        on_dropped: Callable[[str], None] | None = None,
        clock: Callable[[], float] = time.time,
        sleep: Callable[[float], None] = time.sleep,
    ):
        _validate_env(env, "SessionAccounts")
        _check_grant_environment(env, grant)
        if auth_params and _FORBIDDEN_AUTH_PARAMS.intersection(auth_params):
            raise_value_error(f"SessionAccounts: {sorted(_FORBIDDEN_AUTH_PARAMS)} is set by the server, not the client")
        self.accounts: list[str] = grant.accounts  # validates the grant
        if grant_id not in grant.grant_ids():
            # Another grant's id would check and revoke that grant; a malformed one reads as revoked (404).
            raise_value_error(f"SessionAccounts: grant_id {grant_id!r} is not this grant's id")
        public_key = KeyPair.from_private_key(int(session_private_key, 16)).public_key
        if public_key != int(grant.session_key, 16):
            raise_value_error("SessionAccounts: session_private_key does not match grant.session_key")

        self.env = env
        self.grant = grant
        self.grant_id = grant_id
        self.logger = logger or logging.getLogger(__name__)
        self._clock = clock
        self._sleep = sleep
        self._client_options: dict[str, Any] = {"api_base_url": api_base_url, "retry_strategy": retry_strategy}
        self._loop: asyncio.AbstractEventLoop | None = None
        self._on_dropped = on_dropped
        self.dropped_reason: str | None = None
        self._expiry_task: asyncio.Task | None = None
        self._close_tasks: list[asyncio.Task] = []

        self._clients: dict[str, _SessionApiClient] = {}
        self._sockets: dict[str, ParadexWebsocketClient] = {}
        try:
            self._ensure_live()
            self._build_clients(http_client_factory, auth_params)
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
                    ws = _SessionWebsocketClient(
                        owner=self, env=env, logger=logger, api_client=client, connector=ws_connector
                    )
                    ws.init_account(account)
                    self._sockets[address] = ws
                client.init_account(account)  # mints the account's first JWT
        except BaseException:
            self._release()
            raise

    def _release(self) -> None:
        """Undo a construction that failed part-way: stop socket readers and close HTTP clients."""
        for ws in self._sockets.values():
            if ws._reader_task is not None:
                ws._reader_task.cancel()
        for client in self._clients.values():
            client.client.close()

    def _build_clients(self, http_client_factory: Callable[[], httpx.Client] | None, auth_params: dict | None) -> None:
        for address in self.accounts:
            http_client = http_client_factory() if http_client_factory else None
            if http_client is not None and any(c.client is http_client for c in self._clients.values()):
                raise_value_error("SessionAccounts: http_client_factory must build a new client per account")
            self._clients[address] = _SessionApiClient(
                owner=self,
                env=self.env,
                logger=self.logger,
                http_client=http_client,
                auth_params=auth_params,
                **self._client_options,
            )

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

    def _grant_state(self) -> str | None:
        """The grant's state; None when it cannot be learned."""
        try:
            return self._clients[self.accounts[0]].fetch_grant_state()
        except (ValueError, httpx.HTTPError) as e:
            self.logger.warning(f"SessionAccounts: grant state check failed: {e}")
            return None

    def _on_refused(self, error: SessionRejectedError) -> None:
        """After the server refused the session key, drop every account if the grant is gone."""
        if self.dropped_reason is not None:
            raise SessionDroppedError(self.dropped_reason) from error
        state = self._grant_state()
        if state in _DEAD_STATES:
            self.drop(f"grant {self.grant_id} is {state}")
            raise SessionDroppedError(self.dropped_reason) from error
        self.logger.warning(f"SessionAccounts: refused ({error}); grant {self.grant_id} state is {state!r}")

    def revoke(self, cancel_orders: bool = True) -> None:
        """Revoke the grant on the server (``DELETE /v2/sessions/{grant_id}``), then drop every account.

        With ``cancel_orders`` (the default) the server also cancels the session's resting orders, TWAPs
        and untriggered stops on every account. Without it, a session revoking its own grant is a
        sign-out: they keep working, and this key can no longer cancel them.

        The session drops only when the server confirms: success, or 404 for a grant it no longer has.
        Otherwise it stays live and :class:`SessionRevokeError` is raised, so the call can be retried.
        After a 5xx the grant may already be revoked with its orders still working: a retry is then
        refused and drops the session, and only the owner's revoke with ``cancel_orders`` cancels them.
        Call it before :meth:`close`: a dropped session no longer logs in, so it cannot revoke.
        """
        client = self._clients[self.accounts[0]]
        client._validate_auth()
        url = f"{client._v2_api_url}/sessions/{self.grant_id}"
        params = {"cancel_orders": "true"} if cancel_orders else None
        res = client.client.send(client.client.build_request("DELETE", url, params=params))
        if res.status_code in (401, 403) or _session_refusal(res):
            # The session key was refused: if the grant is already revoked or expired, this drops it.
            self._on_refused(SessionRejectedError(res.status_code, res.text))
        if not (res.is_success or _grant_not_found(res)):
            raise SessionRevokeError(res.status_code, res.text)
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
        self._close_sockets()
        if self._on_dropped is not None:
            self._on_dropped(reason)

    def _close_sockets(self) -> None:
        for ws in self._sockets.values():
            # The socket's reconnect path carries on after a failed refresh; a dropped session must not.
            ws.disable_reconnect = True
        loop = self._loop
        if loop is not None and not loop.is_closed():
            try:
                running = asyncio.get_running_loop()
            except RuntimeError:
                running = None
            if running is loop:
                for ws in self._sockets.values():
                    self._close_tasks.append(loop.create_task(ws.close()))
                if self._expiry_task is not None and self._expiry_task is not asyncio.current_task(loop):
                    self._expiry_task.cancel()
            else:  # dropped from another thread, e.g. a REST call run in a worker thread
                for ws in self._sockets.values():
                    asyncio.run_coroutine_threadsafe(ws.close(), loop)
                if self._expiry_task is not None:
                    loop.call_soon_threadsafe(self._expiry_task.cancel)

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
        """Connect and authenticate one websocket per account, and drop everything at expiry.

        If a socket fails to connect, the ones already connected are closed again.
        """
        self._ensure_live()
        self._loop = asyncio.get_running_loop()
        task = self._expiry_task
        if task is None or task.done() or task.get_loop() is not self._loop:  # e.g. its loop ended
            self._expiry_task = self._loop.create_task(self._drop_at_expiry())
        connected: list[ParadexWebsocketClient] = []
        for address, ws in self._sockets.items():
            # A fresh JWT before the socket authenticates, off the loop (a login may back off).
            await asyncio.to_thread(self._clients[address]._validate_auth)
            if not await ws.connect():
                for open_ws in connected:
                    await open_ws.close()
                raise SessionWebsocketError(address)
            connected.append(ws)

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
        self.api(account).cancel_all_orders(params)
