import pytest

from paradex_py.account.account import ParadexAccount
from paradex_py.api.api_client import ApiClient


@pytest.mark.asyncio
async def test_account():
    api_client = ApiClient(env="testnet")
    config = await api_client.load_system_config()

    eth_private_key = "f8e4d1d772cdd44e5e77615ad11cc071c94e4c06dc21150d903f28e6aa6abdff"
    account = ParadexAccount(config, eth_private_key)

    assert account.address == "0x129c135ed63df9353885e292be4426b8ed6122b13c6c0e1bb787288a1f5adfa"
    assert account.private_key == "0x543b6cf6c91817a87174aaea4fb370ac1c694e864d7740d728f8344d53e815"
    assert account.public_key == "0x2c144d2f2d4fc61b6f8967f3ba0012a87d90140bcfe5a3e92e8df83258c960f"
