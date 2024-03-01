from paradex_py.paradex import Paradex


def test_system_config():
    paradex = Paradex(env="testnet")
    assert paradex.config.starknet_gateway_url == "https://potc-testnet-sepolia.starknet.io"
    assert paradex.config.starknet_chain_id == "PRIVATE_SN_POTC_SEPOLIA"
    assert paradex.config.block_explorer_url == "https://voyager.testnet.paradex.trade/"
    assert paradex.config.bridged_tokens[0].name == "TEST USDC"
