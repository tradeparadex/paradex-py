from typing import Optional

from paradex_py.account.account import ParadexAccount
from paradex_py.api.api_client import ApiClient
from paradex_py.api.environment import Environment
from paradex_py.api.models import SystemConfig


class Paradex:
    account: ParadexAccount
    api_client: ApiClient
    config: SystemConfig
    env: Environment

    def __init__(
        self,
        env: Environment,
        l1_address: str,
        l1_private_key: Optional[str] = None,
        l2_private_key: Optional[str] = None,
    ):
        if env is None:
            raise ValueError("Paradex: Invalid environment")
        self.env = env

        # Load api client and system config
        self.api_client = ApiClient(env=env)
        self.config = self.api_client.load_system_config()

        # Initialize account if private key is provided
        if l2_private_key is not None or l1_private_key is not None:
            self.init_account(
                l1_address=l1_address,
                l1_private_key=l1_private_key,
                l2_private_key=l2_private_key,
            )

    def init_account(
        self,
        l1_address: str,
        l1_private_key: Optional[str] = None,
        l2_private_key: Optional[str] = None,
    ):
        self.account = ParadexAccount(
            config=self.config,
            l1_address=l1_address,
            l1_private_key=l1_private_key,
            l2_private_key=l2_private_key,
        )
        self.account_onboarding()
        self.account_auth()

    def account_onboarding(self):
        if self.account is None:
            raise ValueError("Paradex: Account not initialized")
        headers = self.account.onboarding_headers()
        payload = {"public_key": hex(self.account.l2_public_key)}
        self.api_client.onboarding(headers=headers, payload=payload)

    def account_auth(self):
        if self.account is None:
            raise ValueError("Paradex: Account not initialized")
        headers = self.account.auth_headers()
        self.api_client.auth(headers=headers)
