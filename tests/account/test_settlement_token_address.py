"""`transfer_on_l2` used to take `bridged_tokens[0]`, which is ETH on every
environment checked, so the transfer went against the wrong token."""

import pytest

from paradex_py.account.account import ParadexAccount
from paradex_py.api.models import BridgedToken, SystemConfig

BASE = {
    "starknet_gateway_url": "https://potc-testnet-02.starknet.io",
    "starknet_fullnode_rpc_url": "https://pathfinder.example/rpc/v0_7",
    "starknet_fullnode_rpc_base_url": "https://pathfinder.example",
    "starknet_chain_id": "PRIVATE_SN_POTC_SEPOLIA",
    "block_explorer_url": "https://voyager.example/",
    "paraclear_address": "0x1",
    "paraclear_decimals": 8,
    "paraclear_account_proxy_hash": "0x2",
    "paraclear_account_hash": "0x3",
    "oracle_address": "0x4",
    "l1_core_contract_address": "0x5",
    "l1_operator_address": "0x6",
    "l1_chain_id": "11155111",
    "liquidation_fee": "0.2",
}


def _token(symbol, l2):
    return BridgedToken(symbol, symbol, 6, "0x0", "0x0", l2, "0x0")


def _account(tokens):
    acct = ParadexAccount.__new__(ParadexAccount)
    acct.config = SystemConfig(**{**BASE, "bridged_tokens": tokens})
    return acct


def test_picks_usdc_not_the_first_entry():
    # ETH first, as every real environment returns it
    acct = _account([_token("ETH", "0xeee"), _token("USDC", "0xccc"), _token("DIME", "0xddd")])
    assert acct._settlement_token_address() == "0xccc"


def test_position_independent():
    acct = _account([_token("USDC", "0xccc"), _token("ETH", "0xeee")])
    assert acct._settlement_token_address() == "0xccc"


def test_raises_when_absent_rather_than_transferring_the_wrong_token():
    acct = _account([_token("ETH", "0xeee")])
    with pytest.raises(ValueError):
        acct._settlement_token_address()
