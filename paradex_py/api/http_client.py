from enum import Enum
from typing import Any, Dict, List, Optional, Union

import httpx

from paradex_py.api.models import ApiErrorSchema


class HttpMethod(Enum):
    GET = "GET"
    POST = "POST"


class HttpClient:
    def __init__(self):
        self.session = httpx.Client()
        self.session.headers.update({"Content-Type": "application/json"})

    def request(
        self,
        url: str,
        http_method: HttpMethod,
        params: Optional[dict] = None,
        payload: Optional[Union[Dict[str, Any], List[Dict[str, Any]]]] = None,
        headers: Optional[dict] = None,
    ):
        res = self.session.request(
            method=http_method.value,
            url=url,
            params=params,
            json=payload,
            headers=headers,
        )
        if res.status_code >= 300:
            return ApiErrorSchema().loads(res.json())
        return res.json()
