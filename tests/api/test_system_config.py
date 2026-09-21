import copy
from unittest.mock import patch

from paradex_py import Paradex
from paradex_py.api.api_client import ParadexApiClient
from paradex_py.environment import TESTNET
from tests.mocks.api_client import MOCK_CONFIG


def test_system_config():
    paradex = Paradex(env=TESTNET)
    assert paradex.config.starknet_gateway_url in ("", None)
    assert paradex.config.starknet_chain_id == "PRIVATE_SN_PARACLEAR_TESTNET"
    assert paradex.config.block_explorer_url == "https://app.testnet.paradex.trade/explorer"
    assert paradex.config.bridged_tokens[0].name == "TEST USDC"


class TestSystemConfigUnknownFields:
    def setup_method(self):
        self.api_client = ParadexApiClient(env=TESTNET)

    def test_fetch_system_config_tolerates_new_server_fields(self):
        """Fields the server adds later must not break an already released SDK.

        `unknown` passed to load() does not reach the nested BridgedToken
        schema, so this covers both levels. fetch_system_config() runs during
        client initialization, so a single new field would break startup.
        """
        res = copy.deepcopy(MOCK_CONFIG)
        res["some_future_field"] = "ignored"
        res["bridged_tokens"][0]["some_future_bridge_field"] = "ignored"

        with patch.object(self.api_client, "request") as mock_request:
            mock_request.return_value = res

            config = self.api_client.fetch_system_config()

        assert config.starknet_chain_id == "PRIVATE_SN_POTC_SEPOLIA"
        assert config.bridged_tokens[0].name == "TEST USDC"
        assert config.bridged_tokens[0].l2_bridge_address == MOCK_CONFIG["bridged_tokens"][0]["l2_bridge_address"]
