"""Tests for RPC version functionality in ParadexAccount and Paradex."""

from unittest.mock import MagicMock, patch

from paradex_py import Paradex
from paradex_py.account.account import ParadexAccount
from paradex_py.environment import TESTNET
from tests.mocks.api_client import MockApiClient

TEST_L1_ADDRESS = "0xd2c7314539dCe7752c8120af4eC2AA750Cf2035e"
TEST_L1_PRIVATE_KEY = "0xf8e4d1d772cdd44e5e77615ad11cc071c94e4c06dc21150d903f28e6aa6abdff"
TEST_L2_PRIVATE_KEY = "0x543b6cf6c91817a87174aaea4fb370ac1c694e864d7740d728f8344d53e815"


class TestParadexAccountRpcVersion:
    """Test RPC version functionality in ParadexAccount."""

    def test_account_without_rpc_version(self):
        """Test that account uses default RPC URL when rpc_version is not provided."""
        api_client = MockApiClient()
        config = api_client.fetch_system_config()

        with patch("paradex_py.account.account.FullNodeClient") as mock_client:
            mock_client_instance = MagicMock()
            mock_client.return_value = mock_client_instance

            ParadexAccount(
                config=config,
                l1_address=TEST_L1_ADDRESS,
                l1_private_key=TEST_L1_PRIVATE_KEY,
            )

            # Verify that FullNodeClient was called with the default RPC URL
            mock_client.assert_called_once()
            call_args = mock_client.call_args
            assert call_args.kwargs["node_url"] == config.starknet_fullnode_rpc_url
            assert call_args.kwargs["node_url"] == "https://pathfinder.api.testnet.paradex.trade/rpc/v0.5"

    def test_account_with_rpc_version(self):
        """Test that account constructs RPC URL with version when rpc_version is provided."""
        api_client = MockApiClient()
        config = api_client.fetch_system_config()

        with patch("paradex_py.account.account.FullNodeClient") as mock_client:
            mock_client_instance = MagicMock()
            mock_client.return_value = mock_client_instance

            ParadexAccount(
                config=config,
                l1_address=TEST_L1_ADDRESS,
                l1_private_key=TEST_L1_PRIVATE_KEY,
                rpc_version="v0_9",
            )

            # Verify that FullNodeClient was called with the constructed URL
            mock_client.assert_called_once()
            call_args = mock_client.call_args
            expected_url = f"{config.starknet_fullnode_rpc_base_url}/rpc/v0_9"
            assert call_args.kwargs["node_url"] == expected_url
            assert call_args.kwargs["node_url"] == "https://pathfinder.api.testnet.paradex.trade/rpc/v0_9"

    def test_account_with_different_rpc_version(self):
        """Test that account works with different RPC versions."""
        api_client = MockApiClient()
        config = api_client.fetch_system_config()

        with patch("paradex_py.account.account.FullNodeClient") as mock_client:
            mock_client_instance = MagicMock()
            mock_client.return_value = mock_client_instance

            ParadexAccount(
                config=config,
                l1_address=TEST_L1_ADDRESS,
                l2_private_key=TEST_L2_PRIVATE_KEY,
                rpc_version="v0_8",
            )

            # Verify that FullNodeClient was called with the correct version
            mock_client.assert_called_once()
            call_args = mock_client.call_args
            expected_url = f"{config.starknet_fullnode_rpc_base_url}/rpc/v0_8"
            assert call_args.kwargs["node_url"] == expected_url
            assert call_args.kwargs["node_url"] == "https://pathfinder.api.testnet.paradex.trade/rpc/v0_8"


class TestParadexRpcVersion:
    """Test RPC version functionality in Paradex class."""

    def test_paradex_init_account_with_rpc_version(self):
        """Test that Paradex.init_account passes rpc_version to ParadexAccount."""
        # Create a mock Paradex instance
        paradex = Paradex.__new__(Paradex)
        paradex.env = TESTNET
        paradex.logger = MagicMock()
        paradex.api_client = MockApiClient()
        paradex.ws_client = MagicMock()
        paradex.config = paradex.api_client.fetch_system_config()
        paradex.account = None

        with patch("paradex_py.account.account.FullNodeClient") as mock_client:
            mock_client_instance = MagicMock()
            mock_client.return_value = mock_client_instance

            # Initialize account with rpc_version
            paradex.init_account(
                l1_address=TEST_L1_ADDRESS,
                l1_private_key=TEST_L1_PRIVATE_KEY,
                rpc_version="v0_9",
            )

            # Verify that FullNodeClient was called with the correct URL
            mock_client.assert_called_once()
            call_args = mock_client.call_args
            expected_url = f"{paradex.config.starknet_fullnode_rpc_base_url}/rpc/v0_9"
            assert call_args.kwargs["node_url"] == expected_url
            assert paradex.account is not None

    @patch("paradex_py.paradex.ParadexApiClient")
    @patch("paradex_py.paradex.ParadexWebsocketClient")
    def test_paradex_init_with_rpc_version(self, mock_ws_client, mock_api_client):
        """Test that Paradex.__init__ passes rpc_version to ParadexAccount."""
        # Setup mocks
        mock_api_instance = MockApiClient()
        mock_api_client.return_value = mock_api_instance
        mock_ws_client.return_value = MagicMock()

        with patch("paradex_py.account.account.FullNodeClient") as mock_client:
            mock_client_instance = MagicMock()
            mock_client.return_value = mock_client_instance

            # Create Paradex instance with rpc_version
            paradex = Paradex(
                env=TESTNET,
                l1_address=TEST_L1_ADDRESS,
                l1_private_key=TEST_L1_PRIVATE_KEY,
                rpc_version="v0_9",
            )

            # Verify that FullNodeClient was called with the correct URL
            mock_client.assert_called_once()
            call_args = mock_client.call_args
            expected_url = f"{paradex.config.starknet_fullnode_rpc_base_url}/rpc/v0_9"
            assert call_args.kwargs["node_url"] == expected_url
            assert paradex.account is not None

    @patch("paradex_py.paradex.ParadexApiClient")
    @patch("paradex_py.paradex.ParadexWebsocketClient")
    def test_paradex_init_without_rpc_version(self, mock_ws_client, mock_api_client):
        """Test that Paradex.__init__ uses default RPC URL when rpc_version is not provided."""
        # Setup mocks
        mock_api_instance = MockApiClient()
        mock_api_client.return_value = mock_api_instance
        mock_ws_client.return_value = MagicMock()

        with patch("paradex_py.account.account.FullNodeClient") as mock_client:
            mock_client_instance = MagicMock()
            mock_client.return_value = mock_client_instance

            # Create Paradex instance without rpc_version
            paradex = Paradex(
                env=TESTNET,
                l1_address=TEST_L1_ADDRESS,
                l1_private_key=TEST_L1_PRIVATE_KEY,
            )

            # Verify that FullNodeClient was called with default RPC URL
            mock_client.assert_called_once()
            call_args = mock_client.call_args
            assert call_args.kwargs["node_url"] == paradex.config.starknet_fullnode_rpc_url
            assert call_args.kwargs["node_url"] == "https://pathfinder.api.testnet.paradex.trade/rpc/v0.5"
            assert paradex.account is not None
