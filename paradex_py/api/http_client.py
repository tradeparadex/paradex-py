import time
from enum import Enum
from typing import Any

import httpx

from paradex_py.api.models import ApiErrorSchema
from paradex_py.api.protocols import RequestHook, RetryStrategy
from paradex_py.user_agent import get_user_agent
from paradex_py.utils import raise_value_error


class HttpMethod(Enum):
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    DELETE = "DELETE"


class HttpClient:
    def __init__(
        self,
        http_client: httpx.Client | None = None,
        default_timeout: float | None = None,
        retry_strategy: RetryStrategy | None = None,
        request_hook: RequestHook | None = None,
        enable_compression: bool = True,
    ):
        """Initialize HTTP client with optional injection.

        Args:
            http_client: Optional httpx.Client instance for injection.
                        If None, creates a default client.
            default_timeout: Default timeout for requests in seconds.
            retry_strategy: Strategy for retrying failed requests.
            request_hook: Hook for request/response observability.
            enable_compression: Enable HTTP compression (gzip, deflate, br). Defaults to True.
        """
        if http_client is not None:
            self.client = http_client
            # Only set headers if not already set in custom client
            if "Content-Type" not in self.client.headers:
                self.client.headers.update({"Content-Type": "application/json"})
            if "User-Agent" not in self.client.headers:
                self.client.headers.update({"User-Agent": get_user_agent()})
            # Disable compression if requested (for injected clients)
            # Override any existing Accept-Encoding header to disable compression
            if not enable_compression:
                self.client.headers.update({"Accept-Encoding": "identity"})
        else:
            self.client = httpx.Client()
            # Always set our headers for default client (overriding httpx defaults)
            headers = {
                "Content-Type": "application/json",
                "User-Agent": get_user_agent(),
            }
            # Disable compression if requested
            if not enable_compression:
                headers["Accept-Encoding"] = "identity"
            self.client.headers.update(headers)

        self.default_timeout = default_timeout
        self.retry_strategy = retry_strategy
        self.request_hook = request_hook

    def _prepare_request_kwargs(
        self,
        http_method: HttpMethod,
        url: str,
        params: dict | None,
        payload: dict[str, Any] | list[dict[str, Any]] | None,
        headers: Any | None,
        request_timeout: float | None,
    ) -> dict:
        """Prepare request kwargs for httpx."""
        request_kwargs = {
            "method": http_method.value,
            "url": url,
            "params": params,
            "json": payload,
            "headers": headers,
        }
        if request_timeout is not None:
            request_kwargs["timeout"] = request_timeout
        return request_kwargs

    def _handle_response(self, res: httpx.Response, url: str, http_method: HttpMethod) -> Any:
        """Handle HTTP response and return parsed data."""
        # Handle errors
        if res.status_code == 429:
            return raise_value_error("Rate limit exceeded")
        if res.status_code >= 300:
            error = ApiErrorSchema().loads(res.text)
            return raise_value_error(str(error))

        # Return successful response
        try:
            return res.json()
        except ValueError:
            print(f"HttpClient: No response request({url}, {http_method.value})")
            return None

    def request(
        self,
        url: str,
        http_method: HttpMethod,
        params: dict | None = None,
        payload: dict[str, Any] | list[dict[str, Any]] | None = None,
        headers: Any | None = None,
        timeout: float | None = None,
    ):
        """Make HTTP request with retry logic and observability hooks.

        Args:
            url: Request URL
            http_method: HTTP method
            params: Query parameters
            payload: Request body payload
            headers: Request headers
            timeout: Request timeout in seconds (overrides default_timeout)
        """
        # Use provided timeout or default
        request_timeout = timeout if timeout is not None else self.default_timeout

        # Redact sensitive headers for logging
        safe_headers = self._redact_headers(headers) if headers else None

        # Call request hook
        if self.request_hook:
            self.request_hook.on_request(http_method.value, url, safe_headers)

        attempt = 0
        start_time = time.time()

        while True:
            try:
                request_kwargs = self._prepare_request_kwargs(
                    http_method, url, params, payload, headers, request_timeout
                )
                res = self.client.request(**request_kwargs)

                # Call response hook
                if self.request_hook:
                    duration_ms = (time.time() - start_time) * 1000
                    self.request_hook.on_response(http_method.value, url, res.status_code, duration_ms)

                # Check if we should retry
                if self.retry_strategy and self.retry_strategy.should_retry(attempt, res, None):
                    delay = self.retry_strategy.get_delay(attempt)
                    time.sleep(delay)
                    attempt += 1
                    continue
                else:
                    return self._handle_response(res, url, http_method)

            except Exception as e:
                # Check if we should retry on exception
                if self.retry_strategy and self.retry_strategy.should_retry(attempt, None, e):
                    delay = self.retry_strategy.get_delay(attempt)
                    time.sleep(delay)
                    attempt += 1
                    continue
                else:
                    # Re-raise if no more retries
                    raise

    def _redact_headers(self, headers: dict[str, Any]) -> dict[str, Any]:
        """Redact sensitive information from headers for logging."""
        if not headers:
            return {}

        safe_headers = headers.copy()
        sensitive_keys = ["authorization", "x-api-key", "jwt", "token"]

        for key in safe_headers:
            if key.lower() in sensitive_keys:
                safe_headers[key] = "[REDACTED]"

        return safe_headers

    def get(self, api_url: str, path: str, params: dict | None = None, timeout: float | None = None) -> dict:
        return self.request(
            url=f"{api_url}/{path}",
            http_method=HttpMethod.GET,
            params=params,
            headers=self.client.headers,
            timeout=timeout,
        )

    # post is always private, use either provided headers
    # or the client headers with JWT token
    def post(
        self,
        api_url: str,
        path: str,
        payload: dict[str, Any] | list[dict[str, Any]] | None = None,
        params: dict | None = None,
        headers: dict | None = None,
        timeout: float | None = None,
    ) -> dict:
        use_headers = headers if headers else self.client.headers
        return self.request(
            url=f"{api_url}/{path}",
            http_method=HttpMethod.POST,
            payload=payload,
            params=params,
            headers=use_headers,
            timeout=timeout,
        )

    def put(
        self,
        api_url: str,
        path: str,
        payload: dict[str, Any] | list[dict[str, Any]] | None = None,
        params: dict | None = None,
        headers: dict | None = None,
        timeout: float | None = None,
    ) -> dict:
        use_headers = headers if headers else self.client.headers
        return self.request(
            url=f"{api_url}/{path}",
            http_method=HttpMethod.PUT,
            payload=payload,
            params=params,
            headers=use_headers,
            timeout=timeout,
        )

    def delete(
        self,
        api_url: str,
        path: str,
        params: dict | None = None,
        payload: dict | None = None,
        timeout: float | None = None,
    ) -> dict:
        return self.request(
            url=f"{api_url}/{path}",
            http_method=HttpMethod.DELETE,
            params=params,
            payload=payload,
            headers=self.client.headers,
            timeout=timeout,
        )
