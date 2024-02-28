import asyncio
import logging
import os
from datetime import datetime

from paradex_py.api.api_client import ParadexApiClient
from paradex_py.api.environment import TESTNET

LOG_TIMESTAMP = datetime.now().strftime("%Y_%m_%d_%H_%M_%S")
RUNFILE_BASE_NAME = os.path.splitext(os.path.basename(__file__))[0]

logging.basicConfig(
    # filename=f"logs/{RUNFILE_BASE_NAME}_{LOG_TIMESTAMP}.log",
    level=os.getenv("LOGGING_LEVEL", "INFO"),
    format="%(asctime)s.%(msecs)03d | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
l1_key = "0x"  # Enter your L1 PK here


async def main():
    async with ParadexApiClient(env=TESTNET, l1_private_key=l1_key) as client:
        # await client.init()
        balances = await client.private_get_balances()
        logging.info(f"Balances:{balances}")


loop = asyncio.get_event_loop()
loop.run_until_complete(main())
