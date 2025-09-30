"""Tests for HTTP client enhancements: retry strategies, request hooks, timeouts, etc."""

from unittest.mock import patch

import httpx
import pytest

from paradex_py.api.http_client import HttpClient, HttpMethod
from paradex_py.api.protocols import DefaultRetryStrategy, NoOpSigner


class MockRetryStrategy:
    """Mock retry strategy for testing."""

    def __init__(self, max_retries=2, should_retry_responses=None, should_retry_exceptions=None):
        self.max_retries = max_retries
        self.should_retry_responses = should_retry_responses or []
        self.should_retry_exceptions = should_retry_exceptions or []
        self.delays = []

    def should_retry(self, attempt, response, exception):
        if attempt >= self.max_retries:
            return False
        if response and response.status_code in self.should_retry_responses:
            return True
        return exception and any(isinstance(exception, exc_type) for exc_type in self.should_retry_exceptions)

    def get_delay(self, attempt):
        delay = 0.01 * (2**attempt)  # Very short delays for testing
        self.delays.append(delay)
        return delay


class MockRequestHook:
    """Mock request hook for testing."""

    def __init__(self):
        self.requests = []
        self.responses = []

    def on_request(self, method, url, headers):
        self.requests.append({"method": method, "url": url, "headers": headers})

    def on_response(self, method, url, status_code, duration_ms):
        self.responses.append({"method": method, "url": url, "status_code": status_code, "duration_ms": duration_ms})


