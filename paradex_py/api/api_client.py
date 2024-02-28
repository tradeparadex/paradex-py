import logging
import time
import traceback
from typing import Any, Dict, List, Optional, Union

from paradex_py.account.account import ParadexAccount
from paradex_py.api.environment import PROD, TESTNET, Environment
from paradex_py.api.http_client import HttpClient, HttpMethod
from paradex_py.api.models import SystemConfig, SystemConfigSchema


class ParadexApiClient:
    env: Environment
    config: SystemConfig
    http_client: HttpClient

    def __init__(
        self,
        env: Environment,
        l1_private_key: Optional[str] = None,
    ):
        if env not in [PROD, TESTNET]:
            raise ValueError("Paradex: Invalid environment")
        self.env = env
        self.http_client = HttpClient()
        self.jwt: str = ""
        self.account: Optional[ParadexAccount] = None
        self.l1_private_key: Optional[str] = l1_private_key

    async def __aenter__(self):
        await self.init()
        return self

    async def __aexit__(self, exc_type, exc_value, tb):
        await self.http_client.session.close()

    async def init(self) -> None:
        self.config = await self.load_system_config()
        if self.l1_private_key:
            self.account = ParadexAccount(self.config, self.l1_private_key)
            self.jwt = await self.get_jwt_token()
            logging.info(f"ParadexApiClient: jwt:'{self.jwt}' account:'{self.account.address}'")

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
        config = SystemConfigSchema().load(res)
        return config

    async def get_jwt_token(
        self,
    ) -> str:
        FN = "get_jwt_token"
        logging.info(f"{FN} START")
        token: str = ""
        now = int(time.time())
        expiry = now + 24 * 60 * 60
        signature = self.account.auth_signature(now, expiry)

        headers: dict = {
            "PARADEX-STARKNET-ACCOUNT": str(self.account.address),
            "PARADEX-STARKNET-SIGNATURE": signature,
            "PARADEX-TIMESTAMP": str(now),
            "PARADEX-SIGNATURE-EXPIRATION": str(expiry),
        }
        path = f"{self.config.api_url}/auth"
        logging.info(f"{FN} path:{path} headers:{headers}")

        try:
            response: dict = await self.http_client.request(
                url=path,
                http_method=HttpMethod.POST,
                headers=headers,
            )
            if response and isinstance(response, dict) and "jwt_token" in response:
                token = response["jwt_token"]
            else:
                logging.error(f"{FN} invalid response:{response}")
        except Exception as err:
            logging.error(f"{FN} {path} Error:{err} {traceback.format_exc()}")
        return token

    def get_rest_headers(self) -> dict:
        """
        Creates the required headers for PRIVATE
        Paradex RESToverHTTP requests.
        """
        return {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.jwt}",
        }

    async def private_get(
        self,
        path_ext: str,
        params: dict,
    ) -> Optional[dict]:
        FN = f"private_get {path_ext} params:{params}"
        path: str = f"{self.config.api_url}/{path_ext}"
        logging.info(f"{FN} path:{path} START")
        headers: dict = self.get_rest_headers()
        response = None
        try:
            response = await self.http_client.request(
                path,
                http_method=HttpMethod.GET,
                headers=headers,
                params=params,
            )
        except Exception as err:
            logging.error(f"{FN} path:{path} exception:{err} {traceback.format_exc()}")
        return response

    async def private_get_balances(self) -> List[Dict[str, Any]]:
        """
        Returns None if failed to get balances
        Otherwise returns a list of token balances
        """
        result = None
        FN = "private_get_balances"
        logging.info(f"{FN} START")
        response = await self.private_get("balance", params={})
        if response and "results" in response:
            result = response["results"]
        else:
            logging.warning(f"{FN} response:{response} Failed to get balances")
        return result

    def public_get(
        self,
        path_ext: str,
        params: dict,
    ) -> list[dict]:
        """
        Paradex RESToverHTTP endpoint.
        [GET] /markets
        """
        FN = f"public_get {path_ext} params:{params}"
        path: str = f"{self.config.api_url}/{path_ext}"
        logging.info(f"{FN} path:{path} START")
        response = None
        try:
            response = await self.http_client.request(
                path,
                http_method=HttpMethod.GET,
                params=params,
            )
        except Exception as err:
            logging.error(f"{FN} path:{path} exception:{err}")
        return response
