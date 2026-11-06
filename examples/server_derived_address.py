#!/usr/bin/env python3
"""
Example: server-side address derivation via ``GET /onboarding``.

By default ``Paradex(...)`` and ``ParadexEvm(...)`` fetch the L2 account address
from ``GET /onboarding`` instead of computing it client-side. The server returns
the stored address of an existing account, whichever account class it was
created with, and the address a new account will be created at. The endpoint
also returns ``exists``, which the SDK caches to skip ``POST /onboarding`` when
the account is already onboarded.

Passing ``server_derive_address=False`` derives the address locally (no extra request) with
``compute_address`` plus the class hashes from ``GET /system/config``. For a
Starknet key that gives the legacy proxy-class address, which is wrong for
accounts created with the current class (such as new accounts onboarded in the
Paradex app).

Usage:
    export L1_ADDRESS="0x..."
    export L1_PRIVATE_KEY="0x..."
    python examples/server_derived_address.py
    # Compare against the local derivation path:
    python examples/server_derived_address.py --local

For an EVM wallet:
    export EVM_PRIVATE_KEY="0x..."
    python examples/server_derived_address.py --evm
    python examples/server_derived_address.py --evm --local
"""

import logging
import os
import sys

from eth_account import Account

from paradex_py import Paradex, ParadexEvm
from paradex_py.environment import NIGHTLY

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def _source_label(server_derive_address: bool) -> str:
    """Tag for log lines so it's obvious which path produced the address."""
    return "server (GET /onboarding)" if server_derive_address else "local (compute_address)"


def starknet_flow(server_derive_address: bool = True) -> None:
    l1_address = os.getenv("L1_ADDRESS", "")
    l1_private_key = os.getenv("L1_PRIVATE_KEY", "")
    if not l1_address or not l1_private_key:
        sys.exit("Set L1_ADDRESS and L1_PRIVATE_KEY in the environment.")

    paradex = Paradex(
        env=NIGHTLY,
        l1_address=l1_address,
        l1_private_key=l1_private_key,
        server_derive_address=server_derive_address,
        logger=logger,
    )

    # is_onboarded is populated when the server precheck ran (the default); with
    # server_derive_address=False it stays None and the SDK learns onboarding state via the auth retry path.
    logger.info("L2 address (%s): %s", _source_label(server_derive_address), hex(paradex.account.l2_address))
    logger.info("Onboarded (cached from precheck): %s", paradex.is_onboarded)

    summary = paradex.api_client.fetch_account_summary()
    logger.info("Account summary: %s", summary)


def evm_flow(server_derive_address: bool = True) -> None:
    evm_private_key = os.getenv("EVM_PRIVATE_KEY", "")
    if not evm_private_key:
        sys.exit("Set EVM_PRIVATE_KEY in the environment.")

    evm_address = Account.from_key(evm_private_key).address

    paradex = ParadexEvm(
        env=NIGHTLY,
        evm_address=evm_address,
        evm_private_key=evm_private_key,
        server_derive_address=server_derive_address,
    )

    logger.info("L2 address (%s): %s", _source_label(server_derive_address), hex(paradex.account.l2_address))
    logger.info("Onboarded (cached from precheck): %s", paradex.is_onboarded)

    balances = paradex.api_client.fetch_balances()
    logger.info("Balances: %s", balances)


if __name__ == "__main__":
    # `--local` runs the same flow with server derivation off, for side-by-side comparison.
    use_server = "--local" not in sys.argv
    if "--evm" in sys.argv:
        evm_flow(server_derive_address=use_server)
    else:
        starknet_flow(server_derive_address=use_server)
