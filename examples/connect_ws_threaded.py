"""
Example: Using the threaded WebSocket client for synchronous integration.

This demonstrates the simplified API that doesn't require asyncio knowledge.
Use this approach when:
- You prefer synchronous code over async/await
- You're integrating with synchronous trading systems
- You want simpler channel management at runtime

For the async version, see: connect_ws_api.py
"""

import os

from starknet_py.common import int_from_hex

from paradex_py import Paradex
from paradex_py.api.ws_client import ParadexWebsocketChannel
from paradex_py.api.ws_client_threaded import ThreadedParadexWebsocketClient
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


def main():
    """Demonstrate threaded WebSocket client usage.

    Key differences from async version:
    - No asyncio.run() or event loop management required
    - Simple context manager for connection lifecycle
    - Blocking get_updates() instead of callbacks
    - Easy to integrate with synchronous code
    """
    # Initialize Paradex client (still needed for authentication)
    Paradex(
        env=TESTNET,
        l1_address=TEST_L1_ADDRESS,
        l1_private_key=TEST_L1_PRIVATE_KEY,
        logger=logger,
    )

    # Create threaded WebSocket client
    # This runs the async WebSocket in a background thread
    ws_client = ThreadedParadexWebsocketClient(
        env=TESTNET,
        log_messages=True,
    )

    try:
        # Connect using context manager (auto-cleanup on exit)
        with ws_client:
            logger.info("WebSocket connected!")

            # Subscribe to channels - can be done at any time
            ws_client.subscribe(ParadexWebsocketChannel.MARKETS_SUMMARY)
            ws_client.subscribe(ParadexWebsocketChannel.BBO)
            logger.info("Subscribed to MARKETS_SUMMARY and BBO channels")

            # Simple blocking loop - no asyncio needed
            logger.info("Listening for updates (Ctrl+C to stop)...")

            message_count = 0
            while message_count < 100:  # Limit for demo
                # get_updates() blocks until a message arrives or timeout
                msg = ws_client.get_updates(timeout=5.0)

                if msg:
                    message_count += 1
                    logger.info(f"[{message_count}] Channel: {msg.channel}")
                    logger.info(f"    Data: {msg.data}")
                else:
                    logger.info("No message received (timeout)")

            logger.info(f"Received {message_count} messages")

    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except Exception as e:
        logger.error(f"Error: {e}")
    finally:
        logger.info("WebSocket closed")


if __name__ == "__main__":
    main()
