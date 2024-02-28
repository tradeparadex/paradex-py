from enum import Enum
from typing import Any, Dict, List, Optional, Union

import httpx

from paradex_py.api.models import ApiErrorSchema


class HttpMethod(Enum):
    GET = "GET"
    POST = "POST"


class HttpClient:
    client: httpx.Client

    def __init__(self):
        self.client = httpx.Client()
        self.client.headers.update({"Content-Type": "application/json"})

    def request(
        self,
        url: str,
        http_method: HttpMethod,
        params: Optional[dict] = None,
        payload: Optional[Union[Dict[str, Any], List[Dict[str, Any]]]] = None,
        headers: Optional[dict] = None,
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
            print("Paradex: No response")

    def get(self, url: str, params: Optional[dict] = None) -> dict:
        return self.request(url=url, http_method=HttpMethod.GET, params=params)

    def post(
        self,
        url: str,
        payload: Optional[Union[Dict[str, Any], List[Dict[str, Any]]]] = None,
        params: Optional[dict] = None,
        headers: Optional[dict] = None,
    ) -> dict:
        return self.request(
            url=url,
            http_method=HttpMethod.POST,
            payload=payload,
            params=params,
            headers=headers,
        )
