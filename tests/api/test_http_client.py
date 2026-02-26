"""Tests for HttpClient using httpx."""

from unittest.mock import Mock, patch

import httpx
import pytest

from paradex_py.api.http_client import HttpClient, HttpMethod, _parse_rate_limit
from paradex_py.api.models import ApiErrorSchema, RateLimitInfo


class TestHttpClient:
    """Test suite for HttpClient with httpx."""

    def setup_method(self):
        """Setup method to create an HttpClient instance for each test."""
        self.http_client = HttpClient()

    def test_init_creates_httpx_client(self):
        """Test that HttpClient initializes with httpx.Client."""
        assert isinstance(self.http_client.client, httpx.Client)
        assert self.http_client.client.headers["Content-Type"] == "application/json"
        assert "User-Agent" in self.http_client.client.headers
        assert self.http_client.client.headers["User-Agent"].startswith("paradex-py/")

    @patch("httpx.Client.request")
    def test_request_success(self, mock_request):
        """Test successful HTTP request."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "success"}
        mock_request.return_value = mock_response

        result = self.http_client.request(
            url="https://api.example.com/test",
            http_method=HttpMethod.GET,
            params={"param1": "value1"},
            payload={"data": "test"},
            headers={"Custom-Header": "test"},
        )

        assert result == {"status": "success"}
        mock_request.assert_called_once_with(
            method="GET",
            url="https://api.example.com/test",
            params={"param1": "value1"},
            json={"data": "test"},
            headers={"Custom-Header": "test"},
        )

    @patch("httpx.Client.request")
    def test_request_rate_limit_error(self, mock_request):
        """Test rate limit error handling."""
        mock_response = Mock()
        mock_response.status_code = 429
        mock_request.return_value = mock_response

        with pytest.raises(Exception, match="Rate limit exceeded"):
            self.http_client.request(url="https://api.example.com/test", http_method=HttpMethod.GET)

    @patch("httpx.Client.request")
    def test_request_api_error(self, mock_request):
        """Test API error handling for status codes >= 300."""
        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.text = '{"error": "Bad Request"}'
        mock_request.return_value = mock_response

        with patch.object(ApiErrorSchema, "loads", return_value="Bad Request"), pytest.raises(
            Exception, match="Bad Request"
        ):
            self.http_client.request(url="https://api.example.com/test", http_method=HttpMethod.POST)

    @patch("httpx.Client.request")
    def test_request_204_no_content(self, mock_request, caplog):
        """Test handling of 204 No Content responses (no warning expected)."""
        mock_response = Mock()
        mock_response.status_code = 204
        mock_request.return_value = mock_response

        result = self.http_client.request(url="https://api.example.com/test", http_method=HttpMethod.DELETE)

        assert result is None
        # No warning should be logged for 204 No Content
        assert "Invalid JSON" not in caplog.text

    @patch("httpx.Client.request")
    def test_request_json_parse_error(self, mock_request, caplog):
        """Test handling of JSON parse errors (warning expected)."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.side_effect = ValueError("Invalid JSON")
        mock_request.return_value = mock_response

        result = self.http_client.request(url="https://api.example.com/test", http_method=HttpMethod.GET)

        assert result is None
        assert "HttpClient: Invalid JSON in response request(https://api.example.com/test, GET)" in caplog.text

    def test_get_method(self):
        """Test GET method wrapper."""
        with patch.object(self.http_client, "request") as mock_request:
            mock_request.return_value = {"data": "test"}

            result = self.http_client.get(api_url="https://api.example.com", path="endpoint", params={"param": "value"})

            assert result == {"data": "test"}
            mock_request.assert_called_once_with(
                url="https://api.example.com/endpoint",
                http_method=HttpMethod.GET,
                params={"param": "value"},
                headers=self.http_client.client.headers,
                timeout=None,
            )

    def test_post_method_with_default_headers(self):
        """Test POST method with default headers."""
        with patch.object(self.http_client, "request") as mock_request:
            mock_request.return_value = {"success": True}

            result = self.http_client.post(api_url="https://api.example.com", path="create", payload={"data": "test"})

            assert result == {"success": True}
            mock_request.assert_called_once_with(
                url="https://api.example.com/create",
                http_method=HttpMethod.POST,
                payload={"data": "test"},
                params=None,
                headers=self.http_client.client.headers,
                timeout=None,
            )

    def test_post_method_with_custom_headers(self):
        """Test POST method with custom headers."""
        custom_headers = {"Authorization": "Bearer token"}

        with patch.object(self.http_client, "request") as mock_request:
            mock_request.return_value = {"success": True}

            result = self.http_client.post(
                api_url="https://api.example.com", path="create", payload={"data": "test"}, headers=custom_headers
            )

            assert result == {"success": True}
            mock_request.assert_called_once_with(
                url="https://api.example.com/create",
                http_method=HttpMethod.POST,
                payload={"data": "test"},
                params=None,
                headers=custom_headers,
                timeout=None,
            )

    def test_put_method(self):
        """Test PUT method wrapper."""
        with patch.object(self.http_client, "request") as mock_request:
            mock_request.return_value = {"updated": True}

            result = self.http_client.put(
                api_url="https://api.example.com", path="update/123", payload={"data": "updated"}
            )

            assert result == {"updated": True}
            mock_request.assert_called_once_with(
                url="https://api.example.com/update/123",
                http_method=HttpMethod.PUT,
                payload={"data": "updated"},
                params=None,
                headers=self.http_client.client.headers,
                timeout=None,
            )

    def test_delete_method(self):
        """Test DELETE method wrapper."""
        with patch.object(self.http_client, "request") as mock_request:
            mock_request.return_value = {"deleted": True}

            result = self.http_client.delete(
                api_url="https://api.example.com",
                path="delete/123",
                params={"confirm": "true"},
                payload={"reason": "test"},
            )

            assert result == {"deleted": True}
            mock_request.assert_called_once_with(
                url="https://api.example.com/delete/123",
                http_method=HttpMethod.DELETE,
                params={"confirm": "true"},
                payload={"reason": "test"},
                headers=self.http_client.client.headers,
                timeout=None,
            )

    def test_http_method_enum(self):
        """Test HttpMethod enum values."""
        assert HttpMethod.GET.value == "GET"
        assert HttpMethod.POST.value == "POST"
        assert HttpMethod.PUT.value == "PUT"
        assert HttpMethod.DELETE.value == "DELETE"

    def test_all_http_methods_supported(self):
        """Test that all HTTP methods are properly handled."""
        methods_to_test = [
            (HttpMethod.GET, "GET"),
            (HttpMethod.POST, "POST"),
            (HttpMethod.PUT, "PUT"),
            (HttpMethod.DELETE, "DELETE"),
        ]

        for method_enum, method_string in methods_to_test:
            with patch("httpx.Client.request") as mock_request:
                mock_response = Mock()
                mock_response.status_code = 200
                mock_response.json.return_value = {"method": method_string}
                mock_request.return_value = mock_response

                result = self.http_client.request(url="https://api.example.com/test", http_method=method_enum)

                assert result == {"method": method_string}
                mock_request.assert_called_with(
                    method=method_string, url="https://api.example.com/test", params=None, json=None, headers=None
                )

    def test_user_agent_set_on_initialization(self):
        """Test that User-Agent header is set during initialization."""
        http_client = HttpClient()

        assert "User-Agent" in http_client.client.headers
        user_agent = http_client.client.headers["User-Agent"]
        assert user_agent.startswith("paradex-py/")
        assert "Python" in user_agent

    def test_user_agent_preserved_with_custom_client(self):
        """Test that User-Agent is not overridden if custom client already has it."""
        custom_client = httpx.Client()
        custom_user_agent = "custom-agent/1.0"
        custom_client.headers["User-Agent"] = custom_user_agent

        http_client = HttpClient(http_client=custom_client)

        # Custom User-Agent should be preserved
        assert http_client.client.headers["User-Agent"] == custom_user_agent


