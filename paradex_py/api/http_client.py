import logging
from enum import Enum
from typing import Any, Dict, List, Optional, Union

from aiohttp import ClientSession


class HttpMethod(Enum):
    GET = "GET"
    POST = "POST"
    DELETE = "DELETE"


class HttpClient:
    def __init__(self):
        self.session = ClientSession()

    async def request(
        self,
        url: str,
        http_method: HttpMethod,
        headers: Optional[Dict[str, str]] = None,
        params: Optional[dict] = None,
        payload: Optional[Union[Dict[str, Any], List[Dict[str, Any]]]] = None,
    ) -> dict:
        async with self.session.request(
            method=http_method.value,
            url=url,
            headers=headers,
            params=params,
            json=str(payload),
        ) as response:
            if response.status >= 300:
                # return ApiErrorSchema().loads(str(await response.json()))
                logging.error(f"Error: {response.status} {response.reason} {await response.json()}")
            return await response.json(content_type=None)
