"""Tests for resolving the L2 address from GET /onboarding (the default) versus locally."""

from unittest.mock import MagicMock, patch

import pytest

from paradex_py import Paradex
from paradex_py.account.utils import derive_l2_address_starknet, fetch_l2_address
from paradex_py.api.api_client import ParadexApiClient
from paradex_py.environment import TESTNET
from tests.mocks.api_client import MOCK_ONBOARDING_STARKNET, MockApiClient

TEST_L1_ADDRESS = "0xd2c7314539dCe7752c8120af4eC2AA750Cf2035e"
TEST_L1_PRIVATE_KEY = "0xf8e4d1d772cdd44e5e77615ad11cc071c94e4c06dc21150d903f28e6aa6abdff"
# A current-class address: differs from what local (legacy proxy-class) derivation gives.
SERVER_ADDRESS = "0x5e7a1c0ffee"


def _bare_paradex(api_client) -> Paradex:
    """A Paradex with its clients stubbed, built without the network calls __init__ makes."""
    paradex = Paradex.__new__(Paradex)
    paradex.env = TESTNET
    paradex.logger = MagicMock()
    paradex.api_client = api_client
    paradex.ws_client = MagicMock()
    paradex.ws_direct_client = MagicMock()
    paradex.config = MockApiClient().fetch_system_config()
    paradex.account = None
    return paradex


class TestFetchL2Address:
    def test_returns_address_and_exists(self):
        api = MagicMock()
        api.fetch_onboarding.return_value = {"address": "0xabc", "exists": True}

        assert fetch_l2_address(api, {"public_key": "0x1"}, "Paradex") == ("0xabc", True)
        api.fetch_onboarding.assert_called_once_with({"public_key": "0x1"})

    @pytest.mark.parametrize(("exists", "expected"), [(False, False), (None, None)])
    def test_exists_false_or_omitted(self, exists, expected):
        api = MagicMock()
        response = {"address": "0xabc"}
        if exists is not None:
            response["exists"] = exists
        api.fetch_onboarding.return_value = response

        assert fetch_l2_address(api, {}, "Paradex") == ("0xabc", expected)

    def test_request_failure_names_the_opt_out(self):
        api = MagicMock()
        api.fetch_onboarding.side_effect = ValueError("HTTP 503: unavailable")

        with pytest.raises(ValueError, match=r"Paradex: could not fetch .* server_derive_address=False") as exc_info:
            fetch_l2_address(api, {}, "Paradex")
        assert "HTTP 503" in str(exc_info.value)
        assert isinstance(exc_info.value.__cause__, ValueError)

    @pytest.mark.parametrize("response", [None, {}, {"address": ""}, {"address": None, "exists": True}, ["0xabc"]])
    def test_response_without_address_raises(self, response):
        api = MagicMock()
        api.fetch_onboarding.return_value = response

        with pytest.raises(ValueError, match="returned no account address"):
            fetch_l2_address(api, {}, "Paradex")

    def test_non_hex_address_raises(self):
        api = MagicMock()
        api.fetch_onboarding.return_value = {"address": "not-an-address", "exists": True}

        with pytest.raises(ValueError, match="returned an invalid account address"):
            fetch_l2_address(api, {}, "Paradex")


class TestParadexAddressDerivation:
    def test_default_is_server_derivation(self):
        with (
            patch("paradex_py.paradex.ParadexApiClient") as MockApi,
            patch("paradex_py.paradex.ParadexWebsocketClient"),
            patch("paradex_py.paradex.ParadexAccount") as MockAccount,
        ):
            MockApi.return_value.fetch_system_config.return_value = MockApiClient().fetch_system_config()
            MockApi.return_value.fetch_onboarding.return_value = {"address": SERVER_ADDRESS, "exists": False}

            paradex = Paradex(env=TESTNET, l1_address=TEST_L1_ADDRESS, l1_private_key=TEST_L1_PRIVATE_KEY)

        assert paradex.server_derive_address is True
        params = MockApi.return_value.fetch_onboarding.call_args[0][0]
        assert params["account_signer_type"] == "starknet"
        public_key = int(params["public_key"], 16)
        assert MockAccount.call_args.kwargs["l2_address"] == SERVER_ADDRESS
        assert MockAccount.call_args.kwargs["is_onboarded"] is False
        # The server's address wins even though local derivation would give another one.
        assert hex(derive_l2_address_starknet(paradex.config, public_key)) != SERVER_ADDRESS

    def test_server_address_and_exists_reach_the_account(self):
        api = MockApiClient()
        paradex = _bare_paradex(api)

        with patch("paradex_py.account.account.FullNodeClient"):
            paradex.init_account(l1_address=TEST_L1_ADDRESS, l1_private_key=TEST_L1_PRIVATE_KEY)

        assert paradex.account is not None
        assert paradex.account.l2_address == int(MOCK_ONBOARDING_STARKNET["address"], 16)
        assert paradex.is_onboarded is True
        assert api.fetch_onboarding_calls == [
            {"account_signer_type": "starknet", "public_key": hex(paradex.account.l2_public_key)}
        ]

    def test_opt_out_derives_locally_without_a_request(self):
        api = MockApiClient()
        paradex = _bare_paradex(api)
        paradex.server_derive_address = False

        with patch("paradex_py.account.account.FullNodeClient"):
            paradex.init_account(l1_address=TEST_L1_ADDRESS, l1_private_key=TEST_L1_PRIVATE_KEY)

        assert paradex.account is not None
        assert api.fetch_onboarding_calls == []
        assert paradex.account.l2_address == derive_l2_address_starknet(paradex.config, paradex.account.l2_public_key)
        assert paradex.is_onboarded is None

    def test_request_failure_raises_and_leaves_account_unset(self):
        api = MagicMock()
        api.fetch_onboarding.side_effect = ConnectionError("network down")
        paradex = _bare_paradex(api)

        with pytest.raises(ValueError, match="server_derive_address=False"):
            paradex.init_account(l1_address=TEST_L1_ADDRESS, l1_private_key=TEST_L1_PRIVATE_KEY)

        assert paradex.account is None
        api.init_account.assert_not_called()

    @pytest.mark.parametrize(("exists", "posts_onboarding"), [(True, False), (False, True)])
    def test_exists_flag_decides_whether_to_onboard(self, exists, posts_onboarding):
        """With auto_auth, the cached exists flag skips POST /onboarding for an existing
        account and sends it before auth for a new one, through the real API client."""
        api = ParadexApiClient(env=TESTNET)
        paradex = _bare_paradex(api)
        calls: list[str] = []

        with (
            patch("paradex_py.account.account.FullNodeClient"),
            patch.object(api, "fetch_onboarding", return_value={"address": SERVER_ADDRESS, "exists": exists}),
            patch.object(api, "onboarding", side_effect=lambda: calls.append("onboarding")),
            patch.object(api, "auth", side_effect=lambda params=None: calls.append("auth")),
        ):
            paradex.init_account(l1_address=TEST_L1_ADDRESS, l1_private_key=TEST_L1_PRIVATE_KEY)

        assert paradex.account is not None
        assert paradex.account.l2_address == int(SERVER_ADDRESS, 16)
        assert calls == (["onboarding", "auth"] if posts_onboarding else ["auth"])
