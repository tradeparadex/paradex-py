import pytest
from starknet_py.common import int_from_hex

from paradex_py.account.account import ParadexAccount
from tests.mocks.api_client import MockApiClient


@pytest.mark.asyncio
async def test_account_l1_private_key():
    api_client = MockApiClient()
    config = await api_client.load_system_config()

    l1_private_key = int_from_hex("f8e4d1d772cdd44e5e77615ad11cc071c94e4c06dc21150d903f28e6aa6abdff")
    account_address = int_from_hex("0x129c135ed63df9353885e292be4426b8ed6122b13c6c0e1bb787288a1f5adfa")

    account = ParadexAccount(
        config=config,
        l1_private_key=l1_private_key,
    )

    assert account.address == account_address
    assert account.starknet.address == account_address

    assert account.private_key == int_from_hex("0x543b6cf6c91817a87174aaea4fb370ac1c694e864d7740d728f8344d53e815")
    assert account.public_key == int_from_hex("0x2c144d2f2d4fc61b6f8967f3ba0012a87d90140bcfe5a3e92e8df83258c960f")


@pytest.mark.asyncio
async def test_account_private_key():
    api_client = MockApiClient()
    config = await api_client.load_system_config()

    private_key = int_from_hex("0x543b6cf6c91817a87174aaea4fb370ac1c694e864d7740d728f8344d53e815")
    account_address = int_from_hex("0x129c135ed63df9353885e292be4426b8ed6122b13c6c0e1bb787288a1f5adfa")

    account = ParadexAccount(
        config=config,
        private_key=private_key,
    )

    assert account.address == account_address
    assert account.starknet.address == account_address

    assert account.private_key == private_key
    assert account.public_key == int_from_hex("0x2c144d2f2d4fc61b6f8967f3ba0012a87d90140bcfe5a3e92e8df83258c960f")


@pytest.mark.asyncio
async def test_account_onboarding_signature():
    api_client = MockApiClient()
    config = await api_client.load_system_config()

    private_key = int_from_hex("0x543b6cf6c91817a87174aaea4fb370ac1c694e864d7740d728f8344d53e815")
    account = ParadexAccount(
        config=config,
        private_key=private_key,
    )

    sig = account.onboarding_signature()
    assert (
        sig
        == '["1977703130303461992863803129734853218488251484396280000763960303272760326570","2304839285473787246223990153934072220920935645937627960319990072742739460432"]'
    )


@pytest.mark.asyncio
async def test_account_auth_signature():
    api_client = MockApiClient()
    config = await api_client.load_system_config()

    private_key = int_from_hex("0x543b6cf6c91817a87174aaea4fb370ac1c694e864d7740d728f8344d53e815")
    account = ParadexAccount(
        config=config,
        private_key=private_key,
    )

    timestamp = 1706868900
    expiry = 1706955300
    sig = account.auth_signature(timestamp, expiry)
    assert (
        sig
        == '["1977703130303461992863803129734853218488251484396280000763960303272760326570","2372141293109856884078160483922619445669904377109121850462217324440649578224"]'
    )
