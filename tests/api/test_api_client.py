import logging
import os
from datetime import datetime
from decimal import Decimal

from starknet_py.common import int_from_hex

from paradex_py.api.environment import TESTNET
from paradex_py.common.order import Order, OrderSide, OrderType
from paradex_py.paradex import Paradex

LOG_TIMESTAMP = datetime.now().strftime("%Y_%m_%d_%H_%M_%S")
RUNFILE_BASE_NAME = os.path.splitext(os.path.basename(__file__))[0]

logging.basicConfig(
    # filename=f"logs/{RUNFILE_BASE_NAME}_{LOG_TIMESTAMP}.log",
    level=os.getenv("LOGGING_LEVEL", "INFO"),
    format="%(asctime)s.%(msecs)03d | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

TEST_AMM_L1_PRIVATE_KEY = int_from_hex(os.getenv("L1_PRIVATE_KEY", ""))
TEST_AMM_L1_ADDRESS = os.getenv("L1_ADDRESS", "")

paradex = Paradex(
    env=TESTNET,
    l1_address=TEST_AMM_L1_ADDRESS,
    l1_private_key=TEST_AMM_L1_PRIVATE_KEY,
    logger=logger,
)

account_summary = paradex.fetch_account_summary()
logger.info(f"Account Summary: {account_summary}")
balances = paradex.fetch_balances()
logger.info(f"Balances: {balances}")
positions = paradex.fetch_positions()
logger.info(f"Positions: {positions}")
markets = paradex.fetch_markets()
logger.info(f"Markets: {markets}")
for market in markets:
    if not int(market.get("position_limit")):
        continue
    mkt_summary = paradex.fetch_markets_summary(market=market["symbol"])
    logger.info(f"Market Summary: {mkt_summary}")
    ob = paradex.fetch_orderbook(market=market["symbol"])
    logger.info(f"OB: {ob}")
    orders = paradex.fetch_orders(market=market["symbol"])
    logger.info(f"Orders: {orders}")
    # break

order = Order(
    market="ETH-USD-PERP",
    order_type=OrderType.Limit,
    order_side=OrderSide.Buy,
    size=Decimal("0.1"),
    limit_price=Decimal(1_500),
    client_id=f"test_buy_{datetime.now().strftime('%Y%m%d%H%M%S')}",
)

response = paradex.send_order(order=order)
logger.info(f"Order Response: {response}")
orders = paradex.fetch_orders(market="ETH-USD-PERP")
logger.info(f"Orders: {orders}")
