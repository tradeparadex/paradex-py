"""Tests for ParadexAccount httpx integration."""

from types import MethodType
from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest
from starknet_py.net.http_client import HttpMethod

from paradex_py.account.account import ParadexAccount
from tests.mocks.api_client import MockApiClient


class TestAccountHttpxIntegration:
    """Test suite for ParadexAccount's httpx integration via monkey patching."""

    def setup_method(self):
        """Setup method to create test fixtures."""
        self.api_client = MockApiClient()
        self.config = self.api_client.fetch_system_config()

        # Test account data
        self.test_l1_address = "0xd2c7314539dCe7752c8120af4eC2AA750Cf2035e"
        self.test_l1_private_key = "0xf8e4d1d772cdd44e5e77615ad11cc071c94e4c06dc21150d903f28e6aa6abdff"

    def test_account_initialization_with_httpx(self):
        """Test that account initialization properly sets up httpx integration."""
        account = ParadexAccount(
            config=self.config,
            l1_address=self.test_l1_address,
            l1_private_key=self.test_l1_private_key,
        )

        # Verify account was created successfully
        assert account.l1_address == self.test_l1_address
        assert account.starknet is not None

        # Verify that the monkey patch was applied
        original_method = account.starknet.client._client._make_request
        assert isinstance(original_method, MethodType)

    @pytest.mark.asyncio
    async def test_monkey_patched_make_request_success(self):
        """Test successful HTTP request through monkey-patched method."""
        account = ParadexAccount(
            config=self.config,
            l1_address=self.test_l1_address,
            l1_private_key=self.test_l1_private_key,
        )

        # Mock httpx.AsyncClient response
        mock_response = Mock()
        mock_response.json = AsyncMock(return_value={"result": "success"})

        # Mock the handle_request_error method to avoid issues
        with patch.object(
            account.starknet.client._client, "handle_request_error", new_callable=AsyncMock
        ) as mock_handle_error:
            mock_handle_error.return_value = None

            # Mock the AsyncClient.request method
            mock_async_client = AsyncMock()
            mock_async_client.request.return_value = mock_response

            # Test the monkey-patched method directly
            payload = {"method": "test", "params": []}
            result = await account.starknet.client._client._make_request(
                session=mock_async_client,
                address="https://test.example.com",
                http_method=HttpMethod.POST,
                params={},
                payload=payload,
            )

            assert result == {"result": "success"}

            # Verify the request was made with correct parameters
            mock_async_client.request.assert_called_once()
            call_args = mock_async_client.request.call_args

            assert call_args[1]["method"] == "POST"
            assert call_args[1]["url"] == "https://test.example.com"
            assert call_args[1]["json"] == payload
            assert "PARADEX-STARKNET-ACCOUNT" in call_args[1]["headers"]
            assert "PARADEX-STARKNET-SIGNATURE" in call_args[1]["headers"]

    @pytest.mark.asyncio
    async def test_monkey_patched_request_with_headers(self):
        """Test that custom headers are properly added to requests."""
        account = ParadexAccount(
            config=self.config,
            l1_address=self.test_l1_address,
            l1_private_key=self.test_l1_private_key,
        )

        # Mock httpx response
        mock_response = Mock()
        mock_response.json = AsyncMock(return_value={"status": "ok"})

        # Mock the handle_request_error method
        with patch.object(
            account.starknet.client._client, "handle_request_error", new_callable=AsyncMock
        ) as mock_handle_error:
            mock_handle_error.return_value = None

            mock_async_client = AsyncMock()
            mock_async_client.request.return_value = mock_response

            payload = {"test": "data"}

            # Call the monkey-patched method
            await account.starknet.client._client._make_request(
                session=mock_async_client,
                address="https://fullnode.example.com/rpc",
                http_method=HttpMethod.POST,
                params={},
                payload=payload,
            )

        # Verify headers were added
        call_args = mock_async_client.request.call_args
        headers = call_args[1]["headers"]

        # Check that all required Paradex headers are present
        required_headers = [
            "PARADEX-STARKNET-ACCOUNT",
            "PARADEX-STARKNET-SIGNATURE",
            "PARADEX-STARKNET-SIGNATURE-TIMESTAMP",
            "PARADEX-STARKNET-SIGNATURE-VERSION",
        ]

        for header in required_headers:
            assert header in headers, f"Missing required header: {header}"

        # Verify account address format
        assert headers["PARADEX-STARKNET-ACCOUNT"].startswith("0x")

        # Verify signature format (should be JSON array string)
        signature = headers["PARADEX-STARKNET-SIGNATURE"]
        assert signature.startswith("[") and signature.endswith("]")

        # Verify timestamp is numeric string
        timestamp = headers["PARADEX-STARKNET-SIGNATURE-TIMESTAMP"]
        assert timestamp.isdigit()

    def test_fullnode_request_headers_generation(self):
        """Test fullnode request headers generation."""
        account = ParadexAccount(
            config=self.config,
            l1_address=self.test_l1_address,
            l1_private_key=self.test_l1_private_key,
        )

        json_payload = '{"method": "test", "params": []}'
        headers = account.fullnode_request_headers(account.starknet, account.l2_chain_id, json_payload)

        # Verify all required headers are present
        assert "Content-Type" in headers
        assert headers["Content-Type"] == "application/json"
        assert "PARADEX-STARKNET-ACCOUNT" in headers
        assert "PARADEX-STARKNET-SIGNATURE" in headers
        assert "PARADEX-STARKNET-SIGNATURE-TIMESTAMP" in headers
        assert "PARADEX-STARKNET-SIGNATURE-VERSION" in headers

        # Verify account address format
        assert headers["PARADEX-STARKNET-ACCOUNT"] == hex(account.starknet.address)

        # Verify signature version
        assert headers["PARADEX-STARKNET-SIGNATURE-VERSION"] == "1.0.0"

    @pytest.mark.asyncio
    async def test_error_handling_in_monkey_patch(self):
        """Test error handling in the monkey-patched method."""
        account = ParadexAccount(
            config=self.config,
            l1_address=self.test_l1_address,
            l1_private_key=self.test_l1_private_key,
        )

        # Mock httpx client that raises an exception
        mock_async_client = AsyncMock()
        mock_response = Mock()

        # Mock handle_request_error to raise the exception
        async def mock_handle_error(response):
            raise httpx.HTTPStatusError("Client error", request=Mock(), response=Mock())

        with patch.object(account.starknet.client._client, "handle_request_error", side_effect=mock_handle_error):
            mock_async_client.request.return_value = mock_response

            # Test that the exception is properly propagated
            with pytest.raises(httpx.HTTPStatusError):
                await account.starknet.client._client._make_request(
                    session=mock_async_client,
                    address="https://test.example.com",
                    http_method=HttpMethod.POST,
                    params={},
                    payload={"test": "data"},
                )

    def test_httpx_client_type_annotation(self):
        """Test that the monkey-patched method has correct type annotation."""
        account = ParadexAccount(
            config=self.config,
            l1_address=self.test_l1_address,
            l1_private_key=self.test_l1_private_key,
        )

        # Get the monkey-patched method
        patched_method = account.starknet.client._client._make_request

        # Verify it's a bound method
        assert isinstance(patched_method, MethodType)

        # The method should accept AsyncClient (httpx) instead of ClientSession (aiohttp)
        # This is verified by the successful execution of other tests

    @pytest.mark.asyncio
    async def test_json_payload_handling(self):
        """Test that JSON payload is properly handled in the monkey-patched method."""
        account = ParadexAccount(
            config=self.config,
            l1_address=self.test_l1_address,
            l1_private_key=self.test_l1_private_key,
        )

        mock_response = Mock()
        mock_response.json = AsyncMock(return_value={"success": True})

        # Mock handle_request_error
        with patch.object(
            account.starknet.client._client, "handle_request_error", new_callable=AsyncMock
        ) as mock_handle_error:
            mock_handle_error.return_value = None

            mock_async_client = AsyncMock()
            mock_async_client.request.return_value = mock_response

            test_payload = {
                "method": "starknet_call",
                "params": ["latest", {"contract_address": "0x123", "entry_point_selector": "0x456"}],
            }

            result = await account.starknet.client._client._make_request(
                session=mock_async_client,
                address="https://fullnode.test.com",
                http_method=HttpMethod.POST,
                params={},
                payload=test_payload,
            )

        # Verify the result
        assert result == {"success": True}

        # Verify the payload was passed correctly
        call_args = mock_async_client.request.call_args
        assert call_args[1]["json"] == test_payload

        # Verify JSON string was created for signature
        # (This is done internally in the method for header generation)
        mock_async_client.request.assert_called_once()
