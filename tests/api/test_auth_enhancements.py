"""Tests for authentication and signing enhancements: auth providers, signers, auto_auth, etc."""

import time
from unittest.mock import MagicMock, patch

from paradex_py.api.api_client import ParadexApiClient
from paradex_py.api.protocols import NoOpSigner
from paradex_py.environment import TESTNET


class MockAuthProvider:
    """Mock authentication provider for testing."""

    def __init__(self, token="mock-test-token", should_refresh=False):  # noqa: S107
        self.token = token
        self.should_refresh = should_refresh
        self.get_token_calls = 0
        self.refresh_calls = 0

    def get_token(self):
        self.get_token_calls += 1
        return self.token

    def refresh_if_needed(self):
        self.refresh_calls += 1
        if self.should_refresh:
            self.token = f"refreshed-token-{self.refresh_calls}"
            return self.token
        return self.token if self.token else None


class MockSigner:
    """Mock signer for testing."""

    def __init__(self, should_add_signature=True):
        self.should_add_signature = should_add_signature
        self.signed_orders = []
        self.signed_batches = []

    def sign_order(self, order_data):
        self.signed_orders.append(order_data.copy())
        if self.should_add_signature:
            result = order_data.copy()
            result["signature"] = "mock-signature"
            return result
        return order_data

    def sign_batch(self, orders):
        self.signed_batches.append([order.copy() for order in orders])
        if self.should_add_signature:
            return [{**order, "signature": f"mock-signature-{i}"} for i, order in enumerate(orders)]
        return orders


