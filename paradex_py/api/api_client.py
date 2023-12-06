from typing import Any, Dict, List, Optional, Union

from paradex_py.api.environment import MAINNET, TESTNET, Environment
from paradex_py.api.http_client import HttpClient, HttpMethod
from paradex_py.api.models import SystemConfig, SystemConfigSchema


class ApiClient(HttpClient):
    env: Environment
    config: SystemConfig
    http_client: HttpClient

    def __init__(self, env: Environment):
        if env not in [MAINNET, TESTNET]:
            raise ValueError("Paradex: Invalid environment")
        self.env = env
        self.http_client = HttpClient()

    async def get(self, url: str, params: Optional[dict] = None) -> dict:
        return await self.http_client.request(url=url, http_method=HttpMethod.GET, params=params)

    async def post(
        self,
        url: str,
        payload: Union[Dict[str, Any], List[Dict[str, Any]]],
        params: Optional[dict] = None,
    ) -> dict:
        return await self.http_client.request(
            url=url,
            http_method=HttpMethod.POST,
            payload=payload,
            params=params,
        )

    async def load_system_config(self) -> SystemConfig:
        api_url = f"https://api.{self.env}.paradex.trade/v1"
        ws_api_url = f"wss://ws.api.{self.env}.paradex.trade/v1"
        res = await self.get(f"{api_url}/system/config")
        res.update({"api_url": api_url, "ws_api_url": ws_api_url})
        self.config = SystemConfigSchema().load(res)
        return self.config
