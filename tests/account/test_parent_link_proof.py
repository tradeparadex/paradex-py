"""The parent link proof a new account's POST /v1/onboarding carries when an L1 key is available."""

import base64
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from eth_account import Account as EthAccount
from eth_account.messages import encode_defunct
from starknet_py.net.signer.key_pair import KeyPair

from paradex_py import Paradex
from paradex_py.account import utils as account_utils
from paradex_py.account.account import ParadexAccount
from paradex_py.api.api_client import ParadexApiClient
from paradex_py.environment import TESTNET
from tests.mocks import TEST_L2_PRIVATE_KEY
from tests.mocks.api_client import MOCK_ONBOARDING_STARKNET, MockApiClient

TEST_L1_PRIVATE_KEY = "0xf8e4d1d772cdd44e5e77615ad11cc071c94e4c06dc21150d903f28e6aa6abdff"
TEST_L1_ADDRESS = EthAccount.from_key(TEST_L1_PRIVATE_KEY).address
# A server-derived address with a leading zero nibble, so the statement must drop it.
SERVER_L2_ADDRESS = "0x0129c135ed63df9353885e292be4426b8ed6122b13c6c0e1bb787288a1f5adfa"
PARENT_HEADERS = {"PARADEX-PARENT-SIWE-MESSAGE", "PARADEX-PARENT-SIGNATURE"}
STARKNET_HEADERS = {"PARADEX-ETHEREUM-ACCOUNT", "PARADEX-STARKNET-ACCOUNT", "PARADEX-STARKNET-SIGNATURE"}


def _account(**kwargs) -> ParadexAccount:
    args: dict[str, Any] = {
        "config": MockApiClient().fetch_system_config(),
        "l1_address": TEST_L1_ADDRESS.lower(),
        "l1_private_key": TEST_L1_PRIVATE_KEY,
        "l2_address": SERVER_L2_ADDRESS,
        "is_onboarded": False,
        "env": TESTNET,
    }
    args.update(kwargs)
    return ParadexAccount(**args)


def _decoded_message(headers: dict) -> str:
    return base64.b64decode(headers["PARADEX-PARENT-SIWE-MESSAGE"], validate=True).decode()


def test_new_account_onboarding_carries_a_proof_signed_by_the_l1_key():
    account = _account()

    headers = account.onboarding_headers()

    assert set(headers) == STARKNET_HEADERS | PARENT_HEADERS
    message = _decoded_message(headers)
    lines = message.split("\n")
    assert lines[0] == "app.testnet.paradex.trade wants you to sign in with your Ethereum account:"
    assert lines[1] == TEST_L1_ADDRESS  # EIP-55, though the account was given lowercase
    assert lines[3] == (
        "Link this wallet as the parent of Paradex account"
        " 0x129c135ed63df9353885e292be4426b8ed6122b13c6c0e1bb787288a1f5adfa on PRIVATE_SN_POTC_SEPOLIA"
    )
    assert "URI: https://app.testnet.paradex.trade" in lines
    assert "Chain ID: 11155111" in lines
    assert any(line.startswith("Expiration Time: ") for line in lines)

    signature = headers["PARADEX-PARENT-SIGNATURE"]
    assert signature.startswith("0x")
    assert len(signature) == 2 + 65 * 2
    signer = EthAccount.recover_message(encode_defunct(text=message), signature=signature)
    assert signer == TEST_L1_ADDRESS


def test_account_of_unknown_state_carries_a_proof():
    """With no GET /onboarding answer, onboarding runs only after auth said NOT_ONBOARDED."""
    headers = _account(is_onboarded=None).onboarding_headers()

    assert set(headers) >= PARENT_HEADERS


def test_l2_key_only_onboarding_is_unchanged():
    account = _account(l1_private_key=None, l2_private_key=TEST_L2_PRIVATE_KEY)

    with patch("paradex_py.account.account.sign_eip191_message") as sign:
        headers = account.onboarding_headers()

    assert set(headers) == STARKNET_HEADERS
    sign.assert_not_called()


