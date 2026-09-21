import copy
from unittest.mock import patch

import pytest

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

    @pytest.mark.parametrize(
        "drop,expected",
        [
            (lambda res: res.pop("liquidation_fee"), "liquidation_fee"),
            (lambda res: res["bridged_tokens"][0].pop("l1_bridge_address"), "l1_bridge_address"),
        ],
        ids=["top_level", "nested"],
    )
    def test_fetch_system_config_names_a_field_the_server_stopped_sending(self, drop, expected):
        """The mirror case: a field that goes away must fail clearly.

        The SDK cannot carry on without a field its dataclass requires, so this
        stays an error. `partial=True` used to suppress marshmallow's check only
        for the dataclass constructor to raise a bare TypeError a caller cannot
        map back to the response, so the load is strict and says what is missing.
        """
        res = copy.deepcopy(MOCK_CONFIG)
        drop(res)

        with patch.object(self.api_client, "request") as mock_request:
            mock_request.return_value = res

            with pytest.raises(Exception) as exc_info:
                self.api_client.fetch_system_config()

        assert not isinstance(exc_info.value, TypeError)
        assert expected in str(exc_info.value)
        assert "Missing data for required field" in str(exc_info.value)
