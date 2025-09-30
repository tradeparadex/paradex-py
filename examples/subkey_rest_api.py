#!/usr/bin/env python3
"""
Example script demonstrating L2-only REST API usage with ParadexSubkey.

This example shows how to use REST API functionality with only L2 credentials (subkey mode),
without requiring L1 Ethereum address or private key.

Requirements:
- L2_PRIVATE_KEY: Starknet private key for the subkey
- L2_ADDRESS: L2 address of the main account (not the subkey address)

Usage:
    export L2_PRIVATE_KEY="0x..."
    export L2_ADDRESS="0x..."
    python examples/subkey_rest_api.py
"""

import os
import time
from datetime import datetime
from decimal import Decimal

from paradex_py import Paradex, ParadexSubkey
from paradex_py.common.order import Order, OrderSide, OrderType
from paradex_py.environment import TESTNET

# Environment variables
TEST_L2_ADDRESS = os.getenv("L2_ADDRESS", "")
TEST_L2_PRIVATE_KEY = os.getenv("L2_PRIVATE_KEY", "")
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
system_state = public_paradex.api_client.fetch_system_state()
logger.info(f"{system_state=}")
system_time = public_paradex.api_client.fetch_system_time()
logger.info(f"{system_time=}")
insurance_fund = public_paradex.api_client.fetch_insurance_fund()
logger.info(f"{insurance_fund=}")
markets = public_paradex.api_client.fetch_markets()
logger.info(f"{markets=}")
for market in markets["results"][:5]:  # Limit to 5 markets for testing
    if not int(market.get("position_limit")):
        continue
    symbol = market["symbol"]
    mkt_summary = public_paradex.api_client.fetch_markets_summary({"market": symbol})
    logger.info(f"{mkt_summary=}")
    ob = public_paradex.api_client.fetch_orderbook(market=symbol, params={"depth": 5})
    logger.info(f"{ob}=")
    bbo = public_paradex.api_client.fetch_bbo(market=symbol)
    logger.info(f"{bbo=}")

    try:
        trades = public_paradex.api_client.fetch_trades({"market": symbol, "page_size": 20})
        logger.info(f"{trades=}")
    except Exception as e:
        logger.warning(f"Could not fetch trades for {symbol}: {e}")

    try:
        funding_data = public_paradex.api_client.fetch_funding_data(params={"market": symbol})
        logger.info(f"Funding data {funding_data=}")
    except Exception as e:
        logger.warning(f"Could not fetch funding data for {symbol}: {e}")

# Test Insurance endpoints
insurance_fund = public_paradex.api_client.fetch_insurance_fund()
logger.info(f"{insurance_fund=}")

# Test System endpoints
system_config = public_paradex.api_client.fetch_system_config()
logger.info(f"{system_config=}")

# Test Private API calls with L2-only authentication using ParadexSubkey
paradex = ParadexSubkey(
    env=TESTNET,
    l2_private_key=TEST_L2_PRIVATE_KEY,
    l2_address=TEST_L2_ADDRESS,
    logger=logger,
)

account_summary = paradex.api_client.fetch_account_summary()
logger.info(f"{account_summary=}")
account_profile = paradex.api_client.fetch_account_profile()
logger.info(f"{account_profile=}")

try:
    balances = paradex.api_client.fetch_balances()
    logger.info(f"{balances=}")
except Exception as e:
    logger.warning(f"Could not fetch balances: {e}")

try:
    positions = paradex.api_client.fetch_positions()
    logger.info(f"{positions=}")
except Exception as e:
    logger.warning(f"Could not fetch positions: {e}")

try:
    transactions = paradex.api_client.fetch_transactions(params={"page_size": 5})
    logger.info(f"{transactions=}")
except Exception as e:
    logger.warning(f"Could not fetch transactions: {e}")

try:
    fills = paradex.api_client.fetch_fills(params={"page_size": 5})
    logger.info(f"{fills=}")
except Exception as e:
    logger.warning(f"Could not fetch fills: {e}")

try:
    tradebusts = paradex.api_client.fetch_tradebusts()
    logger.info(f"{tradebusts=}")
except Exception as e:
    logger.warning(f"Could not fetch tradebusts: {e}")

try:
    hist_orders = paradex.api_client.fetch_orders_history(params={"page_size": 5})
    logger.info(f"{hist_orders=}")
except Exception as e:
    logger.warning(f"Could not fetch orders history: {e}")

try:
    subaccounts = paradex.api_client.fetch_subaccounts()
    logger.info(f"{subaccounts=}")
except Exception as e:
    logger.warning(f"Could not fetch subaccounts: {e}")

try:
    account_info = paradex.api_client.fetch_account_info()
    logger.info(f"{account_info=}")
except Exception as e:
    logger.warning(f"Could not fetch account info: {e}")

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
    try:
        orders = paradex.api_client.fetch_orders(params={"market": symbol})
        logger.info(f"{symbol=} {orders=}")
    except Exception as e:
        logger.warning(f"Could not fetch orders for {symbol}: {e}")

    try:
        fills = paradex.api_client.fetch_fills(params={"market": symbol, "page_size": 5})
        logger.info(f"{symbol=} {fills=}")
    except Exception as e:
        logger.warning(f"Could not fetch fills for {symbol}: {e}")

    try:
        funding_payments = paradex.api_client.fetch_funding_payments(params={"market": symbol})
        logger.info(f"{symbol=} {funding_payments=}")
    except Exception as e:
        logger.warning(f"Could not fetch funding payments for {symbol}: {e}")

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
