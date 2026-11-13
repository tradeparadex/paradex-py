"""EvmAccount sends its JWT on full node RPC calls, and falls back to calls
without it when the full node does not accept the token for RPC."""

from unittest.mock import AsyncMock, Mock, patch

import pytest
from eth_account import Account as EthAccount
from starknet_py.net.http_client import HttpMethod

from paradex_py.account.evm_account import EvmAccount
from tests.mocks.api_client import MockApiClient

# Throwaway EVM key (anvil dev key #2) — test fixture only.
EVM_KEY = "0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d"
EVM_ADDR = EthAccount.from_key(EVM_KEY).address
L2_ADDR = "0x51f2207a15e14b0a7b21e1b2ec3541f19380429f4269e8c65548170c4f7f2f8"
TOKEN = "header.payload.sig"  # noqa: S105 — placeholder JWT, not a secret

NONCE = {"jsonrpc": "2.0", "id": 0, "result": "0x5"}
REFUSED = {"jsonrpc": "2.0", "id": 0, "error": {"code": -32000, "message": "invalid token usage"}}


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
async def test_sends_the_jwt_when_the_full_node_accepts_it():
    account = _account()
    session = _session(NONCE, NONCE)

    assert await _call(account, session) == NONCE
    assert await _call(account, session) == NONCE

    assert _auth_headers(session) == [f"Bearer {TOKEN}", f"Bearer {TOKEN}"]


@pytest.mark.asyncio
async def test_resends_without_the_jwt_when_the_full_node_refuses_it():
    account = _account()
    session = _session(REFUSED, NONCE)

    assert await _call(account, session) == NONCE

    assert _auth_headers(session) == [f"Bearer {TOKEN}", None]


@pytest.mark.asyncio
async def test_sends_no_jwt_after_a_refusal():
    account = _account()
    session = _session(REFUSED, NONCE, NONCE)

    await _call(account, session)
    assert await _call(account, session) == NONCE

    assert _auth_headers(session) == [f"Bearer {TOKEN}", None, None]


@pytest.mark.asyncio
async def test_a_refreshed_jwt_is_not_sent_after_a_refusal():
    account = _account()
    session = _session(REFUSED, NONCE, NONCE)

    await _call(account, session)
    account.set_jwt_token("header.payload.other")
    await _call(account, session)

    assert _auth_headers(session)[2] is None


@pytest.mark.asyncio
async def test_resends_a_batch_with_a_refused_entry():
    account = _account()
    session = _session([REFUSED, REFUSED], [NONCE, NONCE])

    assert await _call(account, session) == [NONCE, NONCE]
    assert _auth_headers(session) == [f"Bearer {TOKEN}", None]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error",
    [
        {"code": -32000, "message": "rate limit exceeded"},
        {"code": -32000, "message": "token pubkey is not the account owner"},
        {"code": 20, "message": "Contract not found"},
    ],
)
async def test_other_errors_are_returned_without_a_retry(error):
    account = _account()
    body = {"jsonrpc": "2.0", "id": 0, "error": error}
    session = _session(body, NONCE)

    assert await _call(account, session) == body
    assert await _call(account, session) == NONCE

    assert _auth_headers(session) == [f"Bearer {TOKEN}", f"Bearer {TOKEN}"]


@pytest.mark.asyncio
async def test_without_a_jwt_a_refusal_is_not_retried():
    account = _account(jwt=None)
    session = _session(REFUSED)

    assert await _call(account, session) == REFUSED
    assert _auth_headers(session) == [None]
