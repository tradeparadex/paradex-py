import logging
import os
import time
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

TEST_L1_ADDRESS = os.getenv("L1_ADDRESS", "")
TEST_L1_PRIVATE_KEY = int_from_hex(os.getenv("L1_PRIVATE_KEY", ""))

# Test Public API calls
public_paradex = Paradex(env=TESTNET, logger=logger)
insurance_fund = public_paradex.api_client.fetch_insurance_fund()
logger.info(f"Insurance Fund: {insurance_fund}")
markets = public_paradex.api_client.fetch_markets()
logger.info(f"Markets: {markets}")
for market in markets:
    if not int(market.get("position_limit")):
        continue
    symbol = market["symbol"]
    mkt_summary = public_paradex.api_client.fetch_markets_summary(market=symbol)
    logger.info(f"Market Summary: {mkt_summary}")
    ob = public_paradex.api_client.fetch_orderbook(market=symbol)
    logger.info(f"OB: {ob}")
    trades = public_paradex.api_client.fetch_trades(market=symbol)
    logger.info(f"Trades: {trades[:(min(5, len(trades)))]}")


# Test Private API calls
paradex = Paradex(
    env=TESTNET,
    l1_address=TEST_L1_ADDRESS,
    l1_private_key=TEST_L1_PRIVATE_KEY,
    logger=logger,
)

account_summary = paradex.api_client.fetch_account_summary()
logger.info(f"Account Summary: {account_summary}")
balances = paradex.api_client.fetch_balances()
logger.info(f"Balances: {balances}")
positions = paradex.api_client.fetch_positions()
logger.info(f"Positions: {positions}")
transactions = paradex.api_client.fetch_transactions()
logger.info(f"Transactions: {transactions}")
for market in markets:
    if not int(market.get("position_limit")):
        continue
    symbol = market["symbol"]
    orders = paradex.api_client.fetch_orders(market=symbol)
    logger.info(f"{symbol} Orders: {orders}")
    # hist_orders = paradex.api_client.fetch_orders_history(market=symbol)
    # logger.info(f"{symbol} History Orders: {hist_orders}")
    fills = paradex.api_client.fetch_fills(market=symbol)
    logger.info(f"{symbol} Fills:{fills[:(min(5, len(fills)))]}")
    funding_payments = paradex.api_client.fetch_funding_payments(market=symbol)
    logger.info(f"{symbol} Funding Payments: {funding_payments}")

    # break

# Create Order object and submit order
buy_client_id = f"test_buy_{datetime.now().strftime('%Y%m%d%H%M%S')}"
order = Order(
    market="ETH-USD-PERP",
    order_type=OrderType.Limit,
    order_side=OrderSide.Buy,
    size=Decimal("0.1"),
    limit_price=Decimal(1_500),
    client_id=buy_client_id,
)
response = paradex.submit_order(order=order)
buy_id = response.get("id")
logger.info(f"Buy Order Response: {response}")

# Send order by calling send_order() method
sell_client_id = f"test_sell_{datetime.now().strftime('%Y%m%d%H%M%S')}"
response = paradex.send_order(
    market="ETH-USD-PERP",
    order_type=OrderType.Limit,
    order_side=OrderSide.Sell,
    size=Decimal("0.1"),
    limit_price=Decimal(5_500),
    client_id=sell_client_id,
    instruction="POST_ONLY",
    reduce_only=False,
)
logger.info(f"Sell Order Response: {response}")
sell_id = response.get("id")
# Check all open orders
orders = paradex.api_client.fetch_orders(market="ETH-USD-PERP")
logger.info(f"Orders: {orders}")
logger.info("Sleeping for 10 seconds")
time.sleep(10)
# Cancel open orders
response = paradex.cancel_order(order_id=buy_id)
orders = paradex.api_client.fetch_orders(market="ETH-USD-PERP")
logger.info(f"After BUY Cancel Orders: {orders}")
response = paradex.cancel_order_by_client_id(client_order_id=sell_client_id)
orders = paradex.api_client.fetch_orders(market="ETH-USD-PERP")
logger.info(f"After BUY/SELL Cancel Orders: {orders}")
