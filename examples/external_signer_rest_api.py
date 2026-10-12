#!/usr/bin/env python3
"""
Example script demonstrating REST API usage with ExternalSignerAccount and a signing proxy.

The L2 private key stays with the proxy. The client sends each message hash in a header,
and the proxy signs it and puts the real signature in place of the stand-in.

Requirements:
- SIGNING_PROXY_URL: base URL of the proxy in front of the Paradex REST API, ending in /v1
- L2_ADDRESS: L2 address of the account
- L2_PUBLIC_KEY: public key of the key the proxy holds
- SIGN_HEADER: header the proxy reads the message hash from
- SIGN_STAND_IN: stand-in the proxy replaces with the real signature

Usage:
    export SIGNING_PROXY_URL="https://your-signing-proxy/v1"
    export L2_ADDRESS="0x..."
    export L2_PUBLIC_KEY="0x..."
    export SIGN_HEADER="X-Sign-Hash"
    export SIGN_STAND_IN="PROXY_SIGNATURE"
    python examples/external_signer_rest_api.py
"""

import os
from decimal import Decimal

from utils import get_logger

from paradex_py.account import ExternalSignerAccount, HeaderSigner
from paradex_py.api.api_client import ParadexApiClient
from paradex_py.common.order import Order, OrderSide, OrderType
from paradex_py.environment import TESTNET

logger = get_logger(__name__)

client = ParadexApiClient(env=TESTNET, api_base_url=os.environ["SIGNING_PROXY_URL"], logger=logger)
account = ExternalSignerAccount(
    config=client.fetch_system_config(),
    l2_address=os.environ["L2_ADDRESS"],
    l2_public_key=os.environ["L2_PUBLIC_KEY"],
    signer=HeaderSigner(header=os.environ["SIGN_HEADER"], signature=os.environ["SIGN_STAND_IN"]),
)
client.init_account(account)

account_summary = client.fetch_account_summary()
logger.info(f"{account_summary=}")

bbo = client.fetch_bbo(market="ETH-USD-PERP")
bid = Decimal(bbo["bid"]) * Decimal("0.5")
order = Order(
    market="ETH-USD-PERP",
    order_type=OrderType.Limit,
    order_side=OrderSide.Buy,
    size=Decimal("0.01"),
    limit_price=bid.quantize(Decimal("0.1")),
    client_id="external-signer-example",
    instruction="POST_ONLY",
)
submitted = client.submit_order(order=order)
logger.info(f"{submitted=}")

client.cancel_order(order_id=submitted["id"])
logger.info(f"Cancelled {submitted['id']}")
