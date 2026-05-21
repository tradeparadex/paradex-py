"""Example: Using the threaded WebSocket client for synchronous integration.

This demonstrates the synchronous API that doesn't require asyncio knowledge.
For the async version see `examples/connect_ws_api.py`.
"""

import os

from examples.utils import get_logger
from paradex_py import Paradex
from paradex_py.api.ws_client import ParadexWebsocketChannel
from paradex_py.api.ws_client_threaded import ThreadedParadexWebsocketClient
from paradex_py.environment import TESTNET

TEST_L1_ADDRESS = os.getenv("L1_ADDRESS", "")
TEST_L1_PRIVATE_KEY = os.getenv("L1_PRIVATE_KEY", "")


def main() -> None:
    logger = get_logger(__name__)

    Paradex(
        env=TESTNET,
        l1_address=TEST_L1_ADDRESS,
        l1_private_key=TEST_L1_PRIVATE_KEY,
        logger=logger,
    )

    ws_client = ThreadedParadexWebsocketClient(env=TESTNET)

    try:
        with ws_client:
            logger.info("WebSocket connected")

            ws_client.subscribe(ParadexWebsocketChannel.MARKETS_SUMMARY)
            ws_client.subscribe(ParadexWebsocketChannel.BBO)
            logger.info("Subscribed to MARKETS_SUMMARY and BBO")

            message_count = 0
            while message_count < 100:
                msg = ws_client.get_updates(timeout=5.0)
                if msg:
                    message_count += 1
                    logger.info("[%d] %s: %s", message_count, msg.channel, msg.data)
                else:
                    logger.info("No message received (timeout)")

            logger.info("Received %d messages", message_count)

    except KeyboardInterrupt:
        logger.info("Interrupted by user")


if __name__ == "__main__":
    main()
