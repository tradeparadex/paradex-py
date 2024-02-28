from paradex_py.api.models import SystemConfig, SystemConfigSchema

MOCK_CONFIG = {
    "api_url": "https://api.testnet.paradex.trade/v1",
    "ws_api_url": "wss://ws.api.testnet.paradex.trade/v1",
    "starknet_gateway_url": "https://potc-testnet-sepolia.starknet.io",
    "starknet_fullnode_rpc_url": "https://pathfinder.api.testnet.paradex.trade/rpc/v0.5",
    "starknet_chain_id": "PRIVATE_SN_POTC_SEPOLIA",
    "block_explorer_url": "https://voyager.testnet.paradex.trade/",
    "paraclear_address": "0x286003f7c7bfc3f94e8f0af48b48302e7aee2fb13c23b141479ba00832ef2c6",
    "paraclear_decimals": 8,
    "paraclear_account_proxy_hash": "0x3530cc4759d78042f1b543bf797f5f3d647cde0388c33734cf91b7f7b9314a9",
    "paraclear_account_hash": "0x41cb0280ebadaa75f996d8d92c6f265f6d040bb3ba442e5f86a554f1765244e",
    "oracle_address": "0x2c6a867917ef858d6b193a0ff9e62b46d0dc760366920d631715d58baeaca1f",
    "bridged_tokens": [
        {
            "name": "TEST USDC",
            "symbol": "USDC",
            "decimals": 6,
            "l1_token_address": "0x29A873159D5e14AcBd63913D4A7E2df04570c666",
            "l1_bridge_address": "0x8586e05adc0C35aa11609023d4Ae6075Cb813b4C",
            "l2_token_address": "0x6f373b346561036d98ea10fb3e60d2f459c872b1933b50b21fe6ef4fda3b75e",
            "l2_bridge_address": "0x46e9237f5408b5f899e72125dd69bd55485a287aaf24663d3ebe00d237fc7ef",
        }
    ],
    "l1_core_contract_address": "0x582CC5d9b509391232cd544cDF9da036e55833Af",
    "l1_operator_address": "0x11bACdFbBcd3Febe5e8CEAa75E0Ef6444d9B45FB",
    "l1_chain_id": "11155111",
    "liquidation_fee": "0.2",
}


class MockApiClient:
    def load_system_config(self) -> SystemConfig:
        return SystemConfigSchema().load(MOCK_CONFIG)
