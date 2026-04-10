#!/usr/bin/env python3
"""
Example: EVM wallet onboarding → subkey creation → order submission + WS subscriptions.

Full flow:
  1. Generate (or load) an EVM private key
  2. Create ParadexEvm — automatically onboards via SIWE and obtains a JWT
  3. Call create_trading_subkey() — generates a fresh Starknet subkey, registers it,
     and returns a ready-to-trade ParadexSubkey client
  4. Poll account balance until testnet faucet funds arrive
  5. Submit and cancel a perp limit order (BTC-USD-PERP) via the subkey
  6. Submit and cancel a spot limit order (DIME-USD) via the subkey — same signing flow
  7. Subscribe to public (BBO) and private (ORDERS) WebSocket channels via the subkey

Usage:
    # Generate a fresh EVM key each run (demo):
    python examples/evm_onboard_and_trade.py

    # Use an existing EVM key:
    export EVM_PRIVATE_KEY="0x<your-key>"
    python examples/evm_onboard_and_trade.py
"""

import asyncio
import logging
import os
import time
from decimal import Decimal
from pathlib import Path

from eth_account import Account

from paradex_py import ParadexEvm
from paradex_py.api.ws_client import ParadexWebsocketChannel
from paradex_py.common.order import Order, OrderSide, OrderType
from paradex_py.environment import TESTNET

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Dotenv loader — reads KEY=VALUE pairs into os.environ (no extra deps)
# ---------------------------------------------------------------------------

_DOTENV = Path(__file__).parent.parent / ".env.testlocal"


def _load_dotenv(path: Path = _DOTENV) -> None:
    try:
        for line in path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip())
        logger.info(f"Loaded env from {path}")
    except FileNotFoundError:
        pass


def _save_dotenv(updates: dict[str, str], path: Path = _DOTENV) -> None:
    """Upsert key=value pairs in the dotenv file."""
    lines = path.read_text().splitlines() if path.exists() else []
    existing = {line.split("=", 1)[0].strip() for line in lines if "=" in line and not line.startswith("#")}
    for key, value in updates.items():
        entry = f"{key}={value}"
        if key in existing:
            lines = [entry if line.startswith(f"{key}=") else line for line in lines]
        else:
            lines.append(entry)
    path.write_text("\n".join(lines) + "\n")
    logger.info(f"Saved {list(updates)} to {path}")


_load_dotenv()

# ---------------------------------------------------------------------------
# Step 1: EVM key
# ---------------------------------------------------------------------------

evm_private_key = os.getenv("EVM_PRIVATE_KEY") or Account.create().key.hex()
evm_address = Account.from_key(evm_private_key).address
logger.info(f"EVM address: {evm_address}")

# ---------------------------------------------------------------------------
# Step 2: Onboard with EVM key (SIWE)
#   - Calls POST /v2/onboarding (first run) then POST /v2/auth
#   - Stores the JWT automatically in api_client
# ---------------------------------------------------------------------------

evm_paradex = ParadexEvm(
    env=TESTNET,
    evm_address=evm_address,
    evm_private_key=evm_private_key,
)

logger.info(f"Derived Starknet address: {hex(evm_paradex.account.l2_address)}")
logger.info(f"Auth level: {evm_paradex.auth_level}")  # FULL

# Validate the account was onboarded with an EVM (eip191) key
onboarding_info = evm_paradex.api_client.fetch_onboarding(
    {
        "account_signer_type": "eip191",
        "eth_address": evm_paradex.account.evm_address,
    }
)
logger.info(f"Onboarding info: {onboarding_info}")

# ---------------------------------------------------------------------------
# Step 3: Create a trading subkey
#   - Generates a fresh Starknet key pair
#   - Registers it as an active subkey on the EVM account
#   - Returns a ParadexSubkey client ready for order signing
# ---------------------------------------------------------------------------

# Reuse persisted subkey if available; create a new one otherwise
_l2_key = os.getenv("SUBKEY_PRIVATE_KEY")
_l2_addr = hex(evm_paradex.account.l2_address)
if _l2_key:
    from paradex_py import ParadexSubkey

    subkey_paradex = ParadexSubkey(env=TESTNET, l2_private_key=_l2_key, l2_address=_l2_addr)
    logger.info("Reusing persisted subkey")
else:
    subkey_paradex = evm_paradex.create_trading_subkey(name="evm-example-subkey")
    # Persist so the same subkey is reused on next run
    _save_dotenv({"SUBKEY_PRIVATE_KEY": hex(subkey_paradex.account.l2_private_key)})