class TestHttpClientEnhancements:
    """Test HTTP client enhancements."""

    def setup_method(self):
        """Set up test fixtures."""
        self.http_client = HttpClient()

    def test_default_timeout_configuration(self):
        """Test default timeout configuration."""
        client = HttpClient(default_timeout=30.0)
        assert client.default_timeout == 30.0

        # Test with no default timeout
        client_no_timeout = HttpClient()
        assert client_no_timeout.default_timeout is None

    def test_retry_strategy_configuration(self):
        """Test retry strategy configuration."""
        retry_strategy = MockRetryStrategy(max_retries=3)
        client = HttpClient(retry_strategy=retry_strategy)
        assert client.retry_strategy is retry_strategy

    def test_request_hook_configuration(self):
        """Test request hook configuration."""
        request_hook = MockRequestHook()
        client = HttpClient(request_hook=request_hook)
        assert client.request_hook is request_hook

    @patch("httpx.Client.request")
    def test_request_with_timeout(self, mock_request):
        """Test request with timeout parameter."""
        mock_request.return_value = httpx.Response(200, json={"success": True})

        # Test with per-call timeout
        result = self.http_client.request(url="https://example.com/test", http_method=HttpMethod.GET, timeout=5.0)

        assert result == {"success": True}
        mock_request.assert_called_once()
        call_kwargs = mock_request.call_args[1]
        assert call_kwargs["timeout"] == 5.0

    @patch("httpx.Client.request")
    def test_request_with_default_timeout(self, mock_request):
        """Test request with default timeout."""
        mock_request.return_value = httpx.Response(200, json={"success": True})
        client = HttpClient(default_timeout=10.0)

        result = client.request(url="https://example.com/test", http_method=HttpMethod.GET)

        assert result == {"success": True}
        mock_request.assert_called_once()
        call_kwargs = mock_request.call_args[1]
        assert call_kwargs["timeout"] == 10.0

    @patch("httpx.Client.request")
    def test_request_timeout_override(self, mock_request):
        """Test per-call timeout overrides default timeout."""
        mock_request.return_value = httpx.Response(200, json={"success": True})
        client = HttpClient(default_timeout=10.0)

        result = client.request(url="https://example.com/test", http_method=HttpMethod.GET, timeout=5.0)

        assert result == {"success": True}
        mock_request.assert_called_once()
        call_kwargs = mock_request.call_args[1]
        assert call_kwargs["timeout"] == 5.0

    @patch("httpx.Client.request")
    @patch("time.sleep")  # Mock sleep to speed up tests
    def test_retry_strategy_on_server_error(self, mock_sleep, mock_request):
        """Test retry strategy on server errors."""
        retry_strategy = MockRetryStrategy(max_retries=2, should_retry_responses=[500])
        client = HttpClient(retry_strategy=retry_strategy)

        # All calls return 500, should exhaust retries and raise error
        mock_request.side_effect = [
            httpx.Response(500, json={"error": "INTERNAL_ERROR", "message": "server error", "data": None}),
            httpx.Response(500, json={"error": "INTERNAL_ERROR", "message": "server error", "data": None}),
            httpx.Response(500, json={"error": "INTERNAL_ERROR", "message": "server error", "data": None}),
        ]

        with pytest.raises(ValueError, match="server error"):
            client.request(url="https://example.com/test", http_method=HttpMethod.GET)

        # Should have called request 3 times (original + 2 retries)
        assert mock_request.call_count == 3
        assert mock_sleep.call_count == 2
        assert len(retry_strategy.delays) == 2

    @patch("httpx.Client.request")
    @patch("time.sleep")  # Mock sleep to speed up tests
    def test_retry_strategy_on_exception(self, mock_sleep, mock_request):
        """Test retry strategy on exceptions."""
        retry_strategy = MockRetryStrategy(max_retries=2, should_retry_exceptions=[httpx.RequestError])
        client = HttpClient(retry_strategy=retry_strategy)

        # First call raises exception, second call succeeds
        mock_request.side_effect = [
            httpx.RequestError("Connection failed"),
            httpx.Response(200, json={"success": True}),
        ]

        result = client.request(url="https://example.com/test", http_method=HttpMethod.GET)

        assert result == {"success": True}
        assert mock_request.call_count == 2
        assert mock_sleep.call_count == 1
        assert len(retry_strategy.delays) == 1

    @patch("httpx.Client.request")
    def test_request_hook_called(self, mock_request):
        """Test request hook is called properly."""
        mock_request.return_value = httpx.Response(200, json={"success": True})
        request_hook = MockRequestHook()
        client = HttpClient(request_hook=request_hook)

        result = client.request(
            url="https://example.com/test",
            http_method=HttpMethod.POST,
            headers={"Authorization": "Bearer token"},
        )

        assert result == {"success": True}

        # Check request hook was called
        assert len(request_hook.requests) == 1
        assert len(request_hook.responses) == 1

        request_data = request_hook.requests[0]
        assert request_data["method"] == "POST"
        assert request_data["url"] == "https://example.com/test"
        assert request_data["headers"]["Authorization"] == "[REDACTED]"  # Should be redacted

        response_data = request_hook.responses[0]
        assert response_data["method"] == "POST"
        assert response_data["url"] == "https://example.com/test"
        assert response_data["status_code"] == 200
        assert response_data["duration_ms"] > 0

    def test_header_redaction(self):
        """Test sensitive header redaction."""
        client = HttpClient()
        sensitive_headers = {
            "Authorization": "Bearer secret-token",
            "X-API-Key": "secret-key",
            "JWT": "jwt-token",
            "Token": "auth-token",
            "Content-Type": "application/json",
        }

        redacted = client._redact_headers(sensitive_headers)

        assert redacted["Authorization"] == "[REDACTED]"
        assert redacted["X-API-Key"] == "[REDACTED]"
        assert redacted["JWT"] == "[REDACTED]"
        assert redacted["Token"] == "[REDACTED]"  # noqa: S105
        assert redacted["Content-Type"] == "application/json"  # Not redacted

    def test_header_redaction_case_insensitive(self):
        """Test header redaction is case insensitive."""
        client = HttpClient()
        headers = {"authorization": "Bearer token", "X-Api-Key": "secret"}

        redacted = client._redact_headers(headers)

        assert redacted["authorization"] == "[REDACTED]"
        assert redacted["X-Api-Key"] == "[REDACTED]"

    def test_header_redaction_with_none(self):
        """Test header redaction with None input."""
        client = HttpClient()
        assert client._redact_headers(None) == {}
        assert client._redact_headers({}) == {}


