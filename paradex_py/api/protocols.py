"""
Injection protocols and type contracts for paradex_py.

This module exports all the protocols that define injection points
for custom implementations in simulation, testing, and production environments.
"""

from typing import Any, Protocol

import httpx


# WebSocket protocols
class WebSocketConnection(Protocol):
    """Protocol for WebSocket connection implementations."""

    async def send(self, data: str) -> None:
        """Send data through the WebSocket."""
        ...

    async def recv(self) -> str:
        """Receive data from the WebSocket."""
        ...

    async def close(self) -> None:
        """Close the WebSocket connection."""
        ...

    @property
    def state(self) -> Any:
        """Get connection state."""
        ...


class WebSocketConnector(Protocol):
    """Protocol for WebSocket connector implementations."""

    async def __call__(self, url: str, headers: dict[str, str]) -> WebSocketConnection:
        """Create a WebSocket connection.

        Args:
            url: WebSocket URL to connect to
            headers: Connection headers

        Returns:
            WebSocket connection instance
        """
        ...


# HTTP protocols
class HttpClientLike(Protocol):
    """Protocol for HTTP client implementations."""

    def request(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        json: Any = None,
        headers: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> httpx.Response:
        """Make HTTP request."""
        ...


class TransportLike(Protocol):
    """Protocol for HTTP transport implementations."""

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        """Handle HTTP request and return response."""
        ...


class RetryStrategy(Protocol):
    """Protocol for retry/backoff strategies."""

    def should_retry(self, attempt: int, response: httpx.Response | None, exception: Exception | None) -> bool:
        """Determine if request should be retried.

        Args:
            attempt: Current attempt number (0-based)
            response: HTTP response if available
            exception: Exception if request failed

        Returns:
            True if request should be retried
        """
        ...

    def get_delay(self, attempt: int) -> float:
        """Get delay before next retry attempt.

        Args:
            attempt: Current attempt number (0-based)

        Returns:
            Delay in seconds
        """
        ...


class RequestHook(Protocol):
    """Protocol for request/response observability hooks."""

    def on_request(self, method: str, url: str, headers: dict[str, Any] | None) -> None:
        """Called before making request.

        Args:
            method: HTTP method
            url: Request URL (potentially redacted)
            headers: Request headers (potentially redacted)
        """
        ...

    def on_response(self, method: str, url: str, status_code: int, duration_ms: float) -> None:
        """Called after receiving response.

        Args:
            method: HTTP method
            url: Request URL (potentially redacted)
            status_code: HTTP status code
            duration_ms: Request duration in milliseconds
        """
        ...


class AuthProvider(Protocol):
    """Protocol for custom authentication flows."""

    def get_token(self) -> str | None:
        """Get current JWT token.

        Returns:
            JWT token string or None if not available
        """
        ...

    def refresh_if_needed(self) -> str | None:
        """Refresh token if needed and return current token.

        Returns:
            JWT token string or None if refresh failed
        """
        ...


# Signing protocols
class Signer(Protocol):
    """Protocol for order signing implementations."""

    def sign_order(self, order_data: dict[str, Any]) -> dict[str, Any]:
        """Sign an order.

        Args:
            order_data: Order data to sign

        Returns:
            Signed order data with signature fields
        """
        ...

    def sign_batch(self, orders: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Sign multiple orders.

        Args:
            orders: List of orders to sign

        Returns:
            List of signed orders
        """
        ...


# Default implementations
class DefaultRetryStrategy:
    """Default exponential backoff retry strategy."""

    def __init__(self, max_retries: int = 3, base_delay: float = 1.0, max_delay: float = 60.0):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay

    def should_retry(self, attempt: int, response: Any | None, exception: Exception | None) -> bool:
        if attempt >= self.max_retries:
            return False

        # Retry on network errors
        if exception is not None:
            return True

        # Retry on 5xx errors and rate limits
        if response is not None:
            return response.status_code >= 500 or response.status_code == 429

        return False

    def get_delay(self, attempt: int) -> float:
        delay = self.base_delay * (2**attempt)
        return min(delay, self.max_delay)


class NoOpSigner:
    """No-op signer for full simulation scenarios."""

    def sign_order(self, order_data: dict[str, Any]) -> dict[str, Any]:
        """Return order data without signing."""
        return order_data

    def sign_batch(self, orders: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Return orders without signing."""
        return orders


# Type aliases for common injection types
ClientConnectionLike = WebSocketConnection
WebsocketConnectorLike = WebSocketConnector

# Export all protocols
__all__ = [
    # WebSocket protocols
    "WebSocketConnection",
    "WebSocketConnector",
    "ClientConnectionLike",  # Alias
    "WebsocketConnectorLike",  # Alias
    # HTTP protocols
    "HttpClientLike",
    "TransportLike",
    "RetryStrategy",
    "RequestHook",
    # Auth protocols
    "AuthProvider",
    # Signing protocols
    "Signer",
    "NoOpSigner",
    # Default implementations
    "DefaultRetryStrategy",
]
