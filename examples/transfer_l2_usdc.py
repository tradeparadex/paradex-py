import asyncio
import os
from decimal import Decimal

from utils import get_logger

from paradex_py import Paradex
from paradex_py.environment import TESTNET

logger = get_logger(__name__)

# Environment variables
TEST_L1_ADDRESS = os.getenv("L1_ADDRESS", "")
TEST_L1_PRIVATE_KEY = os.getenv("L1_PRIVATE_KEY", "")


paradex = Paradex(env=TESTNET, l1_address=TEST_L1_ADDRESS, l1_private_key=TEST_L1_PRIVATE_KEY)

recipient_address = ""
amount = Decimal(0)
logger.info(f"Transferring USDC from {TEST_L1_ADDRESS} to {recipient_address} amount {amount}")

asyncio.run(paradex.account.transfer_on_l2(recipient_address, amount))
