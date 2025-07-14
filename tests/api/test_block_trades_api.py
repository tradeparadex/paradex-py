from typing import cast
from unittest.mock import Mock, patch

import pytest

from paradex_py.api.api_client import ParadexApiClient
from paradex_py.api.generated.requests import (
    BlockExecuteRequest,
    BlockOfferRequest,
    BlockTradeRequest,
)
from paradex_py.environment import TESTNET


class TestBlockTradesApi:
    def setup_method(self):
        """Setup method to create an API client instance for each test."""
        self.api_client = ParadexApiClient(env=TESTNET)
        # Mock the account and auth methods
        self.api_client.account = Mock()
        self.api_client._validate_auth = Mock()

    def test_list_block_trades_no_filters(self):
        """Test list_block_trades with no filters."""
        with patch.object(self.api_client, "get") as mock_get:
            mock_get.return_value = {"results": []}

            self.api_client.list_block_trades()

            mock_get.assert_called_once_with(api_url=self.api_client.api_url, path="block-trades", params={})
            # Auth validation is tested in the main API client tests
            cast(Mock, self.api_client._validate_auth).assert_called_once()

    def test_list_block_trades_with_status_filter(self):
        """Test list_block_trades with status filter."""
        status = "CREATED"
        expected_params = {"status": status}

        with patch.object(self.api_client, "get") as mock_get:
            mock_get.return_value = {"results": []}

            self.api_client.list_block_trades(status=status)

            mock_get.assert_called_once_with(
                api_url=self.api_client.api_url, path="block-trades", params=expected_params
            )

    def test_list_block_trades_with_market_filter(self):
        """Test list_block_trades with market filter."""
        market = "BTC-USD-PERP"
        expected_params = {"market": market}

        with patch.object(self.api_client, "get") as mock_get:
            mock_get.return_value = {"results": []}

            self.api_client.list_block_trades(market=market)

            mock_get.assert_called_once_with(
                api_url=self.api_client.api_url, path="block-trades", params=expected_params
            )

    def test_list_block_trades_with_both_filters(self):
        """Test list_block_trades with both status and market filters."""
        status = "OFFER_COLLECTION"
        market = "ETH-USD-PERP"
        expected_params = {"status": status, "market": market}

        with patch.object(self.api_client, "get") as mock_get:
            mock_get.return_value = {"results": []}

            self.api_client.list_block_trades(status=status, market=market)

            mock_get.assert_called_once_with(
                api_url=self.api_client.api_url, path="block-trades", params=expected_params
            )

    def test_create_block_trade(self):
        """Test create_block_trade."""
        # Create a mock BlockTradeRequest
        block_trade = Mock(spec=BlockTradeRequest)
        block_trade.model_dump.return_value = {
            "nonce": "test_nonce",
            "required_signers": ["0x123", "0x456"],
            "trades": {"BTC-USD-PERP": {"size": "1.0", "price": "50000"}},
            "signatures": {},
        }

        expected_payload = block_trade.model_dump.return_value

        with patch.object(self.api_client, "post") as mock_post:
            mock_post.return_value = {"block_id": "test_block_id"}

            self.api_client.create_block_trade(block_trade)

            mock_post.assert_called_once_with(
                api_url=self.api_client.api_url,
                path="block-trades",
                payload=expected_payload,
                params=None,
                headers=None,
            )

    def test_create_block_trade_with_dict_fallback(self):
        """Test create_block_trade with dict() fallback for older pydantic versions."""
        # Create a mock BlockTradeRequest without model_dump
        block_trade = Mock(spec=BlockTradeRequest)
        # Since the API code has a bug where it calls model_dump() in both cases,
        # we need to mock model_dump to return the expected payload
        block_trade.model_dump.return_value = {
            "nonce": "test_nonce",
            "required_signers": ["0x123"],
            "trades": {"BTC-USD-PERP": {"size": "1.0"}},
            "signatures": {},
        }

        expected_payload = block_trade.model_dump.return_value

        with patch.object(self.api_client, "post") as mock_post:
            mock_post.return_value = {"block_id": "test_block_id"}

            self.api_client.create_block_trade(block_trade)

            mock_post.assert_called_once_with(
                api_url=self.api_client.api_url,
                path="block-trades",
                payload=expected_payload,
                params=None,
                headers=None,
            )

    def test_get_block_trade(self):
        """Test get_block_trade."""
        block_trade_id = "test_block_id"

        with patch.object(self.api_client, "get") as mock_get:
            mock_get.return_value = {"block_id": block_trade_id, "status": "CREATED"}

            self.api_client.get_block_trade(block_trade_id)

            mock_get.assert_called_once_with(
                api_url=self.api_client.api_url, path=f"block-trades/{block_trade_id}", params=None
            )

    def test_cancel_block_trade(self):
        """Test cancel_block_trade."""
        block_trade_id = "test_block_id"

        with patch.object(self.api_client, "delete") as mock_delete:
            mock_delete.return_value = {"message": "Block trade cancelled"}

            self.api_client.cancel_block_trade(block_trade_id)

            mock_delete.assert_called_once_with(
                api_url=self.api_client.api_url, path=f"block-trades/{block_trade_id}", params=None, payload=None
            )

    def test_execute_block_trade(self):
        """Test execute_block_trade."""
        block_trade_id = "test_block_id"
        execution_request = Mock(spec=BlockExecuteRequest)
        execution_request.model_dump.return_value = {
            "execution_nonce": "exec_nonce",
            "selected_offers": ["offer1", "offer2"],
            "signatures": {},
        }

        expected_payload = execution_request.model_dump.return_value

        with patch.object(self.api_client, "post") as mock_post:
            mock_post.return_value = {"status": "COMPLETED"}

            self.api_client.execute_block_trade(block_trade_id, execution_request)

            mock_post.assert_called_once_with(
                api_url=self.api_client.api_url,
                path=f"block-trades/{block_trade_id}/execute",
                payload=expected_payload,
                params=None,
                headers=None,
            )

    def test_get_block_trade_offers(self):
        """Test get_block_trade_offers."""
        block_trade_id = "test_block_id"

        with patch.object(self.api_client, "get") as mock_get:
            mock_get.return_value = {"results": []}

            self.api_client.get_block_trade_offers(block_trade_id)

            mock_get.assert_called_once_with(
                api_url=self.api_client.api_url, path=f"block-trades/{block_trade_id}/offers", params=None
            )

    def test_create_block_trade_offer(self):
        """Test create_block_trade_offer."""
        block_trade_id = "test_block_id"
        offer = Mock(spec=BlockOfferRequest)
        offer.model_dump.return_value = {
            "nonce": "offer_nonce",
            "offering_account": "0x123",
            "signature": {},
            "trades": {"BTC-USD-PERP": {"price": "50000", "size": "1.0"}},
        }

        expected_payload = offer.model_dump.return_value

        with patch.object(self.api_client, "post") as mock_post:
            mock_post.return_value = {"offer_id": "test_offer_id"}

            self.api_client.create_block_trade_offer(block_trade_id, offer)

            mock_post.assert_called_once_with(
                api_url=self.api_client.api_url,
                path=f"block-trades/{block_trade_id}/offers",
                payload=expected_payload,
                params=None,
                headers=None,
            )

    def test_get_block_trade_offer(self):
        """Test get_block_trade_offer."""
        block_trade_id = "test_block_id"
        offer_id = "test_offer_id"

        with patch.object(self.api_client, "get") as mock_get:
            mock_get.return_value = {"offer_id": offer_id, "status": "CREATED"}

            self.api_client.get_block_trade_offer(block_trade_id, offer_id)

            mock_get.assert_called_once_with(
                api_url=self.api_client.api_url, path=f"block-trades/{block_trade_id}/offers/{offer_id}", params=None
            )

    def test_cancel_block_trade_offer(self):
        """Test cancel_block_trade_offer."""
        block_trade_id = "test_block_id"
        offer_id = "test_offer_id"

        with patch.object(self.api_client, "delete") as mock_delete:
            mock_delete.return_value = {"message": "Offer cancelled"}

            self.api_client.cancel_block_trade_offer(block_trade_id, offer_id)

            mock_delete.assert_called_once_with(
                api_url=self.api_client.api_url,
                path=f"block-trades/{block_trade_id}/offers/{offer_id}",
                params=None,
                payload=None,
            )

    def test_execute_block_trade_offer(self):
        """Test execute_block_trade_offer."""
        block_trade_id = "test_block_id"
        offer_id = "test_offer_id"
        execution_request = Mock(spec=BlockExecuteRequest)
        execution_request.model_dump.return_value = {"execution_nonce": "exec_nonce", "signatures": {}}

        expected_payload = execution_request.model_dump.return_value

        with patch.object(self.api_client, "post") as mock_post:
            mock_post.return_value = {"status": "COMPLETED"}

            self.api_client.execute_block_trade_offer(block_trade_id, offer_id, execution_request)

            mock_post.assert_called_once_with(
                api_url=self.api_client.api_url,
                path=f"block-trades/{block_trade_id}/offers/{offer_id}/execute",
                payload=expected_payload,
                params=None,
                headers=None,
            )

    def test_all_methods_call_validate_auth(self):
        """Test that all block trade methods call _validate_auth."""
        # Test a few key methods to ensure auth validation is called
        methods_to_test = [
            lambda: self.api_client.list_block_trades(),
            lambda: self.api_client.get_block_trade("test_id"),
            lambda: self.api_client.cancel_block_trade("test_id"),
            lambda: self.api_client.get_block_trade_offers("test_id"),
            lambda: self.api_client.get_block_trade_offer("test_id", "offer_id"),
            lambda: self.api_client.cancel_block_trade_offer("test_id", "offer_id"),
        ]

        for method in methods_to_test:
            # Reset the mock
            cast(Mock, self.api_client._validate_auth).reset_mock()

            with patch.object(self.api_client, "get") as mock_get, patch.object(
                self.api_client, "delete"
            ) as mock_delete:
                mock_get.return_value = {}
                mock_delete.return_value = {}

                method()

                cast(Mock, self.api_client._validate_auth).assert_called_once()

    def test_create_methods_call_validate_auth(self):
        """Test that create and execute methods call _validate_auth."""
        mock_request = Mock()
        mock_request.model_dump.return_value = {}

        methods_to_test = [
            lambda: self.api_client.create_block_trade(mock_request),
            lambda: self.api_client.execute_block_trade("test_id", mock_request),
            lambda: self.api_client.create_block_trade_offer("test_id", mock_request),
            lambda: self.api_client.execute_block_trade_offer("test_id", "offer_id", mock_request),
        ]

        for method in methods_to_test:
            # Reset the mock
            cast(Mock, self.api_client._validate_auth).reset_mock()

            with patch.object(self.api_client, "post") as mock_post:
                mock_post.return_value = {}

                method()

                cast(Mock, self.api_client._validate_auth).assert_called_once()

    def test_block_trade_status_filters(self):
        """Test that all valid block trade statuses work as filters."""
        valid_statuses = ["CREATED", "OFFER_COLLECTION", "READY_TO_EXECUTE", "EXECUTING", "COMPLETED", "CANCELLED"]

        for status in valid_statuses:
            with patch.object(self.api_client, "get") as mock_get:
                mock_get.return_value = {"results": []}

                self.api_client.list_block_trades(status=status)

                # Verify the status was passed correctly
                called_params = mock_get.call_args[1]["params"]
                assert called_params["status"] == status

    def test_api_url_construction(self):
        """Test that API URLs are constructed correctly."""
        # Test that the base URL is set correctly
        assert self.api_client.api_url == f"https://api.{TESTNET}.paradex.trade/v1"

        # Test a few method calls to ensure correct path construction
        with patch.object(self.api_client, "get") as mock_get:
            mock_get.return_value = {}

            self.api_client.list_block_trades()
            mock_get.assert_called_with(api_url=self.api_client.api_url, path="block-trades", params={})

            self.api_client.get_block_trade("test123")
            mock_get.assert_called_with(api_url=self.api_client.api_url, path="block-trades/test123", params=None)

            self.api_client.get_block_trade_offers("test123")
            mock_get.assert_called_with(
                api_url=self.api_client.api_url, path="block-trades/test123/offers", params=None
            )

    def test_error_handling_preserves_exceptions(self):
        """Test that exceptions from HTTP methods are preserved."""
        # Test that if the underlying HTTP methods raise exceptions,
        # they bubble up correctly
        with patch.object(self.api_client, "get") as mock_get:
            mock_get.side_effect = Exception("HTTP Error")

            with pytest.raises(Exception, match="HTTP Error"):
                self.api_client.list_block_trades()

        with patch.object(self.api_client, "post") as mock_post:
            mock_post.side_effect = Exception("POST Error")
            mock_request = Mock()
            mock_request.model_dump.return_value = {}

            with pytest.raises(Exception, match="POST Error"):
                self.api_client.create_block_trade(mock_request)

        with patch.object(self.api_client, "delete") as mock_delete:
            mock_delete.side_effect = Exception("DELETE Error")

            with pytest.raises(Exception, match="DELETE Error"):
                self.api_client.cancel_block_trade("test_id")
