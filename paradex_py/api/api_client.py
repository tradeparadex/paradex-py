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
        >>> paradex.api_client.fetch_system_state()
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
        """Fetch open orders for the account.<br>
            Private call requires authorization.<br>
            See [Get open orders](https://docs.api.prod.paradex.trade/?shell#get-open-orders)
            for details.<br>

        Args:
            params: dictionary with parameters. Valid keys:<br>
                `market` (str): instrument symbol. If empty then fetch orders for all markets.<br>

        Returns:
            dictionary with fields:<br>
                `results` - a list of dictionaries, each dict represent an order.<br>
        """
        return self._get_authorized(path="orders", params=params)

    def fetch_orders_history(self, params: Optional[Dict] = None) -> Dict[Any, Any]:
        """Fetch history of orders for the account.<br>
            Private call requires authorization.<br>
            See [Get orders](https://docs.api.prod.paradex.trade/?shell#get-orders) for details.<br>

        Args:
            params: dictionary with parameters. Valid keys:<br>
                `market` (str): instrument symbol. If None or empty then fetch history of orders for all markets.<br>
                `cursor` (string):    Returns the `next` paginated page.<br>
                `start_at` (int):     Start Time in unix time milliseconds.<br>
                `end_at` (int):       End Time in unix time milliseconds.<br>
                `page_size` (int):    Limit the number of responses in the page.<br>
                `client_id` (str):	  Unique ID of order generated by a client.<br>
                `side` (str): 	      Order side.<br>
                `status` (str):       Order status.<br>
                `type` (str):         Order type.<br>

        Returns:
            dictionary with fields:<br>
                `next`, `prev` - pagination tokens.<br>
                `results` - a list of dictionaries, each dict representing an order.<br>
        """
        return self._get_authorized(path="orders-history", params=params)

    def fetch_order(self, order_id: str) -> Dict[Any, Any]:
        """Fetch a state of specific order sent from this account.<br>
            Private call requires authorization.<br>
            See [Get order](https://docs.api.prod.paradex.trade/?shell#get-order)
            for details.<br>

        Args:
            order_id: order's id as assigned by Paradex.<br>

        Returns:
            dictionary representing an order.<br>
        """
        return self._get_authorized(path=f"orders/{order_id}")

    def fetch_order_by_client_id(self, client_id: str) -> Dict[Any, Any]:
        """Fetch a state of specific order sent from this account.<br>
            Private call requires authorization.<br>
            See [Get order by client id](https://docs.api.prod.paradex.trade/?shell#get-order-by-client-id)
            for details.<br>

        Args:
            client_id: order's client_id as assigned by a trader.<br>

        Returns:
            dictionary representing an order.<br>
        """
        return self._get_authorized(path=f"orders/by_client_id/{client_id}")

    def fetch_fills(self, params: Optional[Dict] = None) -> Dict[Any, Any]:
        """Fetch history of fills for this account.<br>
            Private call requires authorization.<br>
            See [List fills](https://docs.api.prod.paradex.trade/?shell#list-fills)
            for details.<br>

        Args:
            params: dictionary with parameters. Valid keys:<br>
                `market` (str): instrument symbol. If None or empty then fetch fills for all markets.<br>
                `cursor` (string):    Returns the `next` paginated page.<br>
                `start_at` (int):     Start Time in unix time milliseconds.<br>
                `end_at` (int):       End Time in unix time milliseconds.<br>
                `page_size` (int):    Limit the number of responses in the page.<br>

        Returns:
            dictionary with fields:<br>
                `next`, `prev` - pagination tokens.<br>
                `results` - a list of dictionaries, each dict representing a fill.<br>
        """
        return self._get_authorized(path="fills", params=params)

    def fetch_tradebusts(self, params: Optional[Dict] = None) -> Dict[Any, Any]:
        """Fetch history of tradebusts for this account.<br>
            Private call requires authorization.<br>
            See [List tradebusts](https://docs.api.prod.paradex.trade/?shell#list-tradebusts) for details.<br>

        Args:
            params: dictionary with parameters. Valid keys:<br>
                `cursor` (string):    Returns the `next` paginated page.<br>
                `start_at` (int):     Start Time in unix time milliseconds.<br>
                `end_at` (int):       End Time in unix time milliseconds.<br>
                `page_size` (int):    Limit the number of responses in the page.<br>

        Returns:
            dictionary with fields:<br>
                `next`, `prev` - pagination tokens.<br>
                `results` - a list of dictionaries, each dict representing a tradebust.<br>
        """
        return self._get_authorized(path="tradebusts", params=params)

    def fetch_funding_payments(self, params: Optional[Dict] = None) -> Dict[Any, Any]:
        """Fetch history of funding payments for this account.<br>
            Private call requires authorization.<br>
            See [Funding Payments History](https://docs.api.prod.paradex.trade/?shell#funding-payments-history)
            for details.<br>

        Args:
            params: dictionary with parameters. Valid keys:<br>
                `market` (str): instrument symbol. If 'ALL' then fetch funding payments for all markets.<br>
                `cursor` (string):    Returns the `next` paginated page.<br>
                `start_at` (int):     Start Time in unix time milliseconds.<br>
                `end_at` (int):       End Time in unix time milliseconds.<br>
                `page_size` (int):    Limit the number of responses in the page.<br>

        Returns:
            dictionary with fields:<br>
                `next`, `prev` - pagination tokens.<br>
                `results` - a list of dictionaries, each dict representing a funding payment.<br>
        """
        return self._get_authorized(path="funding/payments", params=params)

    def fetch_transactions(self, params: Optional[Dict] = None) -> Dict[Any, Any]:
        """Fetch history of transactions initiated by this account.<br>
            Private call requires authorization.<br>
            See [List Transactions](https://docs.api.prod.paradex.trade/?shell#list-transactions)
            for details.<br>

        Args:
            params: dictionary with parameters. Valid keys:<br>
                `cursor` (string):    Returns the `next` paginated page.<br>
                `start_at` (int):     Start Time in unix time milliseconds.<br>
                `end_at` (int):       End Time in unix time milliseconds.<br>
                `page_size` (int):    Limit the number of responses in the page.<br>

        Returns:
            dictionary with fields:<br>
                `next`, `prev` - pagination tokens.<br>
                `results` - a list of dictionaries, each dict representing a transaction.<br>
        """
        return self._get_authorized(path="transactions", params=params)

    def fetch_transfers(self, params: Optional[Dict] = None) -> Dict[Any, Any]:
        """Fetch history of transfers initiated by this account.<br>
            Private call requires authorization.<br>
            See [List Account's transfers](https://docs.api.prod.paradex.trade/?shell#list-account-39-s-transfers-i-e-deposits-and-withdrawals)
            for details.<br>

        Args:
            params: dictionary with parameters. Valid keys:<br>
                `status` (str): get only transfers with specific status. Valid values are:<br>
                                'PENDING', 'AVAILABLE', 'COMPLETED', 'FAILED'.<br>
                `cursor` (string):    Returns the `next` paginated page.<br>
                `start_at` (int):     Start Time in unix time milliseconds.<br>
                `end_at` (int):       End Time in unix time milliseconds.<br>
                `page_size` (int):    Limit the number of responses in the page.<br>

        Returns:
            dictionary with fields:<br>
                `next`, `prev` - pagination tokens.<br>
                `results` - a list of dictionaries, each dict representing a transfer.<br>
        """
        return self._get_authorized(path="transfers", params=params)

    def fetch_account_summary(self) -> AccountSummary:
        """Fetch current summary for this account.<br>
            Private call requires authorization.<br>
            See [Get account information](https://docs.api.prod.paradex.trade/?shell#get-account-information)
            for details.<br>

        Returns:
            object with fields representing account summary.<br>
        """
        res = self._get_authorized(path="account")
        return AccountSummarySchema().load(res)

    def fetch_account_profile(self) -> Dict[Any, Any]:
        """Fetch profile for this account.<br>
            Private call requires authorization.<br>
            See [Get account profile information](https://docs.api.prod.paradex.trade/?shell#get-account-profile-information)
            for details.<br>

        Returns:
            dictionary with fields representing account profile.<br>
        """
        return self._get_authorized(path="account/profile")

    def fetch_balances(self) -> Dict[Any, Any]:
        """Fetch all coin balances for this account.<br>
            Private call requires authorization.<br>
            See [List balances](https://docs.api.prod.paradex.trade/?shell#list-balances) for details.<br>

        Returns:
            dictionary with fields:<br>
                `next`, `prev` - pagination tokens.<br>
                `results` - a list of dictionaries, each dict representing a balance in specific coin.<br>
        """
        return self._get_authorized(path="balance")

    def fetch_positions(self) -> Dict[Any, Any]:
        """Fetch all derivatives positions for this account.<br>
            Private call requires authorization.<br>
            See [List open positions](https://docs.api.prod.paradex.trade/?shell#list-open-positions) for details.<br>

        Returns:
            dictionary with fields:<br>
                `next`, `prev` - pagination tokens.<br>
                `results` - a list of dictionaries, each dict representing a position.<br>
        """
        return self._get_authorized(path="positions")

    def fetch_points_program(self, market: str, program: str) -> Dict[Any, Any]:
        """Fetch points program for specific market.<br>
            Private call requires authorization.<br>
            See [List latest points data](https://docs.api.prod.paradex.trade/?shell#list-latest-points-data) for details.<br>

        Args:
            market: instrument symbol.
            program: program name, can be 'LiquidityProvider' or 'Trader'.

        Returns:
            dictionary with fields:<br>
                `results` - a list of dictionaries, each dict representing a points program for specific market.<br>
        """
        return self._get_authorized(path=f"points_data/{market}/{program}")

    # PUBLIC GET METHODS
    def fetch_system_state(self) -> Dict[Any, Any]:
        """Fetch Paradex system status.<br>
            Public call, no authorization required.<br>
            See [Get system state](https://docs.api.prod.paradex.trade/?shell#get-system-state)
            for details.<br>

        Returns:
            dictionary with fields:<br>
                `status` representing a status of Paradex system.<br>
        """
        return self._get(path="system/state")

    def fetch_system_time(self) -> Dict[Any, Any]:
        """Fetch Paradex system time.<br>
            Public call, no authorization required.<br>
            See [Get system time (unix milliseconds)](https://docs.api.prod.paradex.trade/?shell#get-system-time-unix-milliseconds)
            for details.<br>

        Returns:
            dictionary with fields:<br>
                `server_time` holding Paradex system time in milliseconds since epoch, GMT timezone.<br>
        """
        return self._get(path="system/time")

    def fetch_markets(self, params: Optional[Dict] = None) -> Dict[Any, Any]:
        """Fetch all markets information.<br>
            Public call, no authorization required.<br>
            See [List available markets](https://docs.api.prod.paradex.trade/?shell#list-available-markets)
            for details.<br>

        Args:
            params: dictionary with parameters. Valid keys:<br>
                `market` (str): instrument symbol.

        Returns:
            dictionary with fields:<br>
                `results` - a list of dictionaries, each dict representing a market.<br>
        """
        return self._get(path="markets", params=params)

    def fetch_markets_summary(self, params: Optional[Dict] = None) -> Dict[Any, Any]:
        """Fetch ticker information for specific market.<br>
            Public call, no authorization required.<br>
            See [List available markets summary](https://docs.api.prod.paradex.trade/?shell#list-available-markets-summary)
            for details.<br>

        Args:
            params: dictionary with parameters. Valid keys:<br>
                `market` (str): instrument symbol. If 'ALL' then fetch latest tickers for all markets.<br>
                `start` (int): when market <> 'ALL' - start time in milliseconds since epoch.<br>
                `end` (int): when market <> 'ALL' - end time in milliseconds since epoch.<br>

        Returns:
            dictionary with fields:<br>
                `results` - a list of dictionaries, each dict representing a ticker for specific market and timestamp.<br>
        """
        return self._get(path="markets/summary", params=params)

    def fetch_orderbook(self, market: str, params: Optional[Dict] = None) -> Dict[Any, Any]:
        """Fetch order book for specific market.<br>
            Public call, no authorization required.<br>
            See [Get market orderbook](https://docs.api.prod.paradex.trade/?shell#get-market-orderbook)
            for details.<br>

        Args:
            market: instrument symbol.
            params: dictionary with additional parameters. Valid keys:<br>
                `depth` (int): Depth of the order book. Default is 20.<br>

        Returns:
            dictionary representing a full order book depth for specific market.<br>
        """
        return self._get(path=f"orderbook/{market}", params=params)

    def fetch_bbo(self, market: str) -> Dict[Any, Any]:
        """Fetch best bid/offer for specific market.<br>
            Public call, no authorization required.<br>
            See [Get market bbo](https://docs.api.prod.paradex.trade/?shell#get-market-bbo)
            for details.<br>

        Args:
            market: instrument symbol.<br>

        Returns:
            dictionary representing best bid/offer for specific market.<br>
        """
        return self._get(path=f"bbo/{market}")

    def fetch_insurance_fund(self) -> Dict[Any, Any]:
        """Fetch insurance fund information.<br>
            Public call, no authorization required.<br>
            See [Get insurance fund account information](https://docs.api.prod.paradex.trade/?shell#get-insurance-fund-account-information)
            for details.<br>

        Returns:
            dictionary representing a state of Paradex Insurance Fund.<br>
        """
        return self._get(path="insurance")

    def fetch_liquidations(self, params: Optional[Dict] = None) -> Dict[Any, Any]:
        """Fetch history of liquidations for this account.<br>
            Private call requires authorization.<br>
            See [List liquidations](https://docs.api.prod.paradex.trade/?shell#list-liquidations) for details.<br>

        Args:
            params: dictionary with parameters. Valid keys:<br>
                `start` (int): start time in milliseconds since epoch.<br>
                `end` (int): end time in milliseconds since epoch.<br>

        Returns:
            dictionary with fields:<br>
                `results` - a list of dictionaries, each dict representing a liquidation event.<br>
        """
        return self._get(path="liquidations")

    @validate_market
    def fetch_trades(self, params: Dict) -> Dict[Any, Any]:
        """Fetch Paradex exchange trades for specific market.<br>
            Public call, no authorization required.<br>
            See [Trade tape](https://docs.api.prod.paradex.trade/?shell#trade-tape)
            for details.<br>

        Args:
            params: dictionary with parameters. Valid keys:<br>
                `market` (str): MANDATORY, instrument's symbol.<br>

        Returns:
            dictionary with fields:<br>
                `next`, `prev` - pagination tokens.<br>
                `results` - a list of dictionaries, each dict representing a trade.<br>
        """
        return self._get(path="trades", params=params)

    # order helper functions
    def submit_order(self, order: Order) -> Dict[Any, Any]:
        """Send order to Paradex.<br>
            Private call requires authorization.<br>
            See [Create order](https://docs.api.prod.paradex.trade/?shell#create-order)
            for details.<br>

        Args:
            order : Order object.<br>

        Returns:
            dictionary representing a response from Paradex API.<br>
        """
        order.signature = self.account.sign_order(order)
        order_payload = order.dump_to_dict()
        return self._post_authorized(path="orders", payload=order_payload)

    def cancel_order(self, order_id: str) -> None:
        """Cancel open order previously sent to Paradex from this account.<br>
            Private call requires authorization.<br>
            See [Cancel order](https://docs.api.prod.paradex.trade/?shell#cancel-order) for details.<br>

        Args:
            order_id: Order id as assigned by Paradex.<br>

        Returns:
            None
        """
        self._delete_authorized(path=f"orders/{order_id}")

    def cancel_order_by_client_id(self, client_id: str) -> None:
        """Cancel open order previously sent to Paradex from this account.<br>
            Private call requires authorization.<br>
            See [Cancel open order by client order id](https://docs.api.prod.paradex.trade/?shell#cancel-open-order-by-client-order-id)
            for details.<br>

        Args:
            client_id: Order id as assigned by a trader.<br>

        Returns:
            None
        """
        self._delete_authorized(path=f"orders/by_client_id/{client_id}")

    def cancel_all_orders(self, params: Optional[Dict] = None) -> None:
        """Cancel all open orders for specific market or for all markets.<br>
            Private call requires authorization.<br>
            See [Cancel all open orders](https://docs.api.prod.paradex.trade/?shell#cancel-all-open-orders)
            for details.<br>

        Args:
            params: dictionary with parameters. Valid keys:<br>
                `market` (str): instrument's symbol.<br>

        Returns:
            None
        """
        self._delete_authorized(path="orders", params=params)
