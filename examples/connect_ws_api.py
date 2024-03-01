import asyncio
import logging
import os
import time
from decimal import Decimal

from starknet_py.common import int_from_hex

from examples.shared import logger
from paradex_py import Paradex
from paradex_py.api.ws_client import ParadexWebsocketChannel
from paradex_py.common.order import Order, OrderSide, OrderStatus, OrderType
from paradex_py.environment import TESTNET

# Environment variables
TEST_L1_ADDRESS = os.getenv("L1_ADDRESS", "")
TEST_L1_PRIVATE_KEY = int_from_hex(os.getenv("L1_PRIVATE_KEY", ""))

# Test Private API calls


def order_from_ws_message(msg: dict) -> Order:
    """
    Creates an Order object from a Paradex websocket message.
    """
    client_id = msg["client_id"] if msg["client_id"] else msg["id"]
    order = Order(
        market=msg["market"],
        order_type=OrderType(msg["type"]),
        order_side=OrderSide(msg["side"]),
        size=Decimal(msg["size"]),
        limit_price=Decimal(msg["price"]),
        client_id=client_id,
        instruction=msg.get("instruction", "GTC"),
        reduce_only=bool("REDUCE_ONLY" in msg.get("flags", [])),
    )
    order.id = msg["id"]
    order.status = OrderStatus(msg["status"])
    order.account = msg["account"]
    order.remaining = Decimal(msg["remaining_size"])
    order.created_at = int(msg["created_at"])
    order.cancel_reason = msg["cancel_reason"]
    return order


# Assumes paradex has L1 address and private key
async def paradex_ws_test(paradex: Paradex):
    try:
        await paradex.ws_client.connect()
        await paradex.ws_client.subscribe(ParadexWebsocketChannel.ACCOUNT)
        await paradex.ws_client.subscribe(ParadexWebsocketChannel.MARKETS_SUMMARY)
        await paradex.ws_client.subscribe(ParadexWebsocketChannel.POSITIONS)
        await paradex.ws_client.subscribe(ParadexWebsocketChannel.ORDER_BOOK, "ETH-USD-PERP")
        await paradex.ws_client.subscribe(ParadexWebsocketChannel.ORDERS, "ALL")

        async for message in paradex.ws_client.read_messages():
            if "params" in message:
                message_channel = message["params"].get("channel")
                logger.info(f"Channel: {message_channel} message:{message}")
                if message_channel.startswith(ParadexWebsocketChannel.ACCOUNT.prefix()):
                    # Account Summary
                    account_state = message["params"]["data"]
                    logger.info(f"Account Summary: {account_state}")
                elif message_channel.startswith(ParadexWebsocketChannel.MARKETS_SUMMARY.prefix()):
                    summary = message["params"]["data"]
                    market: str = summary["symbol"]
                    logger.info(f"{market} Summary:{summary}")
                elif message_channel.startswith(ParadexWebsocketChannel.ORDERS.prefix()):
                    order_data = message["params"]["data"]
                    order = order_from_ws_message(order_data)
                    logger.info(f"Order update:{order}")
                elif message_channel.startswith(ParadexWebsocketChannel.POSITIONS.prefix()):
                    positions = message["params"]["data"]
                    logging.info(f"Positions update: {positions}")
                elif message_channel.startswith(ParadexWebsocketChannel.ORDER_BOOK.prefix()):
                    market = message_channel.split(".")[1]
                    ob = message["params"]["data"]
                    logging.debug(f"{market} {message_channel} Orderbook: {ob}")
                else:
                    logger.info(f"Non-actionable channel:{message_channel} {message}")
            else:
                logger.info(f"Non-actionable {message}")

    except Exception:
        logger.exception("Connection closed unexpectedly:")
        time.sleep(1)
        await paradex_ws_test()


paradex = Paradex(
    env=TESTNET,
    l1_address=TEST_L1_ADDRESS,
    l1_private_key=TEST_L1_PRIVATE_KEY,
    logger=logger,
)

asyncio.get_event_loop().run_until_complete(paradex_ws_test(paradex))
