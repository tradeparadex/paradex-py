#!/usr/bin/env python3
"""
Example: EVM wallet onboarding → subkey creation → order submission.

Full flow:
  1. Generate (or load) an EVM private key
  2. Create ParadexEvm — automatically onboards via SIWE and obtains a JWT
  3. Generate a fresh Starknet L2 key pair for the subkey
  4. Register the L2 public key as an active subkey on the account
  5. Authenticate as that subkey with ParadexSubkey
  6. Submit and cancel a limit order via the subkey

Usage:
    # Generate a fresh EVM key each run (demo):
    python examples/evm_onboard_and_trade.py

    # Use an existing EVM key:
    export EVM_PRIVATE_KEY="0x<your-key>"
    python examples/evm_onboard_and_trade.py
"""

import logging
import os
import secrets
from decimal import Decimal

from eth_account import Account
from starknet_py.net.signer.stark_curve_signer import KeyPair

from paradex_py import ParadexEvm, ParadexSubkey
from paradex_py.common.order import Order, OrderSide, OrderType
from paradex_py.environment import TESTNET

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

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

evm_starknet_address = hex(evm_paradex.account.l2_address)
logger.info(f"Derived Starknet address: {evm_starknet_address}")

# ---------------------------------------------------------------------------
# Step 3: Generate a fresh Starknet L2 key pair for the subkey
# ---------------------------------------------------------------------------

# Starknet keys are 252-bit field elements; use secrets for a random one
l2_private_key_int = secrets.randbelow(2**251)
key_pair = KeyPair.from_private_key(l2_private_key_int)
l2_public_key_hex = hex(key_pair.public_key)
l2_private_key_hex = hex(l2_private_key_int)
logger.info(f"Generated subkey public key: {l2_public_key_hex}")

# ---------------------------------------------------------------------------
# Step 4: Register the subkey on the EVM account
#   - Uses the JWT obtained in step 2
#   - state="active" makes it immediately usable (no activation step needed)
# ---------------------------------------------------------------------------

evm_paradex.api_client.create_subkey(
    {
        "name": "evm-example-subkey",
        "public_key": l2_public_key_hex,
        "state": "active",
    }
)

# Verify the subkey appears in the list
subkeys = evm_paradex.api_client.fetch_subkeys()
logger.info(f"Subkeys: {subkeys}")

# ---------------------------------------------------------------------------
# Step 5: Authenticate as the subkey
#   - l2_address is the *parent* account's Starknet address (EVM-derived)
#   - ParadexSubkey calls /auth using the subkey's L2 key
# ---------------------------------------------------------------------------

subkey_paradex = ParadexSubkey(
    env=TESTNET,
    l2_private_key=l2_private_key_hex,
    l2_address=evm_starknet_address,
)
logger.info(f"Subkey auth level: {subkey_paradex.auth_level}")  # TRADING

account_summary = subkey_paradex.api_client.fetch_account_summary()
logger.info(f"Account summary: {account_summary}")

# ---------------------------------------------------------------------------
# Step 6: Submit and cancel a limit order via the subkey
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
    subkey_paradex.api_client.cancel_order(order_id=order_id)
    logger.info(f"Order {order_id} cancelled")

# Optional: revoke the subkey when done
# evm_paradex.api_client.revoke_subkey(l2_public_key_hex)
# logger.info("Subkey revoked")
