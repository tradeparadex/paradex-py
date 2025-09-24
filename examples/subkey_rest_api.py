import os
import time
from datetime import datetime
from decimal import Decimal

from paradex_py import Paradex
from paradex_py.common.order import Order, OrderSide, OrderType
from paradex_py.environment import TESTNET

# Environment variables
TEST_L2_PRIVATE_KEY = os.getenv("L2_PRIVATE_KEY", "")
TEST_L2_ADDRESS = os.getenv("L2_ADDRESS", "")
LOG_FILE = os.getenv("LOG_FILE", "FALSE").lower() == "true"

if LOG_FILE:
    from paradex_py.common.file_logging import file_logger

    logger = file_logger
    logger.info("Using file logger")
else:
    from paradex_py.common.console_logging import console_logger

    logger = console_logger
    logger.info("Using console logger")

# Fetch markets data for the example
public_paradex = Paradex(env=TESTNET, logger=logger)
markets = public_paradex.api_client.fetch_markets()
logger.info(f"{markets=}")

# Test Private API calls using L2-only authentication with a subkey
paradex = Paradex(
    env=TESTNET,
    l2_private_key=TEST_L2_PRIVATE_KEY,
    l2_address=TEST_L2_ADDRESS,
    logger=logger,
)
account_summary = paradex.api_client.fetch_account_summary()
logger.info(f"{account_summary=}")
account_profile = paradex.api_client.fetch_account_profile()
logger.info(f"{account_profile=}")

balances = paradex.api_client.fetch_balances()
logger.info(f"{balances=}")
positions = paradex.api_client.fetch_positions()
logger.info(f"{positions=}")
try:
    transactions = paradex.api_client.fetch_transactions(params={"page_size": 5})
    logger.info(f"{transactions=}")
except Exception as e:
    logger.warning(f"Failed to fetch transactions (timeout): {e}")
    transactions = {"results": [], "error": "timeout"}
try:
    fills = paradex.api_client.fetch_fills(params={"page_size": 5})
    logger.info(f"{fills=}")
except Exception as e:
    logger.warning(f"Failed to fetch fills (timeout): {e}")
    fills = {"results": [], "error": "timeout"}

try:
    tradebusts = paradex.api_client.fetch_tradebusts()
    logger.info(f"{tradebusts=}")
except Exception as e:
    logger.warning(f"Failed to fetch tradebusts (timeout): {e}")
    tradebusts = {"results": [], "error": "timeout"}

try:
    hist_orders = paradex.api_client.fetch_orders_history(params={"page_size": 5})
    logger.info(f"{hist_orders=}")
except Exception as e:
    logger.warning(f"Failed to fetch orders history (timeout): {e}")
    hist_orders = {"results": [], "error": "timeout"}
subaccounts = paradex.api_client.fetch_subaccounts()
logger.info(f"{subaccounts=}")
account_info = paradex.api_client.fetch_account_info()
logger.info(f"{account_info=}")


points_program = paradex.api_client.fetch_points_data(
    market="ETH-USD-PERP",
    program="Maker",
)
logger.info(f"Maker {points_program=}")

transfers = paradex.api_client.fetch_transfers(params={"page_size": 5})
logger.info(f"{transfers=}")
# Per market
for market in markets["results"][:5]:  # Limit to 5 markets for testing
    if not int(market.get("position_limit")):
        continue
    symbol = market["symbol"]
    orders = paradex.api_client.fetch_orders(params={"market": symbol})
    logger.info(f"{symbol=} {orders=}")
    fills = paradex.api_client.fetch_fills(params={"market": symbol, "page_size": 5})
    logger.info(f"{symbol=} {fills=}")
    funding_payments = paradex.api_client.fetch_funding_payments(params={"market": symbol})
    logger.info(f"{symbol=} {funding_payments=}")


# Create Order object and submit order
buy_client_id = f"test_buy_{datetime.now().strftime('%Y%m%d%H%M%S')}"
buy_order = Order(
    market="BTC-USD-PERP",
    order_type=OrderType.Limit,
    order_side=OrderSide.Buy,
    size=Decimal("0.01"),
    limit_price=Decimal(11_500),
    client_id=buy_client_id,
    instruction="POST_ONLY",
    reduce_only=False,
)
response = paradex.api_client.submit_order(order=buy_order)
buy_id = response.get("id")
logger.info(f"Buy Order {response=}")
if buy_id is None:
    logger.error("Failed to get buy order ID")
    exit(1)
buy_order_status = paradex.api_client.fetch_order_by_client_id(client_id=buy_client_id)
logger.info(f"{buy_order_status=}")

# Sell order
sell_client_id = f"test_sell_{datetime.now().strftime('%Y%m%d%H%M%S')}"
sell_order = Order(
    market="ETH-USD-PERP",
    order_type=OrderType.Limit,
    order_side=OrderSide.Sell,
    size=Decimal("0.1"),
    limit_price=Decimal(5_500),
    client_id=sell_client_id,
    instruction="POST_ONLY",
    reduce_only=False,
)
response = paradex.api_client.submit_order(order=sell_order)
logger.info(f"Sell Order {response=}")
sell_id = response.get("id")
if sell_id is None:
    logger.error("Failed to get sell order ID")
    exit(1)
sell_order_status = paradex.api_client.fetch_order(order_id=sell_id)
logger.info(f"{sell_order_status=}")

# Check all open orders
orders = paradex.api_client.fetch_orders()
logger.info(f"ALL {orders=}")
logger.info("Sleeping for 3 seconds")
time.sleep(3)

# Test modify
modify_order = Order(
    order_id=buy_id,
    market="BTC-USD-PERP",
    order_type=OrderType.Limit,
    order_side=OrderSide.Buy,
    size=Decimal("0.01"),
    limit_price=Decimal(9500),
    client_id=buy_client_id,
    instruction="POST_ONLY",
    reduce_only=False,
)
response = paradex.api_client.modify_order(buy_id, modify_order)
logger.info(f"Modify order response {response}")


# Cancel ETH open order
paradex.api_client.cancel_all_orders({"market": "ETH-USD-PERP"})
orders = paradex.api_client.fetch_orders()
logger.info(f"After ETH-USD-PERP Cancel {orders=}")
paradex.api_client.cancel_order(order_id=buy_id)
orders = paradex.api_client.fetch_orders()
logger.info(f"After BUY Cancel {orders=}")


# Place Parent Order with Attached Take Profit and Stop Loss Orders
# using Batch Orders API
order = Order(
    market="BTC-USD-PERP",
    order_type=OrderType.Limit,
    order_side=OrderSide.Buy,
    size=Decimal("0.01"),
    limit_price=Decimal(95_000),
)
taker_profit_order = Order(
    market="BTC-USD-PERP",
    order_type=OrderType.TakeProfitMarket,
    order_side=OrderSide.Sell,
    size=Decimal("0.01"),
    trigger_price=Decimal(100_0000),
    reduce_only=True,
)
stop_loss_order = Order(
    market="BTC-USD-PERP",
    order_type=OrderType.StopLossMarket,
    order_side=OrderSide.Sell,
    size=Decimal("0.01"),
    trigger_price=Decimal(90_000),
    reduce_only=True,
)
orders = [
    order,
    taker_profit_order,
    stop_loss_order,
]
response = paradex.api_client.submit_orders_batch(orders=orders)
logger.info(f"Batch of orders {response=}")
