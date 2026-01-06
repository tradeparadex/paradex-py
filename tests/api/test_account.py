from starknet_py.common import int_from_hex

from paradex_py.account.account import ParadexAccount
from paradex_py.account.utils import typed_data_to_message_hash, unflatten_signature, verify_message_signature
from paradex_py.message.auth import build_auth_message
from paradex_py.message.onboarding import build_onboarding_message
from tests.mocks.api_client import MockApiClient

TEST_L1_ADDRESS = "0xd2c7314539dCe7752c8120af4eC2AA750Cf2035e"
TEST_L1_PRIVATE_KEY = int_from_hex("f8e4d1d772cdd44e5e77615ad11cc071c94e4c06dc21150d903f28e6aa6abdff")
TEST_L2_ADDRESS = int_from_hex("0x4183e117a90be234f2a34efb66dbae17b879b05d6581f72c729197c592fb366")
TEST_L2_PRIVATE_KEY = int_from_hex("0x713fd8c2c3bfb584601cd71b1012d26bf24497d313c9ad9d985cb8ac144096b")
TEST_L2_PUBLIC_KEY = int_from_hex("0x2957ff4b29c5300f007865cd80eaaeb28a81352b22d2fb216845285004cbcd8")


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

    assert account.l2_private_key == TEST_L2_PRIVATE_KEY
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

    assert account.l2_private_key == TEST_L2_PRIVATE_KEY
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
