import asyncio
import logging
import os
import time
from datetime import datetime
from decimal import Decimal

from starknet_py.common import int_from_hex

from paradex_py.api.environment import TESTNET
from paradex_py.api.ws_client import ParadexWSChannel
from paradex_py.common.order import Order, OrderSide, OrderStatus, OrderType
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
        await paradex.connect_ws()
        await paradex.ws_client.subscribe_to_channel(ParadexWSChannel.ACCOUNT)
        await paradex.ws_client.subscribe_to_channel(ParadexWSChannel.MARKETS_SUMMARY)
        await paradex.ws_client.subscribe_to_channel(ParadexWSChannel.POSITIONS)
        await paradex.ws_client.subscribe_to_channel(ParadexWSChannel.ORDER_BOOK, "ETH-USD-PERP")
        await paradex.ws_client.subscribe_to_channel(ParadexWSChannel.ORDERS, "ALL")

        async for message in paradex.ws_client.read_ws_messages():
            if "params" in message:
                message_channel = message["params"].get("channel")
                logger.info(f"Channel: {message_channel} message:{message}")
                if message_channel.startswith(ParadexWSChannel.ACCOUNT.prefix()):
                    # Account Summary
                    account_state = message["params"]["data"]
                    logger.info(f"Account Summary: {account_state}")
                elif message_channel.startswith(ParadexWSChannel.MARKETS_SUMMARY.prefix()):
                    summary = message["params"]["data"]
                    market: str = summary["symbol"]
                    logger.info(f"{market} Summary:{summary}")
                elif message_channel.startswith(ParadexWSChannel.ORDERS.prefix()):
                    order_data = message["params"]["data"]
                    order = order_from_ws_message(order_data)
                    logger.info(f"Order update:{order}")
                elif message_channel.startswith(ParadexWSChannel.POSITIONS.prefix()):
                    positions = message["params"]["data"]
                    logging.info(f"Positions update: {positions}")
                elif message_channel.startswith(ParadexWSChannel.ORDER_BOOK.prefix()):
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
