from enum import Enum
from typing import Any, Dict, List, Optional, Union

from aiohttp import ClientSession

from paradex_py.api.models import ApiErrorSchema


class HttpMethod(Enum):
    GET = "GET"
    POST = "POST"


class HttpClient:
    def __init__(self):
        self.session = ClientSession()

    async def request(
        self,
        url: str,
        http_method: HttpMethod,
        params: Optional[dict] = None,
        payload: Optional[Union[Dict[str, Any], List[Dict[str, Any]]]] = None,
    ):
        async with self.session.request(method=http_method.value, url=url, params=params, json=payload) as request:
            if request.status >= 300:
                return ApiErrorSchema().loads(await request.json())
            return await request.json(content_type=None)
