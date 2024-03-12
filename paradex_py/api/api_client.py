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

    def _delete_authorized(self, path: str) -> dict:
        self._validate_auth()
        return self.delete(api_url=self.api_url, path=path)

    # PRIVATE GET METHODS

    def fetch_orders(self, params: Optional[Dict] = None) -> Optional[List]:
        """Fetch open orders for the account.
            Private call requires authorization.

        Args:
            params (dict): optional dictionary with additional parameters. Possible keys are:
                market (str): instrument symbol. If empty then fetch orders for all markets.
        Returns:
            None: if received invalid response from Paradex API.
            List: list of dictionaries, each dict represent an order.
        """
        response = self._get_authorized(path="orders", params=params)
        return response.get("results") if response else None

    def fetch_orders_history(self, params: Optional[Dict] = None) -> Optional[List]:
        """Fetch history of orders for the account.
            Private call requires authorization.

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
            See https://docs.api.prod.paradex.trade/?shell#get-orders for details.
        Returns:
            None: if received invalid response from Paradex API.
            List: list of dictionaries, each dict representing an order.
        """
        response = self._get_authorized(path="orders-history", params=params)
        return response.get("results") if response else None

    def fetch_order(self, order_id: str) -> Optional[Dict]:
        """Fetch a state of specific order sent from this account.
            Private call requires authorization.

        Args:
            order_id (str): order's id as assigned by Paradex.
        Returns:
            None: if received invalid response from Paradex API.
            Dict: dictionary representing an order.
        """
        path: str = f"orders/{order_id}"
        return self._get_authorized(path=path)

    def fetch_order_by_client_id(self, client_id: str) -> Optional[Dict]:
        """Fetch a state of specific order sent from this account.
            Private call requires authorization.

        Args:
            client_id (str): order's client_id as assigned by a trader.
        Returns:
            None: if received invalid response from Paradex API.
            Dict: dictionary representing an order.
        """
        path: str = f"orders/by_client_id/{client_id}"
        return self._get_authorized(path=path)

    def fetch_fills(self, params: Optional[Dict] = None) -> Optional[List]:
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
            None: if received invalid response from Paradex API.
            List: list of dictionaries, each dict representing a fill.
        """
        response = self._get_authorized(path="fills", params=params)
        return response.get("results") if response else None

    def fetch_funding_payments(self, params: Optional[Dict] = None) -> Optional[List]:
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
            None: if received invalid response from Paradex API.
            List: list of dictionaries, each dict representing a funding payment.
        """
        response = self._get_authorized(path="funding/payments", params=params)
        return response.get("results") if response else None

    def fetch_transactions(self, params: Optional[Dict] = None) -> Optional[List]:
        """Fetch history of transactions initiated by this account.
            Private call requires authorization.
        Args:
            params (dict): optional dictionary with additional parameters. Possible keys are:
                cursor (str):    Returns the `next` paginated page.
                start_at (int):  Start Time in unix time milliseconds.
                end_at (int):    End Time in unix time milliseconds.
                page_size (int): Limit the number of responses in the page.
        Returns:
            None: if received invalid response from Paradex API.
            List: list of dictionaries, each dict representing a transaction.
        """
        response = self._get_authorized(path="transactions", params=params)
        return response.get("results") if response else None

    def fetch_account_summary(self) -> AccountSummary:
        """Fetch current summary for this account.
            Private call requires authorization.

        Returns:
            AccountSummary: object with fields representing account summary.
        """
        res = self._get_authorized(path="account")
        return AccountSummarySchema().load(res)

    def fetch_account_profile(self) -> Optional[Dict]:
        """Fetch profile for this account.
            Private call requires authorization.

        Returns:
            dictionary with fields representing account profile.
        """
        res = self._get_authorized(path="account/profile")
        return res

    def fetch_balances(self) -> Optional[List]:
        """Fetch all coin balances for this account.
            Private call requires authorization.

        Returns:
            None: if received invalid response from Paradex API.
            List: list of dictionaries, each dict representing a balance in specific coin.
        """
        response = self._get_authorized(path="balance")
        return response.get("results") if response else None

    def fetch_positions(self) -> Optional[List]:
        """Fetch all derivatives positions for this account
            Private call requires authorization.

        Returns:
            None: if received invalid response from Paradex API
            List: list of dictionaries, each dict representing a position in specific instrument
        """
        response = self._get_authorized(path="positions")
        return response.get("results") if response else None

    # PUBLIC GET METHODS
    def fetch_markets(self, params: Optional[Dict] = None) -> Optional[List]:
        """Fetch all markets information
            Public call, no authorization required.
        Args:
            params (dict): optional dictionary with additional parameters. Possible keys are:
                market (str): instrument symbol.
        Returns:
            None: if received invalid response from Paradex API
            List: list of dictionaries, each dict representing a market
        """
        response = self._get(path="markets", params=params)
        return response.get("results") if response else None

    def fetch_markets_summary(self, params: Optional[Dict] = None) -> Optional[List]:
        """Fetch ticker information for specific market
            Public call, no authorization required.

        Args:
            params (dict): optional dictionary with additional parameters. Possible keys are:
                market (str): instrument symbol. If 'ALL' then fetch latest tickers for all markets.
                start (int): when market <> 'ALL' - start time in milliseconds since epoch.
                end (int): when market <> 'ALL' - end time in milliseconds since epoch.
        Returns:
            None: if received invalid response from Paradex API.
            List: list of dictionaries, each dict representing a ticker for specific market and timestamp.
        """
        response = self._get(path="markets/summary", params=params)
        return response.get("results") if response else None

    def fetch_orderbook(self, market: str, params: Optional[Dict] = None) -> dict:
        """Fetch order-book for specific market
            Public call, no authorization required.

        Args:
            market (str): MANDATORY. instrument symbol.
            params (dict): optional dictionary with additional parameters. Possible keys are:
                depth (int): Depth of the order book. Default is 20.
        Returns:
            None: if received invalid response from Paradex API
            Dict: dictionary representing a full order book depth for specific market
        """
        return self._get(path=f"orderbook/{market}", params=params)

    def fetch_insurance_fund(self) -> Optional[Dict[Any, Any]]:
        """Fetch insurance fund information
            Public call, no authorization required.

        Returns:
            None: if received invalid response from Paradex API
            Dict: dictionary representing a state of Paradex Insurance Fund
        """
        return self._get(path="insurance")

    @validate_market
    def fetch_trades(self, params: Optional[Dict]) -> Optional[List]:
        """Fetch Paradex exchange trades for specific market
            Public call, no authorization required.

        Args:
            market (str): instrument symbol.
        Returns:
            None: if received invalid response from Paradex API
            Dict: list of dictionaries, dictionary representing a state of Paradex Insurance Fund
        """
        response = self._get(path="trades", params=params)
        return response.get("results") if response else None

    # order helper functions
    def submit_order(self, order: Order) -> Optional[Dict]:
        """Send order to Paradex
            Private call requires authorization.

        Args:
            order (Order): Order object
        Returns:
            None: if received invalid response from Paradex API
            Dict: dictionary representing a response from Paradex API
        """
        response = None
        order.signature = self.account.sign_order(order)
        order_payload = order.dump_to_dict()
        try:
            response = self._post_authorized(path="orders", payload=order_payload)
        except Exception:
            self.logger.exception(f"submit_order payload:{order_payload}")
        return response

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