class TestDefaultRetryStrategy:
    """Test the default retry strategy implementation."""

    def test_default_retry_strategy_max_retries(self):
        """Test default retry strategy respects max retries."""
        strategy = DefaultRetryStrategy(max_retries=3)

        # Should retry up to max_retries
        for attempt in range(3):
            assert strategy.should_retry(attempt, httpx.Response(500), None) is True

        # Should not retry beyond max_retries
        assert strategy.should_retry(3, httpx.Response(500), None) is False

    def test_default_retry_strategy_server_errors(self):
        """Test default retry strategy retries on server errors."""
        strategy = DefaultRetryStrategy()

        # Should retry on 5xx errors
        assert strategy.should_retry(0, httpx.Response(500), None) is True
        assert strategy.should_retry(0, httpx.Response(502), None) is True
        assert strategy.should_retry(0, httpx.Response(503), None) is True

        # Should not retry on 4xx errors
        assert strategy.should_retry(0, httpx.Response(400), None) is False
        assert strategy.should_retry(0, httpx.Response(404), None) is False

        # Should not retry on 2xx success
        assert strategy.should_retry(0, httpx.Response(200), None) is False

    def test_default_retry_strategy_rate_limit(self):
        """Test default retry strategy retries on rate limits."""
        strategy = DefaultRetryStrategy()

        # Should retry on 429 rate limit
        assert strategy.should_retry(0, httpx.Response(429), None) is True

    def test_default_retry_strategy_exceptions(self):
        """Test default retry strategy retries on exceptions."""
        strategy = DefaultRetryStrategy()

        # Should retry on network exceptions
        assert strategy.should_retry(0, None, httpx.RequestError("Connection failed")) is True
        assert strategy.should_retry(0, None, Exception("Generic error")) is True

    def test_default_retry_strategy_exponential_backoff(self):
        """Test default retry strategy exponential backoff."""
        strategy = DefaultRetryStrategy(base_delay=1.0, max_delay=10.0)

        # Should implement exponential backoff
        assert strategy.get_delay(0) == 1.0  # 1.0 * 2^0
        assert strategy.get_delay(1) == 2.0  # 1.0 * 2^1
        assert strategy.get_delay(2) == 4.0  # 1.0 * 2^2
        assert strategy.get_delay(3) == 8.0  # 1.0 * 2^3
        assert strategy.get_delay(4) == 10.0  # Capped at max_delay

    def test_default_retry_strategy_custom_parameters(self):
        """Test default retry strategy with custom parameters."""
        strategy = DefaultRetryStrategy(max_retries=5, base_delay=0.5, max_delay=30.0)

        assert strategy.max_retries == 5
        assert strategy.base_delay == 0.5
        assert strategy.max_delay == 30.0

        # Test delay calculation with custom base
        assert strategy.get_delay(0) == 0.5
        assert strategy.get_delay(1) == 1.0
        assert strategy.get_delay(2) == 2.0


class TestNoOpSigner:
    """Test the no-op signer for simulation."""

    def test_noop_signer_sign_order(self):
        """Test no-op signer returns order data unchanged."""
        signer = NoOpSigner()
        order_data = {"symbol": "BTC-USD-PERP", "side": "BUY", "size": "0.1"}

        result = signer.sign_order(order_data)

        assert result is order_data  # Should return same object
        assert result == {"symbol": "BTC-USD-PERP", "side": "BUY", "size": "0.1"}

    def test_noop_signer_sign_batch(self):
        """Test no-op signer returns batch unchanged."""
        signer = NoOpSigner()
        orders = [
            {"symbol": "BTC-USD-PERP", "side": "BUY", "size": "0.1"},
            {"symbol": "ETH-USD-PERP", "side": "SELL", "size": "1.0"},
        ]

        result = signer.sign_batch(orders)

        assert result is orders  # Should return same object
        assert len(result) == 2
        assert result[0] == {"symbol": "BTC-USD-PERP", "side": "BUY", "size": "0.1"}
        assert result[1] == {"symbol": "ETH-USD-PERP", "side": "SELL", "size": "1.0"}
