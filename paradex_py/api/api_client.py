import base64
import json
import logging
import re
import time
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, cast

import httpx

from paradex_py.account.account import ParadexAccount
from paradex_py.api.block_trades_api import BlockTradesMixin
from paradex_py.api.http_client import HttpClient, HttpMethod
from paradex_py.api.models import AccountSummary, AccountSummarySchema, AuthSchema, SystemConfig, SystemConfigSchema
from paradex_py.api.protocols import AuthProvider, RetryStrategy, Signer
from paradex_py.common.order import Order
from paradex_py.environment import Environment
from paradex_py.utils import raise_value_error

if TYPE_CHECKING:
    from paradex_py.account.evm_account import EvmAccount

_REFRESH_BUFFER_SECONDS = 30  # refresh 30s before JWT expiry to avoid race conditions
_OPAQUE_TOKEN_LIFETIME_SECONDS = 4 * 60  # assumed lifetime for tokens without an exp claim


def _jwt_exp(token: str) -> float | None:
    """Decode JWT payload and return the ``exp`` claim, or ``None`` if unavailable."""
    try:
        payload_b64 = token.split(".")[1]
        payload_b64 += "=" * (4 - len(payload_b64) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
    except Exception:
        return None
    else:
        exp = payload.get("exp")
        return float(exp) if exp is not None else None


class ParadexApiClient(BlockTradesMixin, HttpClient):
    """Class to interact with Paradex REST API.
        Initialized along with `Paradex` class.

    After any REST call, rate limit info from the last response is available as
    :attr:`last_rate_limit` (limit, remaining, reset, window from x-ratelimit-*
    headers). Use it to back off before hitting 429 or to wait after one.

    Args:
        env (Environment): Environment
        logger (logging.Logger, optional): Logger. Defaults to None.
        http_client (HttpClient, optional): Custom HTTP client for injection. Defaults to None.
        api_base_url (str, optional): Custom base URL override. Defaults to None.
        auto_auth (bool, optional): Whether to automatically handle onboarding/auth. Defaults to True.
        auth_provider (AuthProvider, optional): Custom authentication provider. Defaults to None.
        signer (Signer, optional): Custom order signer for submit/modify/batch operations. Defaults to None.
        on_token_expired (Callable[[], str | None], optional): Called when a manually-injected token
            (set via ``set_token()``) expires. Expiry is detected from the JWT ``exp`` claim when
            present; falls back to a 4-minute window for opaque tokens. Should return a fresh token
            string, or None if unavailable. Only meaningful when ``auto_auth=False``. Defaults to None.
        auth_params (dict, optional): Extra query parameters sent with every ``/auth`` request
            (initial and refresh). For example, ``{"token_usage": "interactive"}`` to obtain a
            0-fee JWT token. Defaults to None.

    Examples:
        >>> from paradex_py import Paradex
        >>> from paradex_py.environment import Environment
        >>> paradex = Paradex(env=Environment.TESTNET)
    """

    classname: str = "ParadexApiClient"

    def __init__(
        self,
        env: Environment,
        logger: logging.Logger | None = None,
        http_client: HttpClient | None = None,
        api_base_url: str | None = None,
        auto_auth: bool = True,
        auth_provider: AuthProvider | None = None,
        signer: Signer | None = None,
        retry_strategy: RetryStrategy | None = None,
        on_token_expired: Callable[[], str | None] | None = None,
        auth_params: dict | None = None,
    ):
        self.env = env
        self.logger = logger or logging.getLogger(__name__)

        # Initialize parent with optional HTTP client injection
        if http_client is not None:
            # Extract the underlying httpx.Client if it's wrapped in HttpClient
            if hasattr(http_client, "client"):
                # http_client is another HttpClient instance, extract the underlying client
                underlying_client = http_client.client
            else:
                # http_client is already an httpx.Client, cast to ensure type safety
                underlying_client = cast(httpx.Client, http_client)
            super().__init__(http_client=underlying_client, retry_strategy=retry_strategy)
        else:
            super().__init__(retry_strategy=retry_strategy)

        # Use custom base URL if provided, otherwise use default
        if api_base_url is not None:
            self.api_url = api_base_url
            self._v2_api_url = api_base_url.replace("/v1", "/v2")
        else:
            self.api_url = f"https://api.{self.env}.paradex.trade/v1"
            self._v2_api_url = f"https://api.{self.env}.paradex.trade/v2"

        # Auth configuration
        self.auto_auth = auto_auth
        self.auth_provider = auth_provider
        self.auth_params = auth_params
        self._manual_token: str | None = None
        self._token_exp: float | None = None
        self.on_token_expired: Callable[[], str | None] | None = on_token_expired
        self.account: ParadexAccount | None = None
        self._evm_account: EvmAccount | None = None
        self.auth_timestamp = 0

        # Signing configuration
        self.signer = signer

        # EVM account flag (set by init_account_evm)
        self._is_evm_account = False

    def init_account(self, account: ParadexAccount):
        self.account = account
        if not self.auto_auth:
            return
        is_onboarded = getattr(account, "is_onboarded", None)
        if is_onboarded is True:
            # Server precheck confirmed account is onboarded — skip POST /onboarding.
            self.auth(params=self.auth_params)
        elif is_onboarded is False:
            # Server precheck confirmed account is NOT onboarded — POST first, then auth.
            self.onboarding()
            self.auth(params=self.auth_params)
        else:
            # No precheck ran (local-derivation path) — fall back to the retry-on-error dance.
            try:
                self.auth(params=self.auth_params)
            except ValueError as e:
                if "NOT_ONBOARDED" in str(e):
                    self.onboarding()
                    self.auth(params=self.auth_params)
                else:
                    raise

    def fetch_onboarding(self, params: dict | None = None) -> dict:
        """Check whether an account has been onboarded.

        Public endpoint — no authentication required.

        Args:
            params: Query parameters. Exactly one of two forms:

                Starknet account (``account_signer_type="starknet"``)::

                    {"account_signer_type": "starknet", "public_key": "0x<l2_pubkey>"}

                EVM account (``account_signer_type="eip191"``)::

                    {"account_signer_type": "eip191", "eth_address": "0x<evm_address>"}

                Note: ``public_key`` is ignored by the server for EIP-191 accounts.

        Returns:
            dict with ``address``, ``exists`` (bool), ``account_signer_type``, and
            ``derivation_info``.
        """
        return self.get(api_url=self.api_url, path="onboarding", params=params)

    def onboarding(self):
        if self.account is None:
            raise ValueError("Account not initialized")
        headers = self.account.onboarding_headers()
        payload = {"public_key": hex(self.account.l2_public_key)}
        self.post(api_url=self.api_url, path="onboarding", headers=headers, payload=payload)

    def auth(self, params: dict | None = None):
        if self.account is None:
            raise ValueError("Account not initialized")
        headers = self.account.auth_headers()
        res = self.post(
            api_url=self.api_url, path=f"auth/{hex(self.account.l2_public_key)}", headers=headers, params=params
        )
        data = AuthSchema().load(res, unknown="exclude", partial=True)
        self.auth_timestamp = int(time.time())
        self._token_exp = _jwt_exp(data.jwt_token)
        self.account.set_jwt_token(data.jwt_token)
        self.client.headers.update({"Authorization": f"Bearer {data.jwt_token}"})

    def init_account_evm(self, account: "EvmAccount"):
        """Initialize an EVM account and run the v2 onboarding/auth flow."""
        self._evm_account = account
        self._is_evm_account = True
        if not self.auto_auth:
            return
        is_onboarded = getattr(account, "is_onboarded", None)
        if is_onboarded is True:
            self.auth_evm(params=self.auth_params)
        elif is_onboarded is False:
            self.onboarding_evm()
            self.auth_evm(params=self.auth_params)
        else:
            try:
                self.auth_evm(params=self.auth_params)
            except ValueError as e:
                if "NOT_ONBOARDED" in str(e):
                    self.onboarding_evm()
                    self.auth_evm(params=self.auth_params)
                else:
                    raise

    def onboarding_evm(self):
        """Onboard an EVM account via POST /v2/onboarding (SIWE)."""
        if self._evm_account is None:
            raise ValueError("EVM account not initialized")
        headers = self._evm_account.onboarding_headers()
        payload = {"public_key": self._evm_account.evm_public_key_uncompressed}
        self.post(api_url=self._v2_api_url, path="onboarding", headers=headers, payload=payload)

    def auth_evm(self, params: dict | None = None):
        """Obtain a JWT for an EVM account via POST /v2/auth (SIWE)."""
        if self._evm_account is None:
            raise ValueError("EVM account not initialized")
        headers = self._evm_account.auth_headers()
        res = self.post(api_url=self._v2_api_url, path="auth", headers=headers, params=params)
        data = AuthSchema().load(res, unknown="exclude", partial=True)
        self.auth_timestamp = int(time.time())
        self._token_exp = _jwt_exp(data.jwt_token)
        self._evm_account.set_jwt_token(data.jwt_token)
        self.client.headers.update({"Authorization": f"Bearer {data.jwt_token}"})

    def set_token(self, jwt: str) -> None:
        """Inject a JWT token directly, bypassing the standard onboarding/auth flow.

        Used by ``ParadexApiKey`` to supply a pre-generated token, and also useful
        for testing/simulation scenarios.

        Args:
            jwt: JWT token string
        """
        self._manual_token = jwt
        self.auth_timestamp = int(time.time())
        self._token_exp = _jwt_exp(jwt)
        self.client.headers.update({"Authorization": f"Bearer {jwt}"})
        if self.account:
            self.account.set_jwt_token(jwt)

    def _is_token_expired(self) -> bool:
        """Return True if the current token should be refreshed."""
        exp = self._token_exp
        if exp is not None:
            return time.time() > exp - _REFRESH_BUFFER_SECONDS
        # assumed lifetime for opaque (non-JWT) tokens that have no exp claim
        return time.time() - self.auth_timestamp > _OPAQUE_TOKEN_LIFETIME_SECONDS

    def _refresh_manual_token(self) -> None:
        """Refresh a manually-injected token via the on_token_expired callback if expired."""
        if self.on_token_expired and self._is_token_expired():
            new_token = self.on_token_expired()
            if new_token:
                self.set_token(new_token)
            else:
                self.logger.warning(f"{self.classname}: on_token_expired callback returned None; reusing expired token")

    def _apply_provider_token(self, token: str) -> None:
        """Apply a token obtained from the auth provider to the HTTP client and account."""
        self.client.headers.update({"Authorization": f"Bearer {token}"})
        if self.account:
            self.account.set_jwt_token(token)

    def _validate_auth(self):
        # Precedence: manual token > auth_provider > account-based auth.
        # If both _manual_token and auth_provider are set, auth_provider is bypassed with a warning.
        # For manually-injected tokens (auto_auth disabled): check expiry and refresh via callback
        if not self.auto_auth and self._manual_token:
            if self.auth_provider:
                self.logger.warning(
                    f"{self.classname}: both _manual_token and auth_provider are set; auth_provider is ignored"
                )
            self._refresh_manual_token()
            return

        # Use custom auth provider if available
        if self.auth_provider:
            token = self.auth_provider.refresh_if_needed()
            if token:
                self._apply_provider_token(token)
                return

        # Fall back to standard account-based auth
        if self.account is None and self._evm_account is None:
            if not self.auto_auth:
                return  # Skip auth if disabled and no account
            raise_value_error(f"{self.classname}: Account not found")

        # Refresh JWT if expired
        if self._is_token_expired():
            if self.auto_auth:
                if self._is_evm_account:
                    self.auth_evm(params=self.auth_params)
                else:
                    self.auth(params=self.auth_params)
            else:
                self.logger.warning(f"{self.classname}: JWT expired but auto_auth disabled")

    def _get(self, path: str, params: dict | None = None) -> dict:
        return self.get(api_url=self.api_url, path=path, params=params)

    def _get_authorized(self, path: str, params: dict | None = None) -> dict:
        self._validate_auth()
        return self._get(path=path, params=params)

    def _post_authorized(
        self,
        path: str,
        payload: dict[str, Any] | list[dict[str, Any]] | None = None,
        params: dict | None = None,
        headers: dict | None = None,
    ) -> dict:
        self._validate_auth()
        return self.post(api_url=self.api_url, path=path, payload=payload, params=params, headers=headers)

    def _put_authorized(
        self,
        path: str,
        payload: dict[str, Any] | list[dict[str, Any]] | None = None,
        params: dict | None = None,
        headers: dict | None = None,
    ) -> dict:
        self._validate_auth()
        return self.put(api_url=self.api_url, path=path, payload=payload, params=params, headers=headers)

    def _delete_authorized(self, path: str, params: dict | None = None, payload: dict | None = None) -> dict:
        self._validate_auth()
        return self.delete(api_url=self.api_url, path=path, params=params, payload=payload)

    # PRIVATE GET METHODS
    def fetch_orders(self, params: dict | None = None) -> dict:
        """Fetch open orders for the account.
            Private endpoint requires authorization.

        Args:
            params:
                `market`: Market for the order\n

        Returns:
            results (list): Orders list
        """
        return self._get_authorized(path="orders", params=params)

    def fetch_orders_history(self, params: dict | None = None) -> dict:
        """Fetch history of orders for the account.
            Private endpoint requires authorization.

        Args:
            params:
                `client_id`: Unique ID of client generating the order\n
                `cursor`: Returns the `next` paginated page\n
                `end_at`: End Time (unix time millisecond)\n
                `market`: Market for the order\n
                `page_size`: Limit the number of responses in the page\n
                `side`: Order side\n
                `start_at`: Start Time (unix time millisecond)\n
                `status`: Order status\n
                `type`: Order type\n

        Returns:
            next (str): The pointer to fetch next set of records (null if there are no records left)
            prev (str): The pointer to fetch previous set of records (null if there are no records left)
            results (list): List of Orders
        """
        return self._get_authorized(path="orders-history", params=params)

    def fetch_order(self, order_id: str) -> dict:
        """Fetch a state of specific order sent from this account.
            Private endpoint requires authorization.

        Args:
            order_id: order's id as assigned by Paradex.
        """
        return self._get_authorized(path=f"orders/{order_id}")

    def fetch_order_by_client_id(self, client_id: str) -> dict:
        """Fetch a state of specific order sent from this account.
            Private endpoint requires authorization.

        Args:
            client_id: order's client_id as assigned by a trader.
        """
        return self._get_authorized(path=f"orders/by_client_id/{client_id}")

    def fetch_fills(self, params: dict | None = None) -> dict:
        """Fetch history of fills for this account.
            Private endpoint requires authorization.

        Args:
            params:
                `cursor`: Returns the `next` paginated page\n
                `end_at`: End Time (unix time millisecond)\n
                `market`: Market for the fills\n
                `page_size`: Limit the number of responses in the page\n
                `start_at`: Start Time (unix time millisecond)\n

        Returns:
            next (str): The pointer to fetch next set of records (null if there are no records left)
            prev (str): The pointer to fetch previous set of records (null if there are no records left)
            results (list): List of Fills
        """
        return self._get_authorized(path="fills", params=params)

    def fetch_tradebusts(self, params: dict | None = None) -> dict:
        """Fetch history of tradebusts for this account.

        Args:
            params:
                `cursor`: Returns the `next` paginated page\n
                `end_at`: End Time (unix time millisecond)\n
                `page_size`: Limit the number of responses in the page\n
                `start_at`: Start Time (unix time millisecond)\n

        Returns:
            next (str): The pointer to fetch next set of records (null if there are no records left)
            prev (str): The pointer to fetch previous set of records (null if there are no records left)
            results (list): List of Tradebusts
        """
        return self._get_authorized(path="tradebusts", params=params)

    def fetch_funding_payments(self, params: dict | None = None) -> dict:
        """Fetch history of funding payments for this account.
            Private endpoint requires authorization.

        Args:
            params:
                `cursor`: Returns the `next` paginated page\n
                `end_at`: End Time (unix time millisecond)\n
                `market`: Market for which funding payments are queried\n
                `page_size`: Limit the number of responses in the page\n
                `start_at`: Start Time (unix time millisecond)\n

        Returns:
            next (str): The pointer to fetch next set of records (null if there are no records left)
            prev (str): The pointer to fetch previous set of records (null if there are no records left)
            results (list): List of Funding Payments
        """
        return self._get_authorized(path="funding/payments", params=params)

    def fetch_funding_data(self, params: dict | None = None) -> dict:
        """List historical funding data by market

        Args:
            params:
                `cursor`: Returns the `next` paginated page\n
                `end_at`: End Time (unix time millisecond)\n
                `market`: Market for which funding payments are queried\n
                `page_size`: Limit the number of responses in the page\n
                `start_at`: Start Time (unix time millisecond)\n

        Returns:
            next (str): The pointer to fetch next set of records (null if there are no records left)
            prev (str): The pointer to fetch previous set of records (null if there are no records left)
            results (list): List of Funding Payments
        """
        return self._get(path="funding/data", params=params)

    def fetch_transactions(self, params: dict | None = None) -> dict:
        """Fetch history of transactions initiated by this account.
            Private endpoint requires authorization.

        Args:
            params:
                `cursor`: Returns the `next` paginated page\n
                `end_at`: End Time (unix time millisecond)\n
                `page_size`: Limit the number of responses in the page\n
                `start_at`: Start Time (unix time millisecond)\n

        Returns:
            next (str): The pointer to fetch next set of records (null if there are no records left)
            prev (str): The pointer to fetch previous set of records (null if there are no records left)
            results (list): List of Transactions
        """
        return self._get_authorized(path="transactions", params=params)

    def fetch_transfers(self, params: dict | None = None) -> dict:
        """Fetch history of transfers initiated by this account.
            Private endpoint requires authorization.

        Args:
            params:
                `cursor`: Returns the `next` paginated page\n
                `end_at`: End Time (unix time millisecond)\n
                `page_size`: Limit the number of responses in the page\n
                `start_at`: Start Time (unix time millisecond)\n
                `status`: none\n

        Returns:
            next (str): The pointer to fetch next set of records (null if there are no records left)
            prev (str): The pointer to fetch previous set of records (null if there are no records left)
            results (list): List of Transfers
        """
        return self._get_authorized(path="transfers", params=params)

    def fetch_account_summary(self) -> AccountSummary:
        """Fetch current summary for this account.
        Private endpoint requires authorization.
        """
        res = self._get_authorized(path="account")
        return AccountSummarySchema().load(res, unknown="exclude", partial=True)

    def fetch_account_profile(self) -> dict:
        """Fetch profile for this account.
        Private endpoint requires authorization.
        """
        return self._get_authorized(path="account/profile")

    def fetch_balances(self) -> dict:
        """Fetch all coin balances for this account.
            Private endpoint requires authorization.

        Returns:
            results (list): List of Balances
        """
        return self._get_authorized(path="balance")

    def fetch_positions(self) -> dict:
        """Fetch all derivatives positions for this account.
            Private endpoint requires authorization.

        Returns:
            next (str): The pointer to fetch next set of records (null if there are no records left)
            prev (str): The pointer to fetch previous set of records (null if there are no records left)
            results (list): List of Positions
        """
        return self._get_authorized(path="positions")

    def fetch_points_data(self, market: str, program: str) -> dict:
        """Fetch points program data for specific market.
            Private endpoint requires authorization.

        Args:
            market: Market Name
            program: Program Name - example: Maker, Fee

        Returns:
            results (list): List of points data
        """
        return self._get_authorized(path=f"points_data/{market}/{program}")

    def fetch_liquidations(self, params: dict | None = None) -> dict:
        """Fetch history of liquidations for this account.
            Private endpoint requires authorization.

        Args:
            params:
                `start` (int): start time in milliseconds since epoch.
                `end` (int): end time in milliseconds since epoch.

        Returns:
            results (list): List of Liquidations
        """
        return self._get(path="liquidations", params=params)

    def fetch_trades(self, params: dict) -> dict:
        """Fetch Paradex exchange trades for specific market.

        Args:
            params:
                `market`: Market Name\n

        Returns:
            next (str): The pointer to fetch next set of records (null if there are no records left)
            prev (str): The pointer to fetch previous set of records (null if there are no records left)
            results (list): List of Trades
        """
        if "market" not in params:
            raise_value_error(f"{self.classname}: Market is required to fetch trades")
        return self._get(path="trades", params=params)

    def fetch_subaccounts(self) -> dict:
        """Fetch list of sub-accounts for this account.
        Private endpoint requires authorization.
        """
        return self._get_authorized(path="account/subaccounts")

    def fetch_account_info(self) -> dict:
        """Fetch profile for this account.
        Private endpoint requires authorization.
        """
        return self._get_authorized(path="account/info")

    # SUBKEY MANAGEMENT

    def fetch_subkeys(self, params: dict | None = None) -> dict:
        """List all subkeys for this account.
        Private endpoint requires authorization.

        Args:
            params:
                `include_revoked`: Include revoked subkeys in results\n

        Returns:
            results (list): List of Subkeys
        """
        return self._get_authorized(path="account/keys/subkeys", params=params)

    def create_subkey(self, payload: dict) -> None:
        """Register a new subkey for this account.
        Private endpoint requires authorization.

        Args:
            payload: CreateSubkey fields — name, public_key, state ('active' or 'pending'),
                     encrypted_key and eph_public_key (required when state='pending').

        Returns:
            None (server responds with 204 No Content on success)
        """
        self._post_authorized(path="account/keys/subkeys", payload=payload)

    def activate_subkey(self, payload: dict) -> dict:
        """Activate a pending subkey via Starknet signature.
        Private endpoint requires authorization.

        The signature must be [r, s] over pedersen(timestamp, eph_public_key),
        produced by the main account's Starknet key.

        Args:
            payload: ActivateSubkey fields — account_id, public_key, timestamp, signature, name.

        Returns:
            ActivateSubkeyResponse dict (may include encrypted_key)
        """
        return self._post_authorized(path="account/keys/subkeys/activate", payload=payload)

    def fetch_subkey(self, public_key: str) -> dict:
        """Fetch a specific subkey by its public key.
        Private endpoint requires authorization.

        Args:
            public_key: Public key of the subkey to fetch.
        """
        return self._get_authorized(path=f"account/keys/subkeys/{public_key}")

    def update_subkey(self, public_key: str, payload: dict) -> dict:
        """Update a subkey (e.g. rename it).
        Private endpoint requires authorization.

        Args:
            public_key: Public key of the subkey to update.
            payload: UpdateSubkey fields — name.
        """
        return self._put_authorized(path=f"account/keys/subkeys/{public_key}", payload=payload)

    def revoke_subkey(self, public_key: str) -> None:
        """Revoke a subkey permanently.
        Private endpoint requires authorization.

        Args:
            public_key: Public key of the subkey to revoke.
        """
        self._delete_authorized(path=f"account/keys/subkeys/{public_key}")

    # TOKEN MANAGEMENT

    def fetch_tokens(self, params: dict | None = None) -> dict:
        """List authentication tokens for this account.
        Private endpoint requires authorization.

        Args:
            params:
                `kind`: Filter by token kind ('jwt' or 'api_key')\n

        Returns:
            results (list): List of ApiToken entries
        """
        return self._get_authorized(path="account/tokens", params=params)

    def create_token(self, payload: dict) -> dict:
        """Create a new authentication token (JWT or API key).
        Private endpoint requires authorization.

        Args:
            payload: CreateToken fields — name, token_type, expiry_duration (seconds).

        Returns:
            ApiToken response dict
        """
        return self._post_authorized(path="account/tokens", payload=payload)

    def revoke_token(self, lookup_id: str) -> None:
        """Revoke an authentication token by its lookup ID.
        Private endpoint requires authorization.

        Args:
            lookup_id: Lookup ID of the token to revoke.
        """
        self._delete_authorized(path=f"account/tokens/{lookup_id}")

    def submit_order(self, order: Order, signer: Signer | None = None) -> dict:
        """Send order to Paradex.
            Private endpoint requires authorization.

        Args:
            order: Order containing all required fields.
            signer: Optional custom signer. Uses instance signer or account signer if None.
        """
        # Use provided signer, instance signer, or account signer
        if signer is not None:
            order_data = order.dump_to_dict()
            signed_data = signer.sign_order(order_data)
            order_payload = signed_data
        elif self.signer is not None:
            order_data = order.dump_to_dict()
            signed_data = self.signer.sign_order(order_data)
            order_payload = signed_data
        else:
            # Fall back to account signing
            if self.account is None:
                raise ValueError("Account not initialized and no signer provided")
            order.signature = self.account.sign_order(order)
            order_payload = order.dump_to_dict()

        return self._post_authorized(path="orders", payload=order_payload)

    def submit_orders_batch(self, orders: list[Order], signer: Signer | None = None) -> dict:
        """Send batch of orders to Paradex.
            Private endpoint requires authorization.

        Args:
            orders: List of orders containing all required fields.
            signer: Optional custom signer. Uses instance signer or account signer if None.

        Returns:
            orders (list): List of Orders
            errors (list): List of Errors
        """
        # Use provided signer, instance signer, or account signer
        if signer is not None:
            order_data_list = [order.dump_to_dict() for order in orders]
            order_payloads = signer.sign_batch(order_data_list)
        elif self.signer is not None:
            order_data_list = [order.dump_to_dict() for order in orders]
            order_payloads = self.signer.sign_batch(order_data_list)
        else:
            # Fall back to account signing
            if self.account is None:
                raise ValueError("Account not initialized and no signer provided")
            order_payloads = []
            for order in orders:
                order.signature = self.account.sign_order(order)
                order_payload = order.dump_to_dict()
                order_payloads.append(order_payload)

        return self._post_authorized(path="orders/batch", payload=order_payloads)

    def modify_order(self, order_id: str, order: Order, signer: Signer | None = None) -> dict:
        """Modify an open order previously sent to Paradex from this account.
            Private endpoint requires authorization.

        Args:
            order_id: Order Id
            order: Order update
            signer: Optional custom signer. Uses instance signer or account signer if None.
        """
        # Use provided signer, instance signer, or account signer
        if signer is not None:
            order_data = order.dump_to_dict()
            signed_data = signer.sign_order(order_data)
            order_payload = signed_data
        elif self.signer is not None:
            order_data = order.dump_to_dict()
            signed_data = self.signer.sign_order(order_data)
            order_payload = signed_data
        else:
            # Fall back to account signing
            if self.account is None:
                raise ValueError("Account not initialized and no signer provided")
            order.signature = self.account.sign_order(order)
            order_payload = order.dump_to_dict()

        return self._put_authorized(path=f"orders/{order_id}", payload=order_payload)

    def cancel_order(self, order_id: str) -> None:
        """Cancel open order previously sent to Paradex from this account.
            Private endpoint requires authorization.

        Args:
            order_id: Order Id
        """
        self._delete_authorized(path=f"orders/{order_id}")

    def cancel_order_by_client_id(self, client_id: str) -> None:
        """Cancel open order previously sent to Paradex from this account.
            Private endpoint requires authorization.

        Args:
            client_id: Order id as assigned by a trader.
        """
        self._delete_authorized(path=f"orders/by_client_id/{client_id}")

    def cancel_all_orders(self, params: dict | None = None) -> None:
        """Cancel all open orders for specific market or for all markets.
            Private endpoint requires authorization.

        Args:
            params:
                `market`: Market Name\n
        """
        self._delete_authorized(path="orders", params=params)

    def cancel_orders_batch(
        self, order_ids: list[str] | None = None, client_order_ids: list[str] | None = None
    ) -> dict:
        """Cancel batch of orders by order IDs or client order IDs.
            Private endpoint requires authorization.

        Args:
            order_ids: List of order IDs assigned by Paradex
            client_order_ids: List of client-assigned order IDs

        Returns:
            results (list): List of cancellation results for each order
        """
        if not order_ids and not client_order_ids:
            raise_value_error(f"{self.classname}: Must provide either order_ids or client_order_ids")

        payload = {}
        if order_ids:
            payload["order_ids"] = order_ids
        if client_order_ids:
            payload["client_order_ids"] = client_order_ids

        return self._delete_authorized(path="orders/batch", payload=payload)

    # PUBLIC GET METHODS
    def fetch_system_config(self) -> SystemConfig:
        """Fetch Paradex system config.

        Examples:
            >>> paradex.api_client.fetch_system_config()
            >>> { ..., "paraclear_decimals": 8, ... }
        """

        res = self.request(
            url=f"{self.api_url}/system/config",
            http_method=HttpMethod.GET,
        )
        # Extract base URL from full URL if not provided in response
        if "starknet_fullnode_rpc_base_url" not in res and "starknet_fullnode_rpc_url" in res:
            base_url = re.sub(r"/rpc/v\d+[._]\d+.*$", "", res["starknet_fullnode_rpc_url"])
            res["starknet_fullnode_rpc_base_url"] = base_url
        config = SystemConfigSchema().load(res, unknown="exclude", partial=True)
        self.logger.info(f"{self.classname}: SystemConfig:{config}")
        return config

    def fetch_system_state(self) -> dict:
        """Fetch Paradex system status.

        Examples:
            >>> paradex.api_client.fetch_system_state()
            >>> { "status": "ok" }
        """
        return self._get(path="system/state")

    def fetch_system_time(self) -> dict:
        """Fetch Paradex system time.

        Examples:
            >>> paradex.api_client.fetch_system_time()
            >>> { "server_time": "1710956478221" }

        Returns:
            server_time: Paradex Server time
        """
        return self._get(path="system/time")

    def fetch_portfolio_margin_config(self, params: dict | None = None) -> dict:
        """Fetch Portfolio Margin configuration (per underlying).

        The response is the input expected by
        :func:`paradex_py.margin.compute` when
        ``margin_methodology="portfolio_margin"`` — it contains the live
        scenario set, vol-shock parameters, and hedged/unhedged margin factors
        that the engine refuses to default locally.

        Examples:
            >>> paradex.api_client.fetch_portfolio_margin_config()
            >>> { "results": [{"base_asset": "BTC", "scenarios": [...], ...}] }

        Returns:
            results (list): One entry per underlying.
        """
        return self._get(path="system/portfolio-margin-config", params=params)

    def fetch_markets(self, params: dict | None = None) -> dict:
        """Fetch all markets information.

        Args:
            params:
                `market`: Market Name\n

        Returns:
            results (list): List of Markets
        """
        return self._get(path="markets", params=params)

    def fetch_markets_summary(self, params: dict | None = None) -> dict:
        """Fetch ticker information for specific market.

        Args:
            params:
                `end`: End Time (unix time millisecond)\n
                `market`: Name of the market for which summary is requested (for all available markets use ALL)\n
                `start`: Start Time (unix time millisecond)\n

        Returns:
            results (list): List of Market Summaries
        """
        return self._get(path="markets/summary", params=params)

    def fetch_klines(
        self, symbol: str, resolution: str, start_at: int, end_at: int, price_kind: str | None = None
    ) -> dict:
        """Fetch OHLCV candlestick data for a symbol.

        Args:
            symbol: Symbol of the market pair
            resolution: Resolution in minutes: 1, 3, 5, 15, 30, 60
            start_at: Start time for klines in milliseconds
            end_at: End time for klines in milliseconds
            price_kind: Which price to use for the klines (optional)

        Returns:
            List of OHLCV candlestick data
        """
        params = {
            "symbol": symbol,
            "resolution": resolution,
            "start_at": start_at,
            "end_at": end_at,
        }
        if price_kind:
            params["price_kind"] = price_kind
        return self._get(path="markets/klines", params=params)

    def fetch_orderbook(self, market: str, params: dict | None = None) -> dict:
        """Fetch order-book for specific market.

        Args:
            market: Market Name
            params:
                `depth`: Depth
        """
        return self._get(path=f"orderbook/{market}", params=params)

    def fetch_bbo(self, market: str) -> dict:
        """Fetch best bid/offer for specific market.

        Args:
            market: Market Name
        """
        return self._get(path=f"bbo/{market}")

    def fetch_insurance_fund(self) -> dict:
        """Fetch insurance fund information"""
        return self._get(path="insurance")

    # ALGO ORDERS
    def submit_algo_order(
        self,
        order: Order,
        algo_type: str,
        duration_seconds: int,
        frequency: int | None = None,
        signer: Signer | None = None,
    ) -> dict:
        """Submit an algo order (e.g. TWAP) to Paradex.
            Private endpoint requires authorization.

        Args:
            order: Order with type=MARKET, price=0, containing market/side/size.
            algo_type: Algo type (e.g. "TWAP").
            duration_seconds: Duration in seconds (30-86400, multiple of 30).
            frequency: Interval in seconds between child orders (default: 30).
            signer: Optional custom signer. Uses instance signer or account signer if None.

        Returns:
            Algo order response dict.
        """
        # Sign the order
        if signer is not None:
            order_data = order.dump_to_dict()
            signed_data = signer.sign_order(order_data)
            signature = signed_data["signature"]
            signature_timestamp = signed_data["signature_timestamp"]
        elif self.signer is not None:
            order_data = order.dump_to_dict()
            signed_data = self.signer.sign_order(order_data)
            signature = signed_data["signature"]
            signature_timestamp = signed_data["signature_timestamp"]
        else:
            if self.account is None:
                raise ValueError("Account not initialized and no signer provided")
            order.signature = self.account.sign_order(order)
            signature = order.signature
            signature_timestamp = order.signature_timestamp

        payload: dict[str, Any] = {
            "market": order.market,
            "side": order.order_side.value,
            "type": order.order_type.value,
            "size": str(order.size),
            "algo_type": algo_type,
            "duration_seconds": duration_seconds,
            "signature": signature,
            "signature_timestamp": signature_timestamp,
        }
        if frequency is not None:
            payload["frequency"] = frequency
        if order.recv_window is not None:
            payload["recv_window"] = order.recv_window

        return self._post_authorized(path="algo/orders", payload=payload)

    def fetch_algo_orders(self, params: dict | None = None) -> dict:
        """Fetch algo orders for the account.
            Private endpoint requires authorization.

        Args:
            params:
                `market`: Market name\n
                `status`: Algo order status\n

        Returns:
            results (list): List of algo orders
        """
        return self._get_authorized(path="algo/orders", params=params)

    def cancel_algo_order(self, algo_order_id: str) -> None:
        """Cancel an algo order.
            Private endpoint requires authorization.

        Args:
            algo_order_id: Algo order ID
        """
        self._delete_authorized(path=f"algo/orders/{algo_order_id}")
