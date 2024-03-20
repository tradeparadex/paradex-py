import logging
import time
from typing import Any, Dict, List, Optional, Union

from paradex_py.account.account import ParadexAccount
from paradex_py.api.http_client import HttpClient, HttpMethod
from paradex_py.api.models import AccountSummary, AccountSummarySchema, AuthSchema, SystemConfig, SystemConfigSchema
from paradex_py.common.order import Order
from paradex_py.environment import Environment


class ParadexApiClient(HttpClient):
    """Class to interact with Paradex REST API.
        Initialized along with `Paradex` class.

    Args:
        env (Environment): Environment
        logger (logging.Logger, optional): Logger. Defaults to None.

    Examples:
        >>> from paradex_py import Paradex
        >>> from paradex_py.environment import Environment
        >>> paradex = Paradex(env=Environment.TESTNET)
    """

    classname: str = "ParadexApiClient"

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
        self.logger.info(f"{self.classname}: JWT:{data.jwt_token}")

    def _validate_auth(self):
        if self.account is None:
            raise ValueError("{self.classname}: Account not found")
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
    def fetch_orders(self, params: Optional[Dict] = None) -> Dict:
        """Fetch open orders for the account.
            Private endpoint requires authorization.

        Args:
            params:
                `market`: Market for the order\n

        Returns:
            results (list): Orders list
        """
        return self._get_authorized(path="orders", params=params)

    def fetch_orders_history(self, params: Optional[Dict] = None) -> Dict:
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

    def fetch_order(self, order_id: str) -> Dict:
        """Fetch a state of specific order sent from this account.
            Private endpoint requires authorization.

        Args:
            order_id: order's id as assigned by Paradex.
        """
        return self._get_authorized(path=f"orders/{order_id}")

    def fetch_order_by_client_id(self, client_id: str) -> Dict:
        """Fetch a state of specific order sent from this account.
            Private endpoint requires authorization.

        Args:
            client_id: order's client_id as assigned by a trader.
        """
        return self._get_authorized(path=f"orders/by_client_id/{client_id}")

    def fetch_fills(self, params: Optional[Dict] = None) -> Dict:
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

    def fetch_tradebusts(self, params: Optional[Dict] = None) -> Dict:
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

    def fetch_funding_payments(self, params: Optional[Dict] = None) -> Dict:
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

    def fetch_transactions(self, params: Optional[Dict] = None) -> Dict:
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

    def fetch_transfers(self, params: Optional[Dict] = None) -> Dict:
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
        return AccountSummarySchema().load(res)

    def fetch_account_profile(self) -> Dict:
        """Fetch profile for this account.
        Private endpoint requires authorization.
        """
        return self._get_authorized(path="account/profile")

    def fetch_balances(self) -> Dict:
        """Fetch all coin balances for this account.
            Private endpoint requires authorization.

        Returns:
            results (list): List of Balances
        """
        return self._get_authorized(path="balance")

    def fetch_positions(self) -> Dict:
        """Fetch all derivatives positions for this account.
            Private endpoint requires authorization.

        Returns:
            next (str): The pointer to fetch next set of records (null if there are no records left)
            prev (str): The pointer to fetch previous set of records (null if there are no records left)
            results (list): List of Positions
        """
        return self._get_authorized(path="positions")

    def fetch_points_data(self, market: str, program: str) -> Dict:
        """Fetch points program data for specific market.
            Private endpoint requires authorization.

        Args:
            market: Market Name
            program: Program Name - example: LiquidityProvider, Trader

        Returns:
            results (list): List of points data
        """
        return self._get_authorized(path=f"points_data/{market}/{program}")

    def fetch_liquidations(self, params: Optional[Dict] = None) -> Dict:
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

    def fetch_trades(self, params: Dict) -> Dict:
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
            raise ValueError(f"{self.classname}: Market is required to fetch trades")
        return self._get(path="trades", params=params)

    def submit_order(self, order: Order) -> Dict:
        """Send order to Paradex.
            Private endpoint requires authorization.

        Args:
            order: Order containing all required fields.
        """
        order.signature = self.account.sign_order(order)
        order_payload = order.dump_to_dict()
        return self._post_authorized(path="orders", payload=order_payload)

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

    def cancel_all_orders(self, params: Optional[Dict] = None) -> None:
        """Cancel all open orders for specific market or for all markets.
            Private endpoint requires authorization.

        Args:
            params:
                `market`: Market Name\n
        """
        self._delete_authorized(path="orders", params=params)

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
        config = SystemConfigSchema().load(res)
        self.logger.info(f"{self.classname}: SystemConfig:{config}")
        return config

    def fetch_system_state(self) -> Dict:
        """Fetch Paradex system status.

        Examples:
            >>> paradex.api_client.fetch_system_state()
            >>> { "status": "ok" }
        """
        return self._get(path="system/state")

    def fetch_system_time(self) -> Dict:
        """Fetch Paradex system time.

        Examples:
            >>> paradex.api_client.fetch_system_time()
            >>> { "server_time": "1710956478221" }

        Returns:
            server_time: Paradex Server time
        """
        return self._get(path="system/time")

    def fetch_markets(self, params: Optional[Dict] = None) -> Dict:
        """Fetch all markets information.

        Args:
            params:
                `market`: Market Name\n

        Returns:
            results (list): List of Markets
        """
        return self._get(path="markets", params=params)

    def fetch_markets_summary(self, params: Optional[Dict] = None) -> Dict:
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

    def fetch_orderbook(self, market: str, params: Optional[Dict] = None) -> Dict:
        """Fetch order-book for specific market.

        Args:
            market: Market Name
            params:
                `depth`: Depth
        """
        return self._get(path=f"orderbook/{market}", params=params)

    def fetch_bbo(self, market: str) -> Dict:
        """Fetch best bid/offer for specific market.

        Args:
            market: Market Name
        """
        return self._get(path=f"bbo/{market}")

    def fetch_insurance_fund(self) -> Dict:
        """Fetch insurance fund information"""
        return self._get(path="insurance")
