import logging
import time
from typing import Any, Dict, List, Optional, Union

from paradex_py.account.account import ParadexAccount
from paradex_py.api.http_client import HttpClient, HttpMethod
from paradex_py.api.models import AccountSummary, AccountSummarySchema, AuthSchema, SystemConfig, SystemConfigSchema
from paradex_py.common.order import Order
from paradex_py.environment import Environment


def validate_market(func):
    def wrapper(self, *args, **kwargs):
        if "params" in kwargs and kwargs["params"].get("market"):
            return func(self, *args, **kwargs)
        if not args:
            raise ValueError("ParadexApiClient: no parameters while market is required")
        if not isinstance(args[0], dict):
            raise TypeError(f"ParadexApiClient: '{args}' first item should be dict.")
        if not args[0].get("market"):
            raise ValueError(f"ParadexApiClient: '{args}' first item should contain 'market' key.")
        return func(self, *args, **kwargs)

    return wrapper


class ParadexApiClient(HttpClient):
    """ParadexApiClient class to interact with Paradex API.
    Initialized along with Paradex class.

    Args:
        env (Environment): Environment
        logger (logging.Logger, optional): Logger. Defaults to None.

    Examples:
        >>> from paradex_py import Paradex
        >>> from paradex_py.environment import Environment
        >>> paradex = Paradex(env=Environment.TESTNET)
        >>> paradex.ws_client.connect()
    """

    def __init__(
        self,
        env: Environment,
        logger: Optional[logging.Logger] = None,
    ):
        self.env = env
        self.logger = logger or logging.getLogger(__name__)
        super().__init__()
        self.api_url = f"https://api.{self.env}.paradex.trade/v1"

    async def __aexit__(self):
        await self.client.close()

    def load_system_config(self) -> SystemConfig:
        res = self.request(
            url=f"{self.api_url}/system/config",
            http_method=HttpMethod.GET,
        )
        self.logger.info(f"ParadexApiClient: /system/config:{res}")
        config = SystemConfigSchema().load(res)
        self.logger.info(f"ParadexApiClient: SystemConfig:{config}")
        return config

    def init_account(self, account: ParadexAccount):
        self.account = account
        self.onboarding()
        self.auth()

    def onboarding(self):
        headers = self.account.onboarding_headers()
        payload = {"public_key": hex(self.account.l2_public_key)}
        self.post(api_url=self.api_url, path="onboarding", headers=headers, payload=payload)

    def auth(self):
        headers = self.account.auth_headers()
        res = self.post(api_url=self.api_url, path="auth", headers=headers)
        data = AuthSchema().load(res)
        self.auth_timestamp = time.time()
        self.account.set_jwt_token(data.jwt_token)
        self.client.headers.update({"Authorization": f"Bearer {data.jwt_token}"})
        self.logger.info(f"ParadexApiClient: JWT:{data.jwt_token}")

    def _validate_auth(self):
        if self.account is None:
            raise ValueError("ParadexApiClient: Account not found")
        # Refresh JWT if it's older than 4 minutes
        if time.time() - self.auth_timestamp > 4 * 60:
            self.auth(headers=self.account.auth_headers())

    def _get(self, path: str, params: Optional[dict] = None) -> dict:
        return self.get(api_url=self.api_url, path=path, params=params)

    def _get_authorized(self, path: str, params: Optional[dict] = None) -> dict:
        self._validate_auth()
        return self._get(path=path, params=params)

    def _post_authorized(
        self,
        path: str,
        payload: Optional[Union[Dict[str, Any], List[Dict[str, Any]]]] = None,
        params: Optional[dict] = None,
        headers: Optional[dict] = None,
    ) -> dict:
        self._validate_auth()
        return self.post(api_url=self.api_url, path=path, payload=payload, params=params, headers=headers)

    def _delete_authorized(self, path: str, params: Optional[dict] = None) -> dict:
        self._validate_auth()
        return self.delete(api_url=self.api_url, path=path, params=params)

    # PRIVATE GET METHODS

    def fetch_orders(self, params: Optional[Dict] = None) -> Dict[Any, Any]:
        """Fetch open orders for the account.
            Private call requires authorization.

        Args:
            params (dict): optional dictionary with additional parameters. Possible keys are:
                market (str): instrument symbol. If empty then fetch orders for all markets.
        Returns:
            Dict:
                results - a list of dictionaries, each dict represent an order.
        """
        return self._get_authorized(path="orders", params=params)

    def fetch_orders_history(self, params: Optional[Dict] = None) -> Dict[Any, Any]:
        """Fetch history of orders for the account.
            Private call requires authorization.
            See https://docs.api.prod.paradex.trade/?shell#get-orders for details.
        Args:
            params (dict): optional dictionary with additional parameters. Possible keys are:
                market (str): instrument symbol. If None or empty then fetch history of orders for all markets.
                cursor (string):    Returns the `next` paginated page.
                start_at (int):     Start Time in unix time milliseconds.
                end_at (int):       End Time in unix time milliseconds.
                page_size (int):    Limit the number of responses in the page.
                client_id (str):	Unique ID of order generated by a client
                side (str): 	    Order side
                status (str):       Order status
                type (str):         Order type
        Returns:
            Dict: with fields
                next, prev - pagination tokens
                results - a list of dictionaries, each dict representing an order.
        """
        return self._get_authorized(path="orders-history", params=params)

    def fetch_order(self, order_id: str) -> Dict[Any, Any]:
        """Fetch a state of specific order sent from this account.
            Private call requires authorization.

        Args:
            order_id (str): order's id as assigned by Paradex.
        Returns:
            Dict: dictionary representing an order.
        """
        return self._get_authorized(path=f"orders/{order_id}")

    def fetch_order_by_client_id(self, client_id: str) -> Dict[Any, Any]:
        """Fetch a state of specific order sent from this account.
            Private call requires authorization.

        Args:
            client_id (str): order's client_id as assigned by a trader.
        Returns:
            Dict: dictionary representing an order.
        """
        return self._get_authorized(path=f"orders/by_client_id/{client_id}")

    def fetch_fills(self, params: Optional[Dict] = None) -> Dict[Any, Any]:
        """Fetch history of fills for this account.
            Private call requires authorization.

        Args:
            params (dict): optional dictionary with additional parameters. Possible keys are:
                market (str): instrument symbol. If None or empty then fetch fills for all markets.
                cursor (string):    Returns the `next` paginated page.
                start_at (int):     Start Time in unix time milliseconds.
                end_at (int):       End Time in unix time milliseconds.
                page_size (int):    Limit the number of responses in the page.
        Returns:
            Dict: with fields
                next, prev - pagination tokens
                results - a list of dictionaries, each dict representing a fill.
        """
        return self._get_authorized(path="fills", params=params)

    def fetch_tradebusts(self, params: Optional[Dict] = None) -> Dict[Any, Any]:
        """Fetch history of tradebusts for this account.
            Private call requires authorization.

        Args:
            params (dict): optional dictionary with additional parameters. Possible keys are:
                cursor (string):    Returns the `next` paginated page.
                start_at (int):     Start Time in unix time milliseconds.
                end_at (int):       End Time in unix time milliseconds.
                page_size (int):    Limit the number of responses in the page.
        Returns:
            Dict: with fields
                next, prev - pagination tokens
                results - a list of dictionaries, each dict representing a tradebust.
        """
        return self._get_authorized(path="tradebusts", params=params)

    def fetch_funding_payments(self, params: Optional[Dict] = None) -> Dict[Any, Any]:
        """Fetch history of funding payments for this account.
            Private call requires authorization.

        Args:
            params (dict): optional dictionary with additional parameters. Possible keys are:
                market (str): instrument symbol. If 'ALL' then fetch funding payments for all markets.
                cursor (string):    Returns the `next` paginated page.
                start_at (int):     Start Time in unix time milliseconds.
                end_at (int):       End Time in unix time milliseconds.
                page_size (int):    Limit the number of responses in the page.
        Returns:
            Dict: with fields
                next, prev - pagination tokens
                results - a list of dictionaries, each dict representing a funding payment.
        """
        return self._get_authorized(path="funding/payments", params=params)

    def fetch_transactions(self, params: Optional[Dict] = None) -> Dict[Any, Any]:
        """Fetch history of transactions initiated by this account.
            Private call requires authorization.
        Args:
            params (dict): optional dictionary with additional parameters. Possible keys are:
                cursor (str):    Returns the `next` paginated page.
                start_at (int):  Start Time in unix time milliseconds.
                end_at (int):    End Time in unix time milliseconds.
                page_size (int): Limit the number of responses in the page.
        Returns:
            Dict: with fields
                next, prev - pagination tokens
                results - a list of dictionaries, each dict representing a transaction.
        """
        return self._get_authorized(path="transactions", params=params)

    def fetch_account_summary(self) -> AccountSummary:
        """Fetch current summary for this account.
            Private call requires authorization.

        Returns:
            AccountSummary: object with fields representing account summary.
        """
        res = self._get_authorized(path="account")
        return AccountSummarySchema().load(res)

    def fetch_account_profile(self) -> Dict[Any, Any]:
        """Fetch profile for this account.
            Private call requires authorization.

        Returns:
            dictionary with fields representing account profile.
        """
        return self._get_authorized(path="account/profile")

    def fetch_balances(self) -> Dict[Any, Any]:
        """Fetch all coin balances for this account.
            Private call requires authorization.

        Returns:
            Dict: with fields
                next, prev - pagination tokens
                results - a list of dictionaries, each dict representing a balance in specific coin.
        """
        return self._get_authorized(path="balance")

    def fetch_positions(self) -> Dict[Any, Any]:
        """Fetch all derivatives positions for this account
            Private call requires authorization.

        Returns:
            Dict: with fields
                next, prev - pagination tokens
                results - a list of dictionaries, each dict representing a position.
        """
        return self._get_authorized(path="positions")

    # PUBLIC GET METHODS
    def fetch_markets(self, params: Optional[Dict] = None) -> Dict[Any, Any]:
        """Fetch all markets information
            Public call, no authorization required.
        Args:
            params (dict): optional dictionary with additional parameters. Possible keys are:
                market (str): instrument symbol.
        Returns:
            Dict: with fields
                results - a list of dictionaries, each dict representing a market
        """
        return self._get(path="markets", params=params)

    def fetch_markets_summary(self, params: Optional[Dict] = None) -> Dict[Any, Any]:
        """Fetch ticker information for specific market
            Public call, no authorization required.

        Args:
            params (dict): optional dictionary with additional parameters. Possible keys are:
                market (str): instrument symbol. If 'ALL' then fetch latest tickers for all markets.
                start (int): when market <> 'ALL' - start time in milliseconds since epoch.
                end (int): when market <> 'ALL' - end time in milliseconds since epoch.
        Returns:
            Dict: with fields
                results - a list of dictionaries, each dict representing a ticker for specific market and timestamp.
        """
        return self._get(path="markets/summary", params=params)

    def fetch_orderbook(self, market: str, params: Optional[Dict] = None) -> Dict[Any, Any]:
        """Fetch order-book for specific market
            Public call, no authorization required.

        Args:
            market (str): MANDATORY. instrument symbol.
            params (dict): optional dictionary with additional parameters. Possible keys are:
                depth (int): Depth of the order book. Default is 20.
        Returns:
            Dict: dictionary representing a full order book depth for specific market
        """
        return self._get(path=f"orderbook/{market}", params=params)

    def fetch_bbo(self, market: str) -> Dict[Any, Any]:
        """Fetch best bid/offer for specific market
            Public call, no authorization required.

        Args:
            market (str): MANDATORY. instrument symbol.
        Returns:
            Dict: dictionary representing best bid/offer for specific market
        """
        return self._get(path=f"bbo/{market}")

    def fetch_insurance_fund(self) -> Dict[Any, Any]:
        """Fetch insurance fund information
            Public call, no authorization required.

        Returns:
            Dict: dictionary representing a state of Paradex Insurance Fund
        """
        return self._get(path="insurance")

    def fetch_liquidations(self, params: Optional[Dict]) -> Dict[Any, Any]:
        """Fetch hisotry of liquidations for this account.
            Private call requires authorization.

        Args:
            params (dict): optional dictionary with additional parameters. Possible keys are:
                start (int): start time in milliseconds since epoch.
                end (int): end time in milliseconds since epoch.
        Returns:
            Dict: with fields
                results - a list of dictionaries, each dict representing a liquidation event.
        """
        return self._get(path="liquidations")

    @validate_market
    def fetch_trades(self, params: Dict) -> Dict[Any, Any]:
        """Fetch Paradex exchange trades for specific market
            Public call, no authorization required.

        Args:
            params (dict): MANDATORY dictionary with additional parameters. Possible keys are:
                market (str): MANDATORY, instrument's symbol.
        Returns:
            Dict: with fields
                next, prev - pagination tokens
                results - a list of dictionaries, each dict representing a trade.
        """
        return self._get(path="trades", params=params)

    # order helper functions
    def submit_order(self, order: Order) -> Dict[Any, Any]:
        """Send order to Paradex
            Private call requires authorization.

        Args:
            order (Order): Order object
        Returns:
            Dict: dictionary representing a response from Paradex API
        """
        order.signature = self.account.sign_order(order)
        order_payload = order.dump_to_dict()
        return self._post_authorized(path="orders", payload=order_payload)

    def cancel_order(self, order_id: str) -> None:
        """Cancel open order previously sent to Paradex from this account.
            Private call requires authorization.

        Args:
            order_id (str): Order id as assigned by Paradex.
        Returns:
            None
        """
        self._delete_authorized(path=f"orders/{order_id}")

    def cancel_order_by_client_id(self, client_id: str) -> None:
        """Cancel open order previously sent to Paradex from this account.
            Private call requires authorization.

        Args:
            client_id (str): Order id as assigned by a trader.
        Returns:
            None
        """
        self._delete_authorized(path=f"orders/by_client_id/{client_id}")

    def cancel_all_orders(self, params: Optional[Dict] = None) -> None:
        """Cancel all open orders for specific market or for all markets.
            Private call requires authorization.

        Args:
            params (dict): dictionary with additional parameters. Possible keys are:
                market (str): instrument's symbol.
        Returns:
            None
        """
        self._delete_authorized(path="orders", params=params)
