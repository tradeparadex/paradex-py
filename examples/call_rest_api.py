import os
import time
from datetime import datetime
from decimal import Decimal

from starknet_py.common import int_from_hex

from paradex_py import Paradex
from paradex_py.common.order import Order, OrderSide, OrderType
from paradex_py.environment import TESTNET

# Environment variables
TEST_L1_ADDRESS = os.getenv("L1_ADDRESS", "")
TEST_L1_PRIVATE_KEY = int_from_hex(os.getenv("L1_PRIVATE_KEY", ""))
LOG_FILE = os.getenv("LOG_FILE", "FALSE").lower() == "true"

if LOG_FILE:
    from paradex_py.common.file_logging import file_logger

    logger = file_logger
    logger.info("Using file logger")
else:
    from paradex_py.common.console_logging import console_logger

    logger = console_logger
    logger.info("Using console logger")

# Test Public API calls
public_paradex = Paradex(env=TESTNET, logger=logger)
insurance_fund = public_paradex.api_client.fetch_insurance_fund()
logger.info(f"{insurance_fund=}")
markets = public_paradex.api_client.fetch_markets()
logger.info(f"{markets=}")
for market in markets["results"]:
    if not int(market.get("position_limit")):
        continue
    symbol = market["symbol"]
    mkt_summary = public_paradex.api_client.fetch_markets_summary({"market": symbol})
    logger.info(f"{mkt_summary=}")
    ob = public_paradex.api_client.fetch_orderbook(market=symbol, params={"depth": 5})
    logger.info(f"{ob}=")
    bbo = public_paradex.api_client.fetch_bbo(market=symbol)
    logger.info(f"{bbo=}")
    trades = public_paradex.api_client.fetch_trades({"market": symbol, "page_size": 5})
    logger.info(f"{trades=}")


# Test Private API calls
paradex = Paradex(
    env=TESTNET,
    l1_address=TEST_L1_ADDRESS,
    l1_private_key=TEST_L1_PRIVATE_KEY,
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
transactions = paradex.api_client.fetch_transactions(params={"page_size": 5})
logger.info(f"{transactions=}")
fills = paradex.api_client.fetch_fills(params={"page_size": 5})
logger.info(f"{fills=}")
tradebusts = paradex.api_client.fetch_tradebusts()
logger.info(f"{tradebusts=}")
hist_orders = paradex.api_client.fetch_orders_history(params={"page_size": 5})
logger.info(f"{hist_orders=}")
for market in markets["results"]:
    if not int(market.get("position_limit")):
        continue
    symbol = market["symbol"]
    orders = paradex.api_client.fetch_orders(params={"market": symbol})
    logger.info(f"{symbol=} {orders=}")
    fills = paradex.api_client.fetch_fills(params={"market": symbol, "page_size": 5})
    logger.info(f"{symbol=} {fills=}")
    funding_payments = paradex.api_client.fetch_funding_payments()
    logger.info(f"{symbol=} {funding_payments=}")


# Create Order object and submit order
buy_client_id = f"test_buy_{datetime.now().strftime('%Y%m%d%H%M%S')}"
buy_order = Order(
    market="ETH-USD-PERP",
    order_type=OrderType.Limit,
    order_side=OrderSide.Buy,
    size=Decimal("0.1"),
    limit_price=Decimal(1_500),
    client_id=buy_client_id,
    instruction="POST_ONLY",
    reduce_only=False,
)
response = paradex.api_client.submit_order(order=buy_order)
buy_id = response.get("id")
logger.info(f"Buy Order {response=}")
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
sell_order_status = paradex.api_client.fetch_order(order_id=sell_id)
logger.info(f"{sell_order_status=}")
# Check all open orders
orders = paradex.api_client.fetch_orders()
logger.info(f"ALL {orders=}")
logger.info("Sleeping for 10 seconds")
time.sleep(10)
# Cancel open orders
paradex.api_client.cancel_order(order_id=buy_id)
orders = paradex.api_client.fetch_orders()
logger.info(f"After BUY Cancel {orders=}")
time.sleep(3)
paradex.api_client.cancel_order_by_client_id(client_id=sell_client_id)
orders = paradex.api_client.fetch_orders()
logger.info(f"After BUY/SELL Cancel {orders=}")
