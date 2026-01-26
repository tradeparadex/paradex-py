"""Tests for HTTP compression support in HttpClient."""

import httpx

from paradex_py.api.http_client import HttpClient
from paradex_py.environment import TESTNET
from paradex_py.paradex import Paradex


class TestHttpCompression:
    """Test suite for HTTP compression configuration."""

    def test_compression_enabled_by_default(self):
        """Test that compression is enabled by default (httpx default behavior)."""
        http_client = HttpClient()

        # When compression is enabled, httpx automatically adds Accept-Encoding header
        # or doesn't explicitly set "identity"
        assert (
            "Accept-Encoding" not in http_client.client.headers
            or http_client.client.headers["Accept-Encoding"] != "identity"
        )

    def test_compression_explicitly_enabled(self):
        """Test that compression can be explicitly enabled."""
        http_client = HttpClient(enable_compression=True)

        # Should not set Accept-Encoding to identity
        assert (
            "Accept-Encoding" not in http_client.client.headers
            or http_client.client.headers["Accept-Encoding"] != "identity"
        )

    def test_compression_disabled(self):
        """Test that compression can be disabled."""
        http_client = HttpClient(enable_compression=False)

        # Should set Accept-Encoding to identity
        assert http_client.client.headers["Accept-Encoding"] == "identity"

    def test_compression_disabled_with_custom_client(self):
        """Test that compression can be disabled with custom injected client."""
        custom_client = httpx.Client()
        http_client = HttpClient(http_client=custom_client, enable_compression=False)

        # Should set Accept-Encoding to identity on custom client
        assert http_client.client.headers["Accept-Encoding"] == "identity"

    def test_compression_enabled_with_custom_client(self):
        """Test that compression is left as default with custom client when enabled."""
        custom_client = httpx.Client()
        http_client = HttpClient(http_client=custom_client, enable_compression=True)

        # Should not modify Accept-Encoding header when compression is enabled
        assert (
            "Accept-Encoding" not in http_client.client.headers
            or http_client.client.headers["Accept-Encoding"] != "identity"
        )

    def test_compression_overrides_custom_accept_encoding_when_disabled(self):
        """Test that disabling compression overrides custom Accept-Encoding header."""
        custom_client = httpx.Client()
        custom_client.headers["Accept-Encoding"] = "custom-encoding"
        http_client = HttpClient(http_client=custom_client, enable_compression=False)

        # When compression is explicitly disabled, should override custom Accept-Encoding
        assert http_client.client.headers["Accept-Encoding"] == "identity"

    def test_compression_disabled_via_paradex_constructor(self):
        """Test that compression can be disabled via Paradex constructor."""
        paradex = Paradex(env=TESTNET, enable_http_compression=False)

        # Should have created an HttpClient with compression disabled
        assert paradex.api_client.client.headers["Accept-Encoding"] == "identity"

    def test_compression_enabled_via_paradex_constructor(self):
        """Test that compression is enabled via Paradex constructor."""
        paradex = Paradex(env=TESTNET, enable_http_compression=True)

        # Should not have Accept-Encoding set to identity
        assert (
            "Accept-Encoding" not in paradex.api_client.client.headers
            or paradex.api_client.client.headers["Accept-Encoding"] != "identity"
        )

    def test_compression_default_via_paradex_constructor(self):
        """Test that compression is enabled by default when not specified."""
        paradex = Paradex(env=TESTNET)

        # Should use default compression behavior (not set to identity)
        # Note: Paradex doesn't create HttpClient when all parameters are default
        # So we check the underlying httpx client in the API client
        assert (
            "Accept-Encoding" not in paradex.api_client.client.headers
            or paradex.api_client.client.headers["Accept-Encoding"] != "identity"
        )

    def test_compression_with_other_http_options(self):
        """Test that compression works alongside other HTTP options."""
        http_client = HttpClient(enable_compression=False, default_timeout=30.0)

        # Should have both compression disabled and timeout set
        assert http_client.client.headers["Accept-Encoding"] == "identity"
        assert http_client.default_timeout == 30.0
