from unittest.mock import Mock, patch

import pytest

from paradex_py.api.api_client import ParadexApiClient
from paradex_py.environment import TESTNET


class TestParadexApiClient:
    def setup_method(self):
        """Setup method to create an API client instance for each test."""
        self.api_client = ParadexApiClient(env=TESTNET)
        # Mock the account and auth methods
        self.api_client.account = Mock()
        self.api_client._validate_auth = Mock()

    def test_cancel_orders_batch_with_order_ids(self):
        """Test cancel_orders_batch with order IDs."""
        order_ids = ["order1", "order2", "order3"]
        expected_payload = {"order_ids": order_ids}

        # Mock the delete method
        with patch.object(self.api_client, "delete") as mock_delete:
            mock_delete.return_value = {"results": []}

            self.api_client.cancel_orders_batch(order_ids=order_ids)

            # Verify the delete method was called with correct parameters
            mock_delete.assert_called_once_with(
                api_url=self.api_client.api_url, path="orders/batch", params=None, payload=expected_payload
            )
            # Verify auth validation was called
            self.api_client._validate_auth.assert_called_once()

    def test_cancel_orders_batch_with_client_order_ids(self):
        """Test cancel_orders_batch with client order IDs."""
        client_order_ids = ["client1", "client2"]
        expected_payload = {"client_order_ids": client_order_ids}

        with patch.object(self.api_client, "delete") as mock_delete:
            mock_delete.return_value = {"results": []}

            self.api_client.cancel_orders_batch(client_order_ids=client_order_ids)

            mock_delete.assert_called_once_with(
                api_url=self.api_client.api_url, path="orders/batch", params=None, payload=expected_payload
            )

    def test_cancel_orders_batch_with_both_ids(self):
        """Test cancel_orders_batch with both order IDs and client order IDs."""
        order_ids = ["order1"]
        client_order_ids = ["client1"]
        expected_payload = {"order_ids": order_ids, "client_order_ids": client_order_ids}

        with patch.object(self.api_client, "delete") as mock_delete:
            mock_delete.return_value = {"results": []}

            self.api_client.cancel_orders_batch(order_ids=order_ids, client_order_ids=client_order_ids)

            mock_delete.assert_called_once_with(
                api_url=self.api_client.api_url, path="orders/batch", params=None, payload=expected_payload
            )

    def test_cancel_orders_batch_no_ids_raises_error(self):
        """Test cancel_orders_batch raises error when no IDs provided."""
        with pytest.raises(Exception) as exc_info:
            self.api_client.cancel_orders_batch()

        # The raise_value_error function should raise an exception
        assert "Must provide either order_ids or client_order_ids" in str(exc_info.value)

    def test_fetch_klines_with_required_params(self):
        """Test fetch_klines with required parameters."""
        symbol = "BTC-USD-PERP"
        resolution = "5"
        start_at = 1640995200000
        end_at = 1641081600000

        expected_params = {
            "symbol": symbol,
            "resolution": resolution,
            "start_at": start_at,
            "end_at": end_at,
        }

        with patch.object(self.api_client, "get") as mock_get:
            mock_get.return_value = {"results": []}

            self.api_client.fetch_klines(symbol=symbol, resolution=resolution, start_at=start_at, end_at=end_at)

            mock_get.assert_called_once_with(
                api_url=self.api_client.api_url, path="markets/klines", params=expected_params
            )

    def test_fetch_klines_with_price_kind(self):
        """Test fetch_klines with optional price_kind parameter."""
        symbol = "ETH-USD-PERP"
        resolution = "15"
        start_at = 1640995200000
        end_at = 1641081600000
        price_kind = "mark"

        expected_params = {
            "symbol": symbol,
            "resolution": resolution,
            "start_at": start_at,
            "end_at": end_at,
            "price_kind": price_kind,
        }

        with patch.object(self.api_client, "get") as mock_get:
            mock_get.return_value = {"results": []}

            self.api_client.fetch_klines(
                symbol=symbol, resolution=resolution, start_at=start_at, end_at=end_at, price_kind=price_kind
            )

            mock_get.assert_called_once_with(
                api_url=self.api_client.api_url, path="markets/klines", params=expected_params
            )

    def test_fetch_klines_without_price_kind(self):
        """Test fetch_klines without optional price_kind parameter."""
        symbol = "SOL-USD-PERP"
        resolution = "60"
        start_at = 1640995200000
        end_at = 1641081600000

        expected_params = {
            "symbol": symbol,
            "resolution": resolution,
            "start_at": start_at,
            "end_at": end_at,
        }

        with patch.object(self.api_client, "get") as mock_get:
            mock_get.return_value = {"results": []}

            self.api_client.fetch_klines(symbol=symbol, resolution=resolution, start_at=start_at, end_at=end_at)

            mock_get.assert_called_once_with(
                api_url=self.api_client.api_url, path="markets/klines", params=expected_params
            )

            # Verify price_kind is not in params when not provided
            called_params = mock_get.call_args[1]["params"]
            assert "price_kind" not in called_params
