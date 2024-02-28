from paradex_py.api.api_client import ApiClient


def test_system_config():
    api_client = ApiClient(env="testnet")
    api_client.load_system_config()

    assert api_client.config.api_url == "https://api.testnet.paradex.trade/v1"
    assert api_client.config.ws_api_url == "wss://ws.api.testnet.paradex.trade/v1"
    assert api_client.config.starknet_gateway_url == "https://potc-testnet-sepolia.starknet.io"
    assert api_client.config.starknet_chain_id == "PRIVATE_SN_POTC_SEPOLIA"
    assert api_client.config.block_explorer_url == "https://voyager.testnet.paradex.trade/"
    assert api_client.config.bridged_tokens[0].name == "TEST USDC"