class TestAuthenticationEnhancements:
    """Test authentication enhancements."""

    @patch.object(ParadexApiClient, "fetch_system_config", return_value=MagicMock())
    def test_auto_auth_enabled_default(self, mock_config):
        """Test auto_auth is enabled by default."""
        client = ParadexApiClient(env=TESTNET)
        assert client.auto_auth is True

    @patch.object(ParadexApiClient, "fetch_system_config", return_value=MagicMock())
    def test_auto_auth_disabled(self, mock_config):
        """Test auto_auth can be disabled."""
        client = ParadexApiClient(env=TESTNET, auto_auth=False)
        assert client.auto_auth is False

    @patch.object(ParadexApiClient, "fetch_system_config", return_value=MagicMock())
    def test_auth_provider_injection(self, mock_config):
        """Test auth provider injection."""
        auth_provider = MockAuthProvider()
        client = ParadexApiClient(env=TESTNET, auth_provider=auth_provider)
        assert client.auth_provider is auth_provider

    @patch.object(ParadexApiClient, "fetch_system_config", return_value=MagicMock())
    def test_set_token_manual(self, mock_config):
        """Test manual token injection."""
        client = ParadexApiClient(env=TESTNET)
        test_token = "mock-manual-jwt-token"  # noqa: S105

        client.set_token(test_token)

        assert client._manual_token == test_token
        assert "Bearer mock-manual-jwt-token" in str(client.client.headers.get("Authorization", ""))

    @patch.object(ParadexApiClient, "fetch_system_config", return_value=MagicMock())
    def test_validate_auth_with_manual_token_auto_auth_disabled(self, mock_config):
        """Test auth validation with manual token and auto_auth disabled."""
        client = ParadexApiClient(env=TESTNET, auto_auth=False)
        client.set_token("mock-manual-token")

        # Should not raise any errors
        client._validate_auth()

        # Should not attempt to refresh since we have manual token and auto_auth is disabled
        assert client._manual_token == "mock-manual-token"  # noqa: S105

    @patch.object(ParadexApiClient, "fetch_system_config", return_value=MagicMock())
    def test_validate_auth_with_auth_provider(self, mock_config):
        """Test auth validation with custom auth provider."""
        auth_provider = MockAuthProvider(token="mock-provider-token", should_refresh=True)  # noqa: S106
        client = ParadexApiClient(env=TESTNET, auth_provider=auth_provider)

        client._validate_auth()

        # Should have called refresh_if_needed
        assert auth_provider.refresh_calls == 1
        assert "Bearer refreshed-token-1" in str(client.client.headers.get("Authorization", ""))

    @patch.object(ParadexApiClient, "fetch_system_config", return_value=MagicMock())
    def test_validate_auth_with_auth_provider_syncs_account_token(self, mock_config):
        """Test that auth_provider token is synced to account.jwt_token for WebSocket compatibility."""
        auth_provider = MockAuthProvider(token="mock-provider-token", should_refresh=True)  # noqa: S106
        client = ParadexApiClient(env=TESTNET, auth_provider=auth_provider)

        # Mock account with set_jwt_token method
        mock_account = MagicMock()
        mock_account.set_jwt_token = MagicMock()
        client.account = mock_account

        client._validate_auth()

        # Should have called refresh_if_needed
        assert auth_provider.refresh_calls == 1
        # Should have synced token to account
        mock_account.set_jwt_token.assert_called_once_with("refreshed-token-1")
        assert "Bearer refreshed-token-1" in str(client.client.headers.get("Authorization", ""))

    @patch.object(ParadexApiClient, "fetch_system_config", return_value=MagicMock())
    def test_validate_auth_without_account_auto_auth_disabled(self, mock_config):
        """Test auth validation without account when auto_auth is disabled."""
        client = ParadexApiClient(env=TESTNET, auto_auth=False)
        client.account = None

        # Should not raise error when auto_auth is disabled
        client._validate_auth()

    @patch.object(ParadexApiClient, "fetch_system_config", return_value=MagicMock())
    def test_validate_auth_token_expiry_auto_auth_enabled(self, mock_config):
        """Test auth validation with expired token and auto_auth enabled."""
        client = ParadexApiClient(env=TESTNET, auto_auth=True)

        # Mock account
        mock_account = MagicMock()
        client.account = mock_account

        # Set auth timestamp to be old (> 4 minutes ago)
        client.auth_timestamp = time.time() - 300  # 5 minutes ago

        with patch.object(client, "auth") as mock_auth:
            client._validate_auth()
            # Should call auth to refresh token
            mock_auth.assert_called_once()

    @patch.object(ParadexApiClient, "fetch_system_config", return_value=MagicMock())
    def test_validate_auth_token_expiry_auto_auth_disabled(self, mock_config):
        """Test auth validation with expired token and auto_auth disabled."""
        client = ParadexApiClient(env=TESTNET, auto_auth=False)

        # Mock account
        mock_account = MagicMock()
        client.account = mock_account

        # Set auth timestamp to be old (> 4 minutes ago)
        client.auth_timestamp = time.time() - 300  # 5 minutes ago

        with patch.object(client, "auth") as mock_auth, patch.object(client.logger, "warning") as mock_warning:
            client._validate_auth()

            # Should not call auth
            mock_auth.assert_not_called()
            # Should log warning
            mock_warning.assert_called_once()

    @patch.object(ParadexApiClient, "fetch_system_config", return_value=MagicMock())
    def test_init_account_with_auto_auth_enabled(self, mock_config):
        """Test account initialization with auto_auth enabled."""
        client = ParadexApiClient(env=TESTNET, auto_auth=True)
        mock_account = MagicMock()

        with patch.object(client, "onboarding") as mock_onboarding, patch.object(client, "auth") as mock_auth:
            client.init_account(mock_account)

            assert client.account is mock_account
            mock_onboarding.assert_called_once()
            mock_auth.assert_called_once()

    @patch.object(ParadexApiClient, "fetch_system_config", return_value=MagicMock())
    def test_init_account_with_auto_auth_disabled(self, mock_config):
        """Test account initialization with auto_auth disabled."""
        client = ParadexApiClient(env=TESTNET, auto_auth=False)
        mock_account = MagicMock()

        with patch.object(client, "onboarding") as mock_onboarding, patch.object(client, "auth") as mock_auth:
            client.init_account(mock_account)

            assert client.account is mock_account
            # Should not call onboarding or auth when auto_auth is disabled
            mock_onboarding.assert_not_called()
            mock_auth.assert_not_called()