logger.info(f"Subkey auth level: {subkey_paradex.auth_level}")  # TRADING

account_summary = subkey_paradex.api_client.fetch_account_summary()
logger.info(f"Account summary: {account_summary}")

# ---------------------------------------------------------------------------
# Step 4: Wait for testnet faucet funds before trading
# ---------------------------------------------------------------------------

logger.info("Waiting for testnet funds...")
while True:
    balances = subkey_paradex.api_client.fetch_balances()
    results = balances.get("results", [])
    usdc = next((b for b in results if b.get("token") == "USDC"), None)
    usdc_size = Decimal(usdc["size"]) if usdc else Decimal(0)
    if usdc_size > 0:
        logger.info(f"Funds available: {usdc_size} USDC")
        break
    logger.info("No funds yet, retrying in 5s...")
    time.sleep(5)

# ---------------------------------------------------------------------------
# Step 5: Submit and cancel a limit order via the subkey
# ---------------------------------------------------------------------------

buy_order = Order(
    market="BTC-USD-PERP",
    order_type=OrderType.Limit,
    order_side=OrderSide.Buy,
    size=Decimal("0.001"),
    limit_price=Decimal("10000"),  # far below market — won't fill
    instruction="POST_ONLY",
    reduce_only=False,
)

response = subkey_paradex.api_client.submit_order(order=buy_order)
order_id = response.get("id")
logger.info(f"Order submitted: {response}")

if order_id:
    try:
        subkey_paradex.api_client.cancel_order(order_id=order_id)
        logger.info(f"Order {order_id} cancelled")
    except ValueError:
        logger.info(f"Order {order_id} already closed (POST_ONLY rejected below market)")

# ---------------------------------------------------------------------------
# Step 6: Spot trade USDC → DIME via the subkey
#   - Spot orders use the same Order class and signing as perp orders
#   - Market format: BASE-QUOTE (e.g. DIME-USD), no "-PERP" suffix
#   - BUY side acquires DIME, spending USDC at the quoted price
# ---------------------------------------------------------------------------

spot_buy = Order(
    market="DIME-USD",
    order_type=OrderType.Limit,
    order_side=OrderSide.Buy,
    size=Decimal("100"),  # 100 DIME
    limit_price=Decimal("0.05"),  # at mark price — GTC, rests in book
    instruction="GTC",
    reduce_only=False,
)

spot_response = subkey_paradex.api_client.submit_order(order=spot_buy)
spot_order_id = spot_response.get("id")
logger.info(f"Spot order submitted: {spot_response}")

# Confirm the order rests in the book before cancelling
open_orders = subkey_paradex.api_client.fetch_orders({"market": "DIME-USD", "status": "NEW"})
logger.info(f"Open DIME-USD orders: {open_orders}")

if spot_order_id:
    try:
        subkey_paradex.api_client.cancel_order(order_id=spot_order_id)
        logger.info(f"Spot order {spot_order_id} cancelled")
    except ValueError:
        logger.info(f"Spot order {spot_order_id} already closed (filled or rejected)")

# ---------------------------------------------------------------------------
# Step 7: WebSocket subscriptions via the subkey
#   - Public channel: BBO for BTC-USD-PERP
#   - Private channel: ORDERS (authenticated via subkey JWT)
# ---------------------------------------------------------------------------


async def ws_demo() -> None:
    ws = subkey_paradex.ws_client

    async def on_bbo(channel: ParadexWebsocketChannel, msg: dict) -> None:
        logger.info(f"WS BBO: {msg}")

    async def on_orders(channel: ParadexWebsocketChannel, msg: dict) -> None:
        logger.info(f"WS ORDERS: {msg}")

    async def on_fills(channel: ParadexWebsocketChannel, msg: dict) -> None:
        logger.info(f"WS FILLS: {msg}")

    connected = await ws.connect()
    logger.info(f"WS connected: {connected}")

    await ws.subscribe(ParadexWebsocketChannel.BBO, callback=on_bbo, params={"market": "BTC-USD-PERP"})
    logger.info("Subscribed to BBO")

    await ws.subscribe(ParadexWebsocketChannel.ORDERS, callback=on_orders, params={"market": "ALL"})
    logger.info("Subscribed to ORDERS")

    await ws.subscribe(ParadexWebsocketChannel.FILLS, callback=on_fills, params={"market": "ALL"})
    logger.info("Subscribed to FILLS")

    logger.info("Listening for 5 seconds...")
    await asyncio.sleep(5)

    await ws.close()
    logger.info("WS closed")


asyncio.run(ws_demo())
