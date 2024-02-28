from paradex_py.api.environment import Environment
from paradex_py.api.http_client import HttpClient
from paradex_py.api.models import (
    AccountSummarySchema,
    AuthSchema,
    SystemConfig,
    SystemConfigSchema,
)


class ParadexApiClient(HttpClient):
    env: Environment
    config: SystemConfig

    def __init__(self, env: Environment):
        if env is None:
            raise ValueError("Paradex: Invalid environment")
        self.env = env
        super().__init__()

    async def __aexit__(self):
        await self.client.close()

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
        data = AuthSchema().load(res)
        self.client.headers.update({"Authorization": f"Bearer {data.jwt_token}"})

    def get_account_summary(self):
        res = self.get(f"{self.config.api_url}/account")
        return AccountSummarySchema().load(res)
