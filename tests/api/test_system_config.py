from paradex_py import Paradex
from paradex_py.environment import TESTNET


def test_system_config():
    paradex = Paradex(env=TESTNET)
    assert paradex.config.starknet_gateway_url == "https://potc-testnet-sepolia.starknet.io"
    assert paradex.config.starknet_chain_id == "PRIVATE_SN_POTC_SEPOLIA"
    assert paradex.config.block_explorer_url == "https://app.testnet.paradex.trade/explorer"
    assert paradex.config.bridged_tokens[0].name == "TEST USDC"