class TestSigningEnhancements:
    """Test signing enhancements."""

    @patch.object(ParadexApiClient, "fetch_system_config", return_value=MagicMock())
    def test_signer_injection(self, mock_config):
        """Test signer injection."""
        signer = MockSigner()
        client = ParadexApiClient(env=TESTNET, signer=signer)
        assert client.signer is signer

    @patch.object(ParadexApiClient, "fetch_system_config", return_value=MagicMock())
    def test_submit_order_with_instance_signer(self, mock_config):
        """Test submit_order with instance signer."""
        signer = MockSigner()
        client = ParadexApiClient(env=TESTNET, signer=signer)

        mock_order = MagicMock()
        mock_order.dump_to_dict.return_value = {"symbol": "BTC-USD-PERP", "side": "BUY"}

        with patch.object(client, "_post_authorized", return_value={"success": True}) as mock_post:
            result = client.submit_order(mock_order)

            assert result == {"success": True}
            assert len(signer.signed_orders) == 1
            assert signer.signed_orders[0] == {"symbol": "BTC-USD-PERP", "side": "BUY"}

            # Should have posted signed order
            mock_post.assert_called_once_with(
                path="orders", payload={"symbol": "BTC-USD-PERP", "side": "BUY", "signature": "mock-signature"}
            )

    @patch.object(ParadexApiClient, "fetch_system_config", return_value=MagicMock())
    def test_submit_order_with_parameter_signer(self, mock_config):
        """Test submit_order with parameter signer overriding instance signer."""
        instance_signer = MockSigner()
        param_signer = MockSigner()
        client = ParadexApiClient(env=TESTNET, signer=instance_signer)

        mock_order = MagicMock()
        mock_order.dump_to_dict.return_value = {"symbol": "BTC-USD-PERP", "side": "BUY"}

        with patch.object(client, "_post_authorized", return_value={"success": True}) as mock_post:
            result = client.submit_order(mock_order, signer=param_signer)

            assert result == {"success": True}

            # Parameter signer should be used
            assert len(param_signer.signed_orders) == 1
            assert len(instance_signer.signed_orders) == 0

            mock_post.assert_called_once_with(
                path="orders", payload={"symbol": "BTC-USD-PERP", "side": "BUY", "signature": "mock-signature"}
            )

    @patch.object(ParadexApiClient, "fetch_system_config", return_value=MagicMock())
    def test_submit_order_with_account_fallback(self, mock_config):
        """Test submit_order falls back to account signing."""
        client = ParadexApiClient(env=TESTNET)  # No signer

        mock_account = MagicMock()
        mock_account.sign_order.return_value = "account-signature"
        client.account = mock_account

        mock_order = MagicMock()
        mock_order.dump_to_dict.return_value = {"symbol": "BTC-USD-PERP", "side": "BUY"}

        with patch.object(client, "_post_authorized", return_value={"success": True}) as mock_post:
            result = client.submit_order(mock_order)

            assert result == {"success": True}

            # Should have used account signing
            mock_account.sign_order.assert_called_once_with(mock_order)
            assert mock_order.signature == "account-signature"

            mock_post.assert_called_once_with(path="orders", payload={"symbol": "BTC-USD-PERP", "side": "BUY"})

    @patch.object(ParadexApiClient, "fetch_system_config", return_value=MagicMock())
    def test_submit_orders_batch_with_signer(self, mock_config):
        """Test submit_orders_batch with signer."""
        signer = MockSigner()
        client = ParadexApiClient(env=TESTNET, signer=signer)

        mock_orders = [MagicMock(), MagicMock()]
        mock_orders[0].dump_to_dict.return_value = {"symbol": "BTC-USD-PERP", "side": "BUY"}
        mock_orders[1].dump_to_dict.return_value = {"symbol": "ETH-USD-PERP", "side": "SELL"}

        with patch.object(client, "_post_authorized", return_value={"success": True}) as mock_post:
            result = client.submit_orders_batch(mock_orders)

            assert result == {"success": True}
            assert len(signer.signed_batches) == 1
            assert len(signer.signed_batches[0]) == 2

            # Should have posted signed batch
            expected_payload = [
                {"symbol": "BTC-USD-PERP", "side": "BUY", "signature": "mock-signature-0"},
                {"symbol": "ETH-USD-PERP", "side": "SELL", "signature": "mock-signature-1"},
            ]
            mock_post.assert_called_once_with(path="orders/batch", payload=expected_payload)

    @patch.object(ParadexApiClient, "fetch_system_config", return_value=MagicMock())
    def test_modify_order_with_signer(self, mock_config):
        """Test modify_order with signer."""
        signer = MockSigner()
        client = ParadexApiClient(env=TESTNET, signer=signer)

        mock_order = MagicMock()
        mock_order.dump_to_dict.return_value = {"symbol": "BTC-USD-PERP", "size": "0.2"}

        with patch.object(client, "_put_authorized", return_value={"success": True}) as mock_put:
            result = client.modify_order("order-123", mock_order)

            assert result == {"success": True}
            assert len(signer.signed_orders) == 1

            mock_put.assert_called_once_with(
                path="orders/order-123",
                payload={"symbol": "BTC-USD-PERP", "size": "0.2", "signature": "mock-signature"},
            )

    def test_noop_signer_integration(self):
        """Test NoOpSigner integration for full simulation."""
        signer = NoOpSigner()

        order_data = {"symbol": "BTC-USD-PERP", "side": "BUY", "size": "0.1"}
        result = signer.sign_order(order_data)

        # Should return unchanged
        assert result is order_data
        assert "signature" not in result

        # Test batch signing
        orders = [order_data, {"symbol": "ETH-USD-PERP", "side": "SELL", "size": "1.0"}]
        batch_result = signer.sign_batch(orders)

        assert batch_result is orders
        assert all("signature" not in order for order in batch_result)
