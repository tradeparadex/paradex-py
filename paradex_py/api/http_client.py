from enum import Enum
from typing import Any, Dict, List, Optional, Union

import httpx

from paradex_py.api.models import ApiErrorSchema


class HttpMethod(Enum):
    GET = "GET"
    POST = "POST"
    DELETE = "DELETE"


class HttpClient:
    def __init__(self):
        self.client = httpx.Client()
        self.client.headers.update({"Content-Type": "application/json"})

    def request(
        self,
        url: str,
        http_method: HttpMethod,
        params: Optional[dict] = None,
        payload: Optional[Union[Dict[str, Any], List[Dict[str, Any]]]] = None,
        headers: Optional[Any] = None,
    ):
        res = self.client.request(
            method=http_method.value,
            url=url,
            params=params,
            json=payload,
            headers=headers,
        )
        if res.status_code >= 300:
            error = ApiErrorSchema().loads(res.text)
            raise Exception(error)
        try:
            return res.json()
        except ValueError:
            print(f"HttpClient: No response request({url}, {http_method.value})")

    def get(self, api_url: str, path: str, params: Optional[dict] = None) -> dict:
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
        payload: Optional[Union[Dict[str, Any], List[Dict[str, Any]]]] = None,
        params: Optional[dict] = None,
        headers: Optional[dict] = None,
    ) -> dict:
        use_headers = headers if headers else self.client.headers
        return self.request(
            url=f"{api_url}/{path}",
            http_method=HttpMethod.POST,
            payload=payload,
            params=params,
            headers=use_headers,
        )

    def delete(
        self,
        api_url: str,
        path: str,
        params: Optional[dict] = None,
    ) -> dict:
        return self.request(
            url=f"{api_url}/{path}",
            http_method=HttpMethod.DELETE,
            params=params,
            headers=self.client.headers,
        )
