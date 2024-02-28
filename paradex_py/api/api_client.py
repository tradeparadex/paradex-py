from typing import Any, Dict, List, Optional, Union

from paradex_py.api.environment import Environment
from paradex_py.api.http_client import HttpClient, HttpMethod
from paradex_py.api.models import AuthSchema, SystemConfig, SystemConfigSchema


class ApiClient(HttpClient):
    env: Environment
    config: SystemConfig
    http_client: HttpClient
    authorization_header: Optional[str]

    def __init__(self, env: Environment):
        if env is None:
            raise ValueError("Paradex: Invalid environment")
        self.env = env
        self.http_client = HttpClient()

    def get(self, url: str, params: Optional[dict] = None) -> dict:
        return self.http_client.request(url=url, http_method=HttpMethod.GET, params=params)

    def post(
        self,
        url: str,
        payload: Optional[Union[Dict[str, Any], List[Dict[str, Any]]]] = None,
        params: Optional[dict] = None,
        headers: Optional[dict] = None,
    ) -> dict:
        return self.http_client.request(
            url=url,
            http_method=HttpMethod.POST,
            payload=payload,
            params=params,
            headers=headers,
        )

    def load_system_config(self) -> SystemConfig:
        api_url = f"https://api.{self.env}.paradex.trade/v1"
        ws_api_url = f"wss://ws.api.{self.env}.paradex.trade/v1"
        res = self.get(f"{api_url}/system/config")
        res.update({"api_url": api_url, "ws_api_url": ws_api_url})
        self.config = SystemConfigSchema().load(res)
        return self.config

    def onboarding(self, headers: dict, payload: dict):
        self.post(f"{self.config.api_url}/onboarding", headers=headers, payload=payload)

    def auth(self, headers: dict):
        res = self.post(f"{self.config.api_url}/auth", headers=headers)
        auth_data = AuthSchema().load(res)
        self.authorization_header = f"Bearer {auth_data.jwt_token}"
