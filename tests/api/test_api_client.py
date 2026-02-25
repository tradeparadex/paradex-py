from decimal import Decimal
from unittest.mock import Mock, patch

import pytest

from paradex_py.api.api_client import ParadexApiClient
from paradex_py.common.order import Order, OrderSide, OrderType
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

    def _make_order(self, market: str = "BTC-USD-PERP", client_id: str = "client-1") -> Order:
        """Helper to create a minimal Order for tests."""
        return Order(
            market=market,
            order_type=OrderType.Limit,
            order_side=OrderSide.Buy,
            size=Decimal("0.1"),
            limit_price=Decimal("50000"),
            client_id=client_id,
        )

    def test_submit_orders_batch_with_signer(self):
        """Test submit_orders_batch uses provided signer and posts to orders/batch."""
        orders = [self._make_order(client_id="c1"), self._make_order(client_id="c2")]
        signed_payloads = [{"signed": "payload1"}, {"signed": "payload2"}]
        mock_signer = Mock()
        mock_signer.sign_batch.return_value = signed_payloads

        with patch.object(self.api_client, "post") as mock_post:
            mock_post.return_value = {"orders": [], "errors": []}

            result = self.api_client.submit_orders_batch(orders, signer=mock_signer)

            order_data_list = [o.dump_to_dict() for o in orders]
            mock_signer.sign_batch.assert_called_once_with(order_data_list)
            mock_post.assert_called_once_with(
                api_url=self.api_client.api_url,
                path="orders/batch",
                payload=signed_payloads,
                params=None,
                headers=None,
            )
            self.api_client._validate_auth.assert_called_once()
            assert result == {"orders": [], "errors": []}

    def test_submit_orders_batch_with_instance_signer(self):
        """Test submit_orders_batch uses instance signer when no signer provided."""
        self.api_client.signer = Mock()
        orders = [self._make_order()]
        signed_payloads = [{"signed": "payload"}]
        self.api_client.signer.sign_batch.return_value = signed_payloads

        with patch.object(self.api_client, "post") as mock_post:
            mock_post.return_value = {"orders": [], "errors": []}

            self.api_client.submit_orders_batch(orders)

            self.api_client.signer.sign_batch.assert_called_once()
            mock_post.assert_called_once_with(
                api_url=self.api_client.api_url,
                path="orders/batch",
                payload=signed_payloads,
                params=None,
                headers=None,
            )

    def test_submit_orders_batch_with_account(self):
        """Test submit_orders_batch uses account signing when no signer provided."""
        self.api_client.signer = None
        orders = [self._make_order(client_id="c1"), self._make_order(client_id="c2")]

        with patch.object(self.api_client, "post") as mock_post:
            mock_post.return_value = {"orders": [], "errors": []}

            self.api_client.submit_orders_batch(orders)

            assert self.api_client.account.sign_order.call_count == 2
            call_payload = mock_post.call_args[1]["payload"]
            assert len(call_payload) == 2
            assert call_payload[0]["client_id"] == "c1"
            assert call_payload[1]["client_id"] == "c2"
            mock_post.assert_called_once_with(
                api_url=self.api_client.api_url,
                path="orders/batch",
                payload=call_payload,
                params=None,
                headers=None,
            )

    def test_submit_orders_batch_no_signer_no_account_raises(self):
        """Test submit_orders_batch raises when no signer and no account."""
        self.api_client.signer = None
        self.api_client.account = None
        orders = [self._make_order()]

        with pytest.raises(ValueError, match="Account not initialized and no signer provided"):
            self.api_client.submit_orders_batch(orders)