class TestRateLimitInfo:
    """Tests for RateLimitInfo parsing and last_rate_limit on HttpClient."""

    def test_parse_rate_limit_full_headers(self):
        """_parse_rate_limit returns RateLimitInfo when all x-ratelimit-* headers present."""
        res = Mock(spec=httpx.Response)
        res.headers = {
            "x-ratelimit-limit": "20",
            "x-ratelimit-remaining": "19",
            "x-ratelimit-reset": "1770947024",
            "x-ratelimit-window": "1",
        }
        info = _parse_rate_limit(res)
        assert info == RateLimitInfo(limit=20, remaining=19, reset=1770947024, window=1)

    def test_parse_rate_limit_partial_headers(self):
        """_parse_rate_limit sets only present headers; others are None."""
        res = Mock(spec=httpx.Response)
        res.headers = {"x-ratelimit-limit": "10", "x-ratelimit-remaining": "5"}
        info = _parse_rate_limit(res)
        assert info.limit == 10
        assert info.remaining == 5
        assert info.reset is None
        assert info.window is None

    def test_parse_rate_limit_no_headers(self):
        """_parse_rate_limit returns all None when no rate limit headers."""
        res = Mock(spec=httpx.Response)
        res.headers = {}
        info = _parse_rate_limit(res)
        assert info == RateLimitInfo(limit=None, remaining=None, reset=None, window=None)

    def test_parse_rate_limit_invalid_integer_skipped(self):
        """_parse_rate_limit skips headers that do not parse as int."""
        res = Mock(spec=httpx.Response)
        res.headers = {
            "x-ratelimit-limit": "20",
            "x-ratelimit-remaining": "not-a-number",
            "x-ratelimit-reset": "1770947024",
            "x-ratelimit-window": "1",
        }
        info = _parse_rate_limit(res)
        assert info.limit == 20
        assert info.remaining is None
        assert info.reset == 1770947024
        assert info.window == 1

    def test_last_rate_limit_initially_none(self):
        """last_rate_limit is None before any request."""
        client = HttpClient()
        assert client.last_rate_limit is None

    @patch("httpx.Client.request")
    def test_last_rate_limit_set_after_success(self, mock_request):
        """last_rate_limit is set from x-ratelimit-* headers after successful request."""
        client = HttpClient()
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "ok"}
        mock_response.headers = {
            "x-ratelimit-limit": "20",
            "x-ratelimit-remaining": "18",
            "x-ratelimit-reset": "1770947025",
            "x-ratelimit-window": "1",
        }
        mock_request.return_value = mock_response

        client.request(url="https://api.example.com/test", http_method=HttpMethod.GET)

        assert client.last_rate_limit is not None
        assert client.last_rate_limit.limit == 20
        assert client.last_rate_limit.remaining == 18
        assert client.last_rate_limit.reset == 1770947025
        assert client.last_rate_limit.window == 1

    @patch("httpx.Client.request")
    def test_last_rate_limit_set_after_429(self, mock_request):
        """last_rate_limit is set from 429 response so caller can read reset time."""
        client = HttpClient()
        mock_response = Mock()
        mock_response.status_code = 429
        mock_response.headers = {
            "x-ratelimit-limit": "20",
            "x-ratelimit-remaining": "0",
            "x-ratelimit-reset": "1770947030",
            "x-ratelimit-window": "1",
        }
        mock_request.return_value = mock_response

        with pytest.raises(Exception, match="Rate limit exceeded"):
            client.request(url="https://api.example.com/test", http_method=HttpMethod.GET)

        assert client.last_rate_limit is not None
        assert client.last_rate_limit.remaining == 0
        assert client.last_rate_limit.reset == 1770947030

    @patch("httpx.Client.request")
    def test_last_rate_limit_all_none_when_no_headers(self, mock_request):
        """last_rate_limit has all-None fields when response has no rate limit headers."""
        client = HttpClient()
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": "ok"}
        mock_response.headers = {}
        mock_request.return_value = mock_response

        client.request(url="https://api.example.com/test", http_method=HttpMethod.GET)

        assert client.last_rate_limit is not None
        assert client.last_rate_limit == RateLimitInfo(limit=None, remaining=None, reset=None, window=None)

    @patch("httpx.Client.request")
    def test_last_rate_limit_overwritten_by_next_request(self, mock_request):
        """last_rate_limit reflects the most recent response."""
        client = HttpClient()
        mock_request.return_value = Mock(
            status_code=200,
            json=Mock(return_value={"a": 1}),
            headers={
                "x-ratelimit-limit": "20",
                "x-ratelimit-remaining": "10",
                "x-ratelimit-reset": "100",
                "x-ratelimit-window": "1",
            },
        )

        client.request(url="https://api.example.com/first", http_method=HttpMethod.GET)
        first = client.last_rate_limit
        assert first is not None and first.remaining == 10

        mock_request.return_value = Mock(
            status_code=200,
            json=Mock(return_value={"b": 2}),
            headers={
                "x-ratelimit-limit": "20",
                "x-ratelimit-remaining": "9",
                "x-ratelimit-reset": "101",
                "x-ratelimit-window": "1",
            },
        )
        client.request(url="https://api.example.com/second", http_method=HttpMethod.GET)
        second = client.last_rate_limit
        assert second is not None and second.remaining == 9
