from unittest.mock import AsyncMock, patch

import pytest
from websockets import State

from paradex_py import Paradex, ParadexAccount
from paradex_py.api.ws_client import ParadexWebsocketClient
from paradex_py.environment import TESTNET

MOCK_L1_PRIVATE_KEY = "0x0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
MOCK_L1_ADDRESS = "0xabcdef0123456789abcdef0123456789abcdef01"


@pytest.fixture
def mock_paradex() -> Paradex:
    return Paradex(l1_address=MOCK_L1_ADDRESS, l1_private_key=MOCK_L1_PRIVATE_KEY, env=TESTNET)


@pytest.fixture
def ws_client(mock_paradex: Paradex) -> ParadexWebsocketClient:
    return mock_paradex.ws_client


@pytest.mark.asyncio
@patch("websockets.connect", new_callable=AsyncMock)
async def test_connect_authenticated(
    mock_connect: AsyncMock,
    ws_client: ParadexWebsocketClient,
    mock_paradex: Paradex,
) -> None:
    """Tests successful authenticated connection."""
    mock_ws_connection = AsyncMock()
    mock_ws_connection.state = State.OPEN
    mock_connect.return_value = mock_ws_connection

    mock_account: ParadexAccount = mock_paradex.account

    # Mock _send_auth_id to prevent actual sending during test
    with patch.object(ws_client, "_send_auth_id", new_callable=AsyncMock) as mock_send_auth:
        connected = await ws_client.connect()

        assert connected is True
        expected_headers = {"Authorization": f"Bearer {mock_account.jwt_token}"}
        mock_connect.assert_called_once_with(ws_client.api_url, additional_headers=expected_headers)

        mock_send_auth.assert_called_once_with(mock_ws_connection, mock_account.jwt_token)
        assert ws_client.ws.state == State.OPEN
