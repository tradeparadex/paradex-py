import logging
from typing import Any, Dict, List, Optional, Union

from paradex_py.api.environment import Environment
from paradex_py.api.http_client import HttpClient, HttpMethod
from paradex_py.api.models import (
    AuthSchema,
    SystemConfig,
    SystemConfigSchema,
)


class ParadexApiClient(HttpClient):
    env: Environment
    config: SystemConfig

    def __init__(self, env: Environment, logger: Optional[logging.Logger] = None):
        if env is None:
            raise ValueError("Paradex: Invalid environment")
        self.env = env
        self.logger = logger or logging.getLogger(__name__)
        super().__init__()

    async def __aexit__(self):
        await self.client.close()

    def load_system_config(self) -> SystemConfig:
        api_url = f"https://api.{self.env}.paradex.trade/v1"
        ws_api_url = f"wss://ws.api.{self.env}.paradex.trade/v1"
        res = self.request(
            url=f"{api_url}/system/config",
            http_method=HttpMethod.GET,
        )
        res.update({"api_url": api_url, "ws_api_url": ws_api_url})
        self.logger.info(f"ParadexApiClient: /system/config:{res}")
        self.config = SystemConfigSchema().load(res)
        self.logger.info(f"ParadexApiClient: SystemConfig:{self.config}")
        return self.config

    def onboarding(self, headers: dict, payload: dict):
        self.post(
            path="onboarding",
            headers=headers,
            payload=payload,
        )

    def auth(self, headers: dict):
        res = self.post(path="auth", headers=headers)
        data = AuthSchema().load(res)
        self.client.headers.update({"Authorization": f"Bearer {data.jwt_token}"})
        self.logger.info(f"ParadexApiClient: JWT:{data.jwt_token}")

    def get(self, path: str, params: Optional[dict] = None) -> dict:
        return self.request(
            url=f"{self.config.api_url}/{path}",
            http_method=HttpMethod.GET,
            params=params,
        )

    def private_get(self, path: str, params: Optional[dict] = None) -> dict:
        return self.request(
            url=f"{self.config.api_url}/{path}",
            http_method=HttpMethod.GET,
            params=params,
            headers=self.client.headers,
        )

    # post is always private, use either provided headers
    # or the client headers with JWT token
    def post(
        self,
        path: str,
        payload: Optional[Union[Dict[str, Any], List[Dict[str, Any]]]] = None,
        params: Optional[dict] = None,
        headers: Optional[dict] = None,
    ) -> dict:
        use_headers = headers if headers else self.client.headers
        return self.request(
            url=f"{self.config.api_url}/{path}",
            http_method=HttpMethod.POST,
            payload=payload,
            params=params,
            headers=use_headers,
        )