def test_existing_account_onboarding_is_unchanged():
    account = _account(is_onboarded=True)

    with patch("paradex_py.account.account.sign_eip191_message") as sign:
        headers = account.onboarding_headers()

    assert set(headers) == STARKNET_HEADERS
    sign.assert_not_called()


def test_no_proof_without_an_environment():
    """A directly constructed account names no SIWE domain, so it sends what it sent before."""
    headers = _account(env=None).onboarding_headers()

    assert set(headers) == STARKNET_HEADERS


def test_ledger_signs_the_proof_once():
    account = _account(l1_private_key=None, l2_private_key=TEST_L2_PRIVATE_KEY)
    account.l1_private_key_from_ledger = True

    with patch("paradex_py.account.account.sign_eip191_message_ledger", return_value="0xledger") as ledger:
        headers = account.onboarding_headers()

    ledger.assert_called_once()
    message, address = ledger.call_args.args
    assert address == TEST_L1_ADDRESS.lower()
    assert message == _decoded_message(headers)
    assert headers["PARADEX-PARENT-SIGNATURE"] == "0xledger"


def test_ledger_personal_sign_uses_the_wallet_path():
    found = MagicMock(path="44'/60'/0'/0/3")
    with (
        patch.object(account_utils, "init_dongle", return_value="dongle"),
        patch.object(account_utils, "find_account", return_value=found) as find,
        patch.object(account_utils, "sign_message", return_value=MagicMock(signature="0xsig")) as sign,
    ):
        assert account_utils.sign_eip191_message_ledger("hello", TEST_L1_ADDRESS) == "0xsig"

    find.assert_called_once_with(TEST_L1_ADDRESS, "dongle", count=10)
    sign.assert_called_once_with("hello", sender_path="44'/60'/0'/0/3", dongle="dongle")


def test_ledger_without_the_wallet_raises():
    with (
        patch.object(account_utils, "init_dongle", return_value="dongle"),
        patch.object(account_utils, "find_account", return_value=None),
        pytest.raises(ValueError, match="not found on Ledger"),
    ):
        account_utils.sign_eip191_message_ledger("hello", TEST_L1_ADDRESS)


# ---------------------------------------------------------------------------
# POST /v1/onboarding through the API client
# ---------------------------------------------------------------------------


def _client(account) -> ParadexApiClient:
    with patch.object(ParadexApiClient, "fetch_system_config", return_value=MockApiClient().fetch_system_config()):
        client = ParadexApiClient(env=TESTNET)
    client.account = account
    return client


def test_onboarding_signs_once_and_a_second_call_sends_no_proof():
    account = _account()
    client = _client(account)

    with (
        patch.object(client, "post") as post,
        patch("paradex_py.account.account.sign_eip191_message", wraps=account_utils.sign_eip191_message) as sign,
    ):
        client.onboarding()
        first = post.call_args.kwargs["headers"]
        client.onboarding()
        second = post.call_args.kwargs["headers"]

    assert sign.call_count == 1
    assert set(first) >= PARENT_HEADERS
    assert set(second) == STARKNET_HEADERS
    assert account.is_onboarded is True


def test_failed_onboarding_leaves_the_account_new():
    account = _account()
    client = _client(account)

    with patch.object(client, "post", side_effect=ValueError("boom")), pytest.raises(ValueError):
        client.onboarding()

    assert account.is_onboarded is False


# ---------------------------------------------------------------------------
# Paradex.init_account hands the L1 credentials to new accounts only
# ---------------------------------------------------------------------------


def _paradex(exists: bool | None) -> Paradex:
    paradex = Paradex.__new__(Paradex)
    paradex.env = TESTNET
    paradex.logger = MagicMock()
    response = dict(MOCK_ONBOARDING_STARKNET, address=SERVER_L2_ADDRESS)
    if exists is None:
        paradex.server_derive_address = False
    else:
        paradex.server_derive_address = True
        response["exists"] = exists
    paradex.api_client = MockApiClient(onboarding_response=response)
    paradex.ws_client = MagicMock()
    paradex.ws_direct_client = MagicMock()
    paradex.config = paradex.api_client.fetch_system_config()
    paradex.account = None
    return paradex


