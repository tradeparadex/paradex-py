from starknet_py.common import int_from_hex

from paradex_py.account.account import ParadexAccount
from paradex_py.account.utils import typed_data_to_message_hash, unflatten_signature, verify_message_signature
from paradex_py.message.auth import build_auth_message
from paradex_py.message.onboarding import build_onboarding_message
from tests.mocks.api_client import MockApiClient

TEST_L1_ADDRESS = "0xd2c7314539dCe7752c8120af4eC2AA750Cf2035e"
TEST_L1_PRIVATE_KEY = "0xf8e4d1d772cdd44e5e77615ad11cc071c94e4c06dc21150d903f28e6aa6abdff"
TEST_L2_ADDRESS = int_from_hex("0x129c135ed63df9353885e292be4426b8ed6122b13c6c0e1bb787288a1f5adfa")
TEST_L2_PRIVATE_KEY = "0x543b6cf6c91817a87174aaea4fb370ac1c694e864d7740d728f8344d53e815"
TEST_L2_PUBLIC_KEY = int_from_hex("0x2c144d2f2d4fc61b6f8967f3ba0012a87d90140bcfe5a3e92e8df83258c960f")


def test_account_l1_private_key():
    api_client = MockApiClient()
    config = api_client.fetch_system_config()

    account = ParadexAccount(
        config=config,
        l1_address=TEST_L1_ADDRESS,
        l1_private_key=TEST_L1_PRIVATE_KEY,
    )

    assert account.l2_address == TEST_L2_ADDRESS
    assert account.starknet.address == TEST_L2_ADDRESS

    assert account.l2_private_key == int_from_hex(TEST_L2_PRIVATE_KEY)
    assert account.l2_public_key == TEST_L2_PUBLIC_KEY


def test_account_l2_private_key():
    api_client = MockApiClient()
    config = api_client.fetch_system_config()

    account = ParadexAccount(
        config=config,
        l1_address=TEST_L1_ADDRESS,
        l2_private_key=TEST_L2_PRIVATE_KEY,
    )

    assert account.l2_address == TEST_L2_ADDRESS
    assert account.starknet.address == TEST_L2_ADDRESS

    assert account.l2_private_key == int_from_hex(TEST_L2_PRIVATE_KEY)
    assert account.l2_public_key == TEST_L2_PUBLIC_KEY


def test_account_onboarding_signature():
    api_client = MockApiClient()
    config = api_client.fetch_system_config()

    account = ParadexAccount(
        config=config,
        l1_address=TEST_L1_ADDRESS,
        l2_private_key=TEST_L2_PRIVATE_KEY,
    )

    sig = account.onboarding_signature()

    message = build_onboarding_message(account.l2_chain_id)
    is_signature_valid = verify_message_signature(
        typed_data_to_message_hash(message, account.l2_address),
        unflatten_signature(sig),
        account.l2_public_key,
    )
    assert is_signature_valid is True


def test_account_auth_signature():
    api_client = MockApiClient()
    config = api_client.fetch_system_config()

    account = ParadexAccount(
        config=config,
        l1_address=TEST_L1_ADDRESS,
        l2_private_key=TEST_L2_PRIVATE_KEY,
    )

    timestamp = 1706868900
    expiry = 1706955300
    sig = account.auth_signature(timestamp, expiry)

    message = build_auth_message(account.l2_chain_id, timestamp, expiry)
    is_signature_valid = verify_message_signature(
        typed_data_to_message_hash(message, account.l2_address),
        unflatten_signature(sig),
        account.l2_public_key,
    )
    assert is_signature_valid is True
