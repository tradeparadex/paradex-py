from enum import Enum
from typing import Any

import httpx

from paradex_py.api.models import ApiErrorSchema


class HttpMethod(Enum):
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    DELETE = "DELETE"


class HttpClient:
    def __init__(self, http_client: httpx.Client | None = None):
        """Initialize HTTP client with optional injection.

        Args:
            http_client: Optional httpx.Client instance for injection.
                        If None, creates a default client.
        """
        if http_client is not None:
            self.client = http_client
        else:
            self.client = httpx.Client()

        # Only set default headers if they're not already set
        if "Content-Type" not in self.client.headers:
            self.client.headers.update({"Content-Type": "application/json"})

    def request(
        self,
        url: str,
        http_method: HttpMethod,
        params: dict | None = None,
        payload: dict[str, Any] | list[dict[str, Any]] | None = None,
        headers: Any | None = None,
    ):
        res = self.client.request(
            method=http_method.value,
            url=url,
            params=params,
            json=payload,
            headers=headers,
        )
        if res.status_code == 429:
            raise Exception("Rate limit exceeded")
        if res.status_code >= 300:
            error = ApiErrorSchema().loads(res.text)
            raise Exception(error)
        try:
            return res.json()
        except ValueError:
            print(f"HttpClient: No response request({url}, {http_method.value})")

    def get(self, api_url: str, path: str, params: dict | None = None) -> dict:
        return self.request(
            url=f"{api_url}/{path}",
            http_method=HttpMethod.GET,
            params=params,
            headers=self.client.headers,
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
    ) -> dict:
        use_headers = headers if headers else self.client.headers
        return self.request(
            url=f"{api_url}/{path}",
            http_method=HttpMethod.POST,
            payload=payload,
            params=params,
            headers=use_headers,
        )

    def put(
        self,
        api_url: str,
        path: str,
        payload: dict[str, Any] | list[dict[str, Any]] | None = None,
        params: dict | None = None,
        headers: dict | None = None,
    ) -> dict:
        use_headers = headers if headers else self.client.headers
        return self.request(
            url=f"{api_url}/{path}",
            http_method=HttpMethod.PUT,
            payload=payload,
            params=params,
            headers=use_headers,
        )

    def delete(
        self,
        api_url: str,
        path: str,
        params: dict | None = None,
        payload: dict | None = None,
    ) -> dict:
        return self.request(
            url=f"{api_url}/{path}",
            http_method=HttpMethod.DELETE,
            params=params,
            payload=payload,
            headers=self.client.headers,
        )