def _paradex_with_auto_auth(exists: bool | None) -> tuple[Paradex, list[dict]]:
    """A Paradex whose auto_auth init_account records the onboarding headers it would send."""
    paradex = _paradex(exists)
    paradex.api_client.auto_auth = True
    sent: list[dict] = []
    paradex.api_client.init_account = lambda account: sent.append(account.onboarding_headers())
    return paradex, sent


@pytest.mark.parametrize("exists", [False, None])
def test_init_account_signs_a_proof_then_drops_the_l1_key_with_auto_auth(exists):
    paradex, sent = _paradex_with_auto_auth(exists)

    paradex.init_account(l1_address=TEST_L1_ADDRESS, l1_private_key=TEST_L1_PRIVATE_KEY)

    assert paradex.account is not None
    assert paradex.account.env == TESTNET
    assert set(sent[0]) >= PARENT_HEADERS
    assert paradex.account.l1_private_key is None
    assert paradex.account.l1_private_key_from_ledger is False


def test_init_account_drops_the_l1_key_when_auto_auth_onboarding_fails():
    paradex = _paradex(exists=False)
    paradex.api_client.auto_auth = True
    paradex.api_client.init_account = MagicMock(side_effect=ValueError("onboarding failed"))

    with pytest.raises(ValueError, match="onboarding failed"):
        paradex.init_account(l1_address=TEST_L1_ADDRESS, l1_private_key=TEST_L1_PRIVATE_KEY)

    assert paradex.account is not None
    assert paradex.account.l1_private_key is None


@pytest.mark.parametrize("exists", [False, None])
def test_init_account_keeps_no_l1_key_without_auto_auth(exists):
    paradex = _paradex(exists)

    paradex.init_account(l1_address=TEST_L1_ADDRESS, l1_private_key=TEST_L1_PRIVATE_KEY)

    assert paradex.account is not None
    assert paradex.account.l1_private_key is None
    assert set(paradex.account.onboarding_headers()) == STARKNET_HEADERS


def test_init_account_sends_no_proof_for_an_existing_account():
    paradex, sent = _paradex_with_auto_auth(exists=True)

    paradex.init_account(l1_address=TEST_L1_ADDRESS, l1_private_key=TEST_L1_PRIVATE_KEY)

    assert paradex.account is not None
    assert paradex.account.l1_private_key is None
    assert set(sent[0]) == STARKNET_HEADERS


def test_init_account_with_an_l2_key_sends_no_proof():
    paradex, sent = _paradex_with_auto_auth(exists=False)

    paradex.init_account(l1_address=TEST_L1_ADDRESS, l2_private_key=TEST_L2_PRIVATE_KEY)

    assert paradex.account is not None
    assert set(sent[0]) == STARKNET_HEADERS


def test_init_account_with_a_ledger_asks_it_once_for_the_l2_key():
    paradex, _ = _paradex_with_auto_auth(exists=False)
    ledger_flags: list[bool] = []
    paradex.api_client.init_account = lambda account: ledger_flags.append(account.l1_private_key_from_ledger)
    key_pair = KeyPair.from_private_key(int(TEST_L2_PRIVATE_KEY, 16))

    with (
        patch("paradex_py.paradex.resolve_l2_keypair", return_value=key_pair) as resolve,
        patch("paradex_py.account.utils.derive_stark_key_from_ledger") as ledger_derive,
    ):
        paradex.init_account(l1_address=TEST_L1_ADDRESS, l1_private_key_from_ledger=True)

    resolve.assert_called_once()
    ledger_derive.assert_not_called()
    assert ledger_flags == [True]
    assert paradex.account is not None
    assert paradex.account.l1_private_key is None
    assert paradex.account.l1_private_key_from_ledger is False
