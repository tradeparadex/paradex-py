"""EvmAccount sends its JWT on full node RPC calls, and resends a call without
it when the full node refuses the token."""

from unittest.mock import AsyncMock, Mock, patch

import pytest
from eth_account import Account as EthAccount
from starknet_py.net.http_client import HttpMethod

from paradex_py.account import evm_account
from paradex_py.account.evm_account import RPC_JWT_RETRY_AFTER_SECONDS, EvmAccount
from tests.mocks.api_client import MockApiClient

# Throwaway EVM key (anvil dev key #2) — test fixture only.
EVM_KEY = "0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d"
EVM_ADDR = EthAccount.from_key(EVM_KEY).address
L2_ADDR = "0x51f2207a15e14b0a7b21e1b2ec3541f19380429f4269e8c65548170c4f7f2f8"
TOKEN = "header.payload.sig"  # noqa: S105 — placeholder JWT, not a secret
BEARER = f"Bearer {TOKEN}"

NONCE = {"jsonrpc": "2.0", "id": 0, "result": "0x5"}


def _refused(message: str) -> dict:
    return {"jsonrpc": "2.0", "id": 0, "error": {"code": -32000, "message": message}}


# JWT auth for RPC off on the full node: every token is refused.
AUTH_OFF = _refused("invalid token usage")
# JWT auth on, account not deployed yet: the node finds no Eip191 owner.
UNDEPLOYED = _refused("account owner is not an Eip191 signer")


def _account(jwt: str | None = TOKEN) -> EvmAccount:
    account = EvmAccount(
        config=MockApiClient().fetch_system_config(),
        env="testnet",
        evm_address=EVM_ADDR,
        evm_private_key=EVM_KEY,
        l2_address=L2_ADDR,
    )
    if jwt is not None:
        account.set_jwt_token(jwt)
    return account


def _session(*bodies: object) -> AsyncMock:
    responses = []
    for body in bodies:
        response = Mock()
        response.json = AsyncMock(return_value=body)
        responses.append(response)
    session = AsyncMock()
    session.request.side_effect = responses
    return session


async def _call(account: EvmAccount, session: AsyncMock) -> object:
    client = account.starknet.client._client
    with patch.object(client, "handle_request_error", new_callable=AsyncMock):
        return await client._make_request(
            session=session,
            address="https://rpc.example.com",
            http_method=HttpMethod.POST,
            params={},
            payload={"jsonrpc": "2.0", "id": 0, "method": "starknet_getNonce", "params": []},
        )


def _auth_headers(session: AsyncMock) -> list[str | None]:
    return [call.kwargs["headers"].get("Authorization") for call in session.request.call_args_list]


@pytest.mark.asyncio
async def test_jwt_auth_off_resends_without_the_jwt():
    account = _account()
    session = _session(AUTH_OFF, NONCE)

    assert await _call(account, session) == NONCE
    assert _auth_headers(session) == [BEARER, None]


@pytest.mark.asyncio
async def test_jwt_auth_on_deployed_owner_keeps_the_jwt():
    account = _account()
    session = _session(NONCE, NONCE)

    assert await _call(account, session) == NONCE
    assert await _call(account, session) == NONCE
    assert _auth_headers(session) == [BEARER, BEARER]


@pytest.mark.asyncio
async def test_jwt_auth_on_undeployed_account_resends_without_the_jwt():
    account = _account()
    session = _session(UNDEPLOYED, NONCE)

    assert await _call(account, session) == NONCE
    assert _auth_headers(session) == [BEARER, None]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "message",
    [
        "session tokens cannot read owner data",
        "token pubkey is not the account owner",
        "token pubkey is not a secp256k1 key",
    ],
)
async def test_a_token_that_is_not_the_owners_resends_without_it(message):
    account = _account()
    session = _session(_refused(message), NONCE)

    assert await _call(account, session) == NONCE
    assert _auth_headers(session) == [BEARER, None]


@pytest.mark.asyncio
async def test_skips_the_jwt_after_a_refusal_then_tries_it_again():
    account = _account()
    session = _session(UNDEPLOYED, NONCE, NONCE, NONCE)

    with patch.object(evm_account.time, "monotonic", return_value=1000.0):
        await _call(account, session)
        await _call(account, session)
    with patch.object(evm_account.time, "monotonic", return_value=1000.0 + RPC_JWT_RETRY_AFTER_SECONDS):
        assert await _call(account, session) == NONCE

    assert _auth_headers(session) == [BEARER, None, None, BEARER]


@pytest.mark.asyncio
async def test_a_refreshed_jwt_is_sent_again_and_accepted():
    account = _account()
    session = _session(UNDEPLOYED, NONCE, NONCE, NONCE)

    with patch.object(evm_account.time, "monotonic", return_value=1000.0):
        assert await _call(account, session) == NONCE
        await _call(account, session)
        account.set_jwt_token("header.payload.refreshed")
        assert await _call(account, session) == NONCE

    assert _auth_headers(session) == [BEARER, None, None, "Bearer header.payload.refreshed"]


@pytest.mark.asyncio
async def test_setting_the_same_jwt_keeps_the_skip():
    account = _account()
    session = _session(UNDEPLOYED, NONCE, NONCE)

    with patch.object(evm_account.time, "monotonic", return_value=1000.0):
        await _call(account, session)
        account.set_jwt_token(TOKEN)
        await _call(account, session)

    assert _auth_headers(session) == [BEARER, None, None]


@pytest.mark.asyncio
async def test_the_skip_is_per_account():
    refused, other = _account(), _account()
    session = _session(AUTH_OFF, NONCE, NONCE)

    await _call(refused, session)
    await _call(other, session)

    assert _auth_headers(session) == [BEARER, None, BEARER]


@pytest.mark.asyncio
async def test_resends_a_batch_with_a_refused_entry():
    account = _account()
    session = _session([AUTH_OFF, AUTH_OFF], [NONCE, NONCE])

    assert await _call(account, session) == [NONCE, NONCE]
    assert _auth_headers(session) == [BEARER, None]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error",
    [
        {"code": -32000, "message": "rate limit exceeded"},
        {"code": -32000, "message": "owner lookup unavailable"},
        {"code": 20, "message": "Contract not found"},
    ],
)
async def test_other_errors_are_returned_without_a_retry(error):
    account = _account()
    body = {"jsonrpc": "2.0", "id": 0, "error": error}
    session = _session(body, NONCE)

    assert await _call(account, session) == body
    assert await _call(account, session) == NONCE
    assert _auth_headers(session) == [BEARER, BEARER]


@pytest.mark.asyncio
async def test_without_a_jwt_a_refusal_is_not_retried():
    account = _account(jwt=None)
    session = _session(AUTH_OFF)

    assert await _call(account, session) == AUTH_OFF
    assert _auth_headers(session) == [None]
