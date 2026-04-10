"""Tests for AuthLevel, ParadexL2, ParadexSubkey, ParadexApiKey, ParadexEvm, and on_token_expired."""

import base64
import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from paradex_py import AuthLevel, ParadexApiKey, ParadexEvm, ParadexL2, ParadexSubkey
from paradex_py.api.api_client import ParadexApiClient, _jwt_exp
from paradex_py.environment import TESTNET

MOCK_SYSTEM_CONFIG = MagicMock()

L2_KEY = "0x1234567890abcdef"
L2_ADDR = "0xdeadbeef"
API_KEY = "test-api-key-token"
EVM_ADDR = "0x846359e7bffc0AA5cB98767D94a874ec90f3944e"
EVM_KEY = "0x" + "a" * 64


def _make_jwt(exp: float) -> str:
    """Build a minimal but structurally valid JWT with the given exp claim."""
    header = base64.urlsafe_b64encode(b'{"alg":"HS256"}').rstrip(b"=").decode()
    payload = base64.urlsafe_b64encode(json.dumps({"exp": exp}).encode()).rstrip(b"=").decode()
    return f"{header}.{payload}.fakesig"


# ---------------------------------------------------------------------------
# AuthLevel
# ---------------------------------------------------------------------------


class TestAuthLevel:
    def test_ordering(self):
        assert AuthLevel.UNAUTHENTICATED < AuthLevel.AUTHENTICATED
        assert AuthLevel.AUTHENTICATED < AuthLevel.TRADING
        assert AuthLevel.TRADING < AuthLevel.FULL

    def test_gte_comparisons(self):
        assert AuthLevel.FULL >= AuthLevel.TRADING
        assert AuthLevel.FULL >= AuthLevel.AUTHENTICATED
        assert AuthLevel.FULL >= AuthLevel.UNAUTHENTICATED
        assert AuthLevel.TRADING >= AuthLevel.TRADING
        assert AuthLevel.TRADING >= AuthLevel.AUTHENTICATED
        assert not (AuthLevel.TRADING >= AuthLevel.FULL)
        assert not (AuthLevel.AUTHENTICATED >= AuthLevel.TRADING)

    def test_values(self):
        assert AuthLevel.UNAUTHENTICATED == 0
        assert AuthLevel.AUTHENTICATED == 1
        assert AuthLevel.TRADING == 2
        assert AuthLevel.FULL == 3


# ---------------------------------------------------------------------------
# ParadexL2 — full account key
# ---------------------------------------------------------------------------


class TestParadexL2:
    @patch("paradex_py.paradex_l2.SubkeyAccount")
    @patch("paradex_py.paradex_l2.ParadexWebsocketClient")
    @patch("paradex_py.paradex_l2.ParadexApiClient")
    def test_successful_init(self, MockApiClient, MockWsClient, MockSubkeyAccount):
        mock_api = MockApiClient.return_value
        mock_api.fetch_system_config.return_value = MOCK_SYSTEM_CONFIG

        p = ParadexL2(env=TESTNET, l2_private_key=L2_KEY, l2_address=L2_ADDR)

        MockApiClient.assert_called_once_with(env=TESTNET, logger=None)
        mock_api.fetch_system_config.assert_called_once()
        MockSubkeyAccount.assert_called_once_with(config=MOCK_SYSTEM_CONFIG, l2_private_key=L2_KEY, l2_address=L2_ADDR)
        mock_api.init_account.assert_called_once_with(MockSubkeyAccount.return_value)
        MockWsClient.return_value.init_account.assert_called_once_with(MockSubkeyAccount.return_value)
        assert p.config is MOCK_SYSTEM_CONFIG

    @patch("paradex_py.paradex_l2.SubkeyAccount")
    @patch("paradex_py.paradex_l2.ParadexWebsocketClient")
    @patch("paradex_py.paradex_l2.ParadexApiClient")
    def test_ws_timeout_forwarded(self, MockApiClient, MockWsClient, MockSubkeyAccount):
        MockApiClient.return_value.fetch_system_config.return_value = MOCK_SYSTEM_CONFIG
        ParadexL2(env=TESTNET, l2_private_key=L2_KEY, l2_address=L2_ADDR, ws_timeout=42)
        MockWsClient.assert_called_once_with(
            env=TESTNET, logger=None, ws_timeout=42, api_client=MockApiClient.return_value, sbe_enabled=False
        )

    @patch("paradex_py.paradex_l2.SubkeyAccount")
    @patch("paradex_py.paradex_l2.ParadexWebsocketClient")
    @patch("paradex_py.paradex_l2.ParadexApiClient")
    def test_ws_enabled_false_skips_ws_client(self, MockApiClient, MockWsClient, MockSubkeyAccount):
        MockApiClient.return_value.fetch_system_config.return_value = MOCK_SYSTEM_CONFIG
        p = ParadexL2(env=TESTNET, l2_private_key=L2_KEY, l2_address=L2_ADDR, ws_enabled=False)
        MockWsClient.assert_not_called()
        assert p.ws_client is None

    @patch("paradex_py.paradex_l2.SubkeyAccount")
    @patch("paradex_py.paradex_l2.ParadexWebsocketClient")
    @patch("paradex_py.paradex_l2.ParadexApiClient")
    def test_ws_enabled_false_no_ws_init_account(self, MockApiClient, MockWsClient, MockSubkeyAccount):
        MockApiClient.return_value.fetch_system_config.return_value = MOCK_SYSTEM_CONFIG
        ParadexL2(env=TESTNET, l2_private_key=L2_KEY, l2_address=L2_ADDR, ws_enabled=False)
        MockWsClient.return_value.init_account.assert_not_called()

    def test_missing_env_raises(self):
        with pytest.raises((ValueError, TypeError)):
            ParadexL2(env=None, l2_private_key=L2_KEY, l2_address=L2_ADDR)

    @patch("paradex_py.paradex_l2.ParadexApiClient")
    def test_missing_l2_private_key_raises(self, MockApiClient):
        MockApiClient.return_value.fetch_system_config.return_value = MOCK_SYSTEM_CONFIG
        with pytest.raises(ValueError):
            ParadexL2(env=TESTNET, l2_private_key="", l2_address=L2_ADDR)

    @patch("paradex_py.paradex_l2.ParadexApiClient")
    def test_missing_l2_address_raises(self, MockApiClient):
        MockApiClient.return_value.fetch_system_config.return_value = MOCK_SYSTEM_CONFIG
        with pytest.raises(ValueError):
            ParadexL2(env=TESTNET, l2_private_key=L2_KEY, l2_address="")

    @patch("paradex_py.paradex_l2.SubkeyAccount")
    @patch("paradex_py.paradex_l2.ParadexWebsocketClient")
    @patch("paradex_py.paradex_l2.ParadexApiClient")
    def test_capabilities_full(self, MockApiClient, MockWsClient, MockSubkeyAccount):
        MockApiClient.return_value.fetch_system_config.return_value = MOCK_SYSTEM_CONFIG
        p = ParadexL2(env=TESTNET, l2_private_key=L2_KEY, l2_address=L2_ADDR)
        assert p.auth_level == AuthLevel.FULL
        assert p.is_authenticated is True
        assert p.can_trade is True
        assert p.can_withdraw is True


# ---------------------------------------------------------------------------
# ParadexSubkey — trade-scoped, no withdrawals
# ---------------------------------------------------------------------------


class TestParadexSubkey:
    def test_is_subclass_of_paradex_l2(self):
        assert issubclass(ParadexSubkey, ParadexL2)

    @patch("paradex_py.paradex_l2.SubkeyAccount")
    @patch("paradex_py.paradex_l2.ParadexWebsocketClient")
    @patch("paradex_py.paradex_l2.ParadexApiClient")
    def test_capabilities_trading_no_withdraw(self, MockApiClient, MockWsClient, MockSubkeyAccount):
        MockApiClient.return_value.fetch_system_config.return_value = MOCK_SYSTEM_CONFIG
        p = ParadexSubkey(env=TESTNET, l2_private_key=L2_KEY, l2_address=L2_ADDR)
        assert p.auth_level == AuthLevel.TRADING
        assert p.is_authenticated is True
        assert p.can_trade is True
        assert p.can_withdraw is False

    @patch("paradex_py.paradex_l2.SubkeyAccount")
    @patch("paradex_py.paradex_l2.ParadexWebsocketClient")
    @patch("paradex_py.paradex_l2.ParadexApiClient")
    def test_auth_level_differs_from_parent(self, MockApiClient, MockWsClient, MockSubkeyAccount):
        """ParadexSubkey overrides auth_level to TRADING; ParadexL2 returns FULL."""
        MockApiClient.return_value.fetch_system_config.return_value = MOCK_SYSTEM_CONFIG
        subkey = ParadexSubkey(env=TESTNET, l2_private_key=L2_KEY, l2_address=L2_ADDR)
        l2 = ParadexL2(env=TESTNET, l2_private_key=L2_KEY, l2_address=L2_ADDR)
        assert subkey.auth_level == AuthLevel.TRADING
        assert l2.auth_level == AuthLevel.FULL


# ---------------------------------------------------------------------------
# ParadexApiKey — read-only
# ---------------------------------------------------------------------------


class TestParadexApiKey:
    @patch("paradex_py.paradex_api_key.ParadexWebsocketClient")
    @patch("paradex_py.paradex_api_key.ParadexApiClient")
    def test_successful_init(self, MockApiClient, MockWsClient):
        mock_api = MockApiClient.return_value
        mock_api.fetch_system_config.return_value = MOCK_SYSTEM_CONFIG

        p = ParadexApiKey(env=TESTNET, api_key=API_KEY)

        MockApiClient.assert_called_once_with(env=TESTNET, logger=None, auto_auth=False, on_token_expired=None)
        mock_api.fetch_system_config.assert_called_once()
        mock_api.set_token.assert_called_once_with(API_KEY)
        assert p.config is MOCK_SYSTEM_CONFIG

    @patch("paradex_py.paradex_api_key.ParadexWebsocketClient")
    @patch("paradex_py.paradex_api_key.ParadexApiClient")
    def test_on_token_expired_wired_to_api_client(self, MockApiClient, MockWsClient):
        MockApiClient.return_value.fetch_system_config.return_value = MOCK_SYSTEM_CONFIG
        callback = MagicMock(return_value="new-token")

        ParadexApiKey(env=TESTNET, api_key=API_KEY, on_token_expired=callback)

        MockApiClient.assert_called_once_with(env=TESTNET, logger=None, auto_auth=False, on_token_expired=callback)

    @patch("paradex_py.paradex_api_key.ParadexWebsocketClient")
    @patch("paradex_py.paradex_api_key.ParadexApiClient")
    def test_ws_client_receives_api_client(self, MockApiClient, MockWsClient):
        mock_api = MockApiClient.return_value
        mock_api.fetch_system_config.return_value = MOCK_SYSTEM_CONFIG

        ParadexApiKey(env=TESTNET, api_key=API_KEY)

        MockWsClient.assert_called_once_with(
            env=TESTNET, logger=None, ws_timeout=None, api_client=mock_api, sbe_enabled=False
        )

    @patch("paradex_py.paradex_api_key.ParadexWebsocketClient")
    @patch("paradex_py.paradex_api_key.ParadexApiClient")
    def test_ws_timeout_forwarded(self, MockApiClient, MockWsClient):
        MockApiClient.return_value.fetch_system_config.return_value = MOCK_SYSTEM_CONFIG
        ParadexApiKey(env=TESTNET, api_key=API_KEY, ws_timeout=30)
        MockWsClient.assert_called_once_with(
            env=TESTNET, logger=None, ws_timeout=30, api_client=MockApiClient.return_value, sbe_enabled=False
        )

    @patch("paradex_py.paradex_api_key.ParadexWebsocketClient")
    @patch("paradex_py.paradex_api_key.ParadexApiClient")
    def test_ws_enabled_false_skips_ws_client(self, MockApiClient, MockWsClient):
        MockApiClient.return_value.fetch_system_config.return_value = MOCK_SYSTEM_CONFIG
        p = ParadexApiKey(env=TESTNET, api_key=API_KEY, ws_enabled=False)
        MockWsClient.assert_not_called()
        assert p.ws_client is None

    def test_missing_env_raises(self):
        with pytest.raises((ValueError, TypeError)):
            ParadexApiKey(env=None, api_key=API_KEY)

    @patch("paradex_py.paradex_api_key.ParadexApiClient")
    def test_missing_api_key_raises(self, MockApiClient):
        MockApiClient.return_value.fetch_system_config.return_value = MOCK_SYSTEM_CONFIG
        with pytest.raises(ValueError):
            ParadexApiKey(env=TESTNET, api_key="")

    @patch("paradex_py.paradex_api_key.ParadexWebsocketClient")
    @patch("paradex_py.paradex_api_key.ParadexApiClient")
    def test_capabilities_authenticated_read_only(self, MockApiClient, MockWsClient):
        MockApiClient.return_value.fetch_system_config.return_value = MOCK_SYSTEM_CONFIG
        p = ParadexApiKey(env=TESTNET, api_key=API_KEY)
        assert p.auth_level == AuthLevel.AUTHENTICATED
        assert p.is_authenticated is True
        assert p.can_trade is False
        assert p.can_withdraw is False

    @patch("paradex_py.paradex_api_key.ParadexWebsocketClient")
    @patch("paradex_py.paradex_api_key.ParadexApiClient")
    def test_no_account_attribute(self, MockApiClient, MockWsClient):
        MockApiClient.return_value.fetch_system_config.return_value = MOCK_SYSTEM_CONFIG
        p = ParadexApiKey(env=TESTNET, api_key=API_KEY)
        assert not hasattr(p, "account")

    @patch("paradex_py.paradex_api_key.ParadexWebsocketClient")
    @patch("paradex_py.paradex_api_key.ParadexApiClient")
    def test_set_token_called_after_config(self, MockApiClient, MockWsClient):
        mock_api = MockApiClient.return_value
        call_order = []
        mock_api.fetch_system_config.side_effect = lambda: call_order.append("fetch_config") or MOCK_SYSTEM_CONFIG
        mock_api.set_token.side_effect = lambda _: call_order.append("set_token")

        ParadexApiKey(env=TESTNET, api_key=API_KEY)

        assert call_order == ["fetch_config", "set_token"]


# ---------------------------------------------------------------------------
# _jwt_exp helper
# ---------------------------------------------------------------------------


class TestJwtExp:
    def test_extracts_exp_from_valid_jwt(self):
        exp = time.time() + 3600
        token = _make_jwt(exp)
        result = _jwt_exp(token)
        assert result is not None
        assert abs(result - exp) < 1

    def test_returns_none_for_non_jwt(self):
        assert _jwt_exp("not-a-jwt") is None
        assert _jwt_exp("") is None
        assert _jwt_exp("only.two") is None

    def test_returns_none_for_jwt_without_exp(self):
        header = base64.urlsafe_b64encode(b'{"alg":"HS256"}').rstrip(b"=").decode()
        payload = base64.urlsafe_b64encode(b'{"sub":"user"}').rstrip(b"=").decode()
        token = f"{header}.{payload}.sig"
        assert _jwt_exp(token) is None


# ---------------------------------------------------------------------------
# on_token_expired — api_client._validate_auth behavior
# ---------------------------------------------------------------------------


class TestOnTokenExpired:
    @patch.object(ParadexApiClient, "fetch_system_config", return_value=MagicMock())
    def test_callback_called_when_token_expired(self, mock_config):
        new_token = "fresh-token"  # noqa: S105
        callback = MagicMock(return_value=new_token)

        client = ParadexApiClient(env=TESTNET, auto_auth=False, on_token_expired=callback)
        client.set_token("old-token")
        client.auth_timestamp = time.time() - 300  # 5 minutes ago → expired

        client._validate_auth()

        callback.assert_called_once()
        assert "Bearer fresh-token" in str(client.client.headers.get("Authorization", ""))

    @patch.object(ParadexApiClient, "fetch_system_config", return_value=MagicMock())
    def test_callback_not_called_when_token_fresh(self, mock_config):
        callback = MagicMock(return_value="fresh-token")

        client = ParadexApiClient(env=TESTNET, auto_auth=False, on_token_expired=callback)
        client.set_token("current-token")
        # auth_timestamp set by set_token — token is fresh

        client._validate_auth()

        callback.assert_not_called()

    @patch.object(ParadexApiClient, "fetch_system_config", return_value=MagicMock())
    def test_no_callback_expired_token_no_error(self, mock_config):
        """Without a callback, expired manual tokens are silently reused (no crash)."""
        client = ParadexApiClient(env=TESTNET, auto_auth=False)
        client.set_token("old-token")
        client.auth_timestamp = time.time() - 300

        # Should not raise
        client._validate_auth()

        assert "Bearer old-token" in str(client.client.headers.get("Authorization", ""))

    @patch.object(ParadexApiClient, "fetch_system_config", return_value=MagicMock())
    def test_callback_returning_none_leaves_old_token(self, mock_config):
        """If callback returns None, the old token stays in place."""
        callback = MagicMock(return_value=None)

        client = ParadexApiClient(env=TESTNET, auto_auth=False, on_token_expired=callback)
        client.set_token("old-token")
        client.auth_timestamp = time.time() - 300

        client._validate_auth()

        callback.assert_called_once()
        assert "Bearer old-token" in str(client.client.headers.get("Authorization", ""))

    @patch.object(ParadexApiClient, "fetch_system_config", return_value=MagicMock())
    def test_callback_returning_none_logs_warning(self, mock_config):
        """If callback returns None, a warning is logged."""
        callback = MagicMock(return_value=None)

        client = ParadexApiClient(env=TESTNET, auto_auth=False, on_token_expired=callback)
        client.set_token("old-token")
        client.auth_timestamp = time.time() - 300

        with patch.object(client.logger, "warning") as mock_warning:
            client._validate_auth()
            mock_warning.assert_called_once()
            assert "None" in mock_warning.call_args[0][0] or "expired" in mock_warning.call_args[0][0]

    @patch.object(ParadexApiClient, "fetch_system_config", return_value=MagicMock())
    def test_callback_updates_auth_timestamp(self, mock_config):
        """set_token() called by callback resets auth_timestamp."""
        callback = MagicMock(return_value="new-token")

        client = ParadexApiClient(env=TESTNET, auto_auth=False, on_token_expired=callback)
        client.set_token("old-token")
        client.auth_timestamp = time.time() - 300

        before = int(time.time())
        client._validate_auth()
        after = int(time.time()) + 1  # +1 to absorb int truncation

        assert before <= client.auth_timestamp <= after

    @patch.object(ParadexApiClient, "fetch_system_config", return_value=MagicMock())
    def test_callback_called_when_jwt_exp_in_past(self, mock_config):
        """Callback fires when JWT exp claim is in the past (JWT-based expiry)."""
        expired_token = _make_jwt(time.time() - 10)
        callback = MagicMock(return_value="fresh-token")

        client = ParadexApiClient(env=TESTNET, auto_auth=False, on_token_expired=callback)
        client.set_token(expired_token)

        client._validate_auth()

        callback.assert_called_once()

    @patch.object(ParadexApiClient, "fetch_system_config", return_value=MagicMock())
    def test_callback_not_called_when_jwt_exp_in_future(self, mock_config):
        """Callback does not fire when JWT exp claim is well in the future."""
        fresh_token = _make_jwt(time.time() + 3600)
        callback = MagicMock(return_value="fresh-token")

        client = ParadexApiClient(env=TESTNET, auto_auth=False, on_token_expired=callback)
        client.set_token(fresh_token)

        client._validate_auth()

        callback.assert_not_called()

    @patch.object(ParadexApiClient, "fetch_system_config", return_value=MagicMock())
    def test_jwt_exp_takes_precedence_over_auth_timestamp(self, mock_config):
        """A token with a far-future exp is not refreshed even if auth_timestamp is old."""
        far_future_token = _make_jwt(time.time() + 3600)
        callback = MagicMock(return_value="new-token")

        client = ParadexApiClient(env=TESTNET, auto_auth=False, on_token_expired=callback)
        client.set_token(far_future_token)
        # Simulate old auth_timestamp (would trigger fallback path)
        client.auth_timestamp = time.time() - 300

        client._validate_auth()

        # JWT exp says token is still valid — callback must NOT be called
        callback.assert_not_called()


# ---------------------------------------------------------------------------
# _validate_auth precedence: manual token > auth_provider
# ---------------------------------------------------------------------------


class TestValidateAuthPrecedence:
    @patch.object(ParadexApiClient, "fetch_system_config", return_value=MagicMock())
    def test_manual_token_bypasses_auth_provider(self, mock_config):
        """When both _manual_token and auth_provider are set, auth_provider is ignored."""
        auth_provider = MagicMock()
        auth_provider.refresh_if_needed.return_value = "provider-token"

        client = ParadexApiClient(env=TESTNET, auto_auth=False, auth_provider=auth_provider)
        client.set_token(_make_jwt(time.time() + 3600))

        client._validate_auth()

        auth_provider.refresh_if_needed.assert_not_called()
        assert "Authorization" in client.client.headers

    @patch.object(ParadexApiClient, "fetch_system_config", return_value=MagicMock())
    def test_manual_token_with_provider_logs_warning(self, mock_config):
        """A warning is logged when both _manual_token and auth_provider are set."""
        auth_provider = MagicMock()
        auth_provider.refresh_if_needed.return_value = "provider-token"

        client = ParadexApiClient(env=TESTNET, auto_auth=False, auth_provider=auth_provider)
        client.set_token(_make_jwt(time.time() - 10))  # expired → triggers refresh path
        callback = MagicMock(return_value="new-token")
        client.on_token_expired = callback

        with patch.object(client.logger, "warning") as mock_warning:
            client._validate_auth()
            mock_warning.assert_called_once()
            assert "auth_provider" in mock_warning.call_args[0][0]


# ---------------------------------------------------------------------------
# async with context manager
# ---------------------------------------------------------------------------


class TestAsyncContextManager:
    @patch("paradex_py.paradex_l2.SubkeyAccount")
    @patch("paradex_py.paradex_l2.ParadexWebsocketClient")
    @patch("paradex_py.paradex_l2.ParadexApiClient")
    @pytest.mark.asyncio
    async def test_paradex_l2_async_with(self, MockApiClient, MockWsClient, MockSubkeyAccount):
        MockApiClient.return_value.fetch_system_config.return_value = MOCK_SYSTEM_CONFIG
        mock_ws = MockWsClient.return_value
        mock_ws.close = AsyncMock()

        async with ParadexL2(env=TESTNET, l2_private_key=L2_KEY, l2_address=L2_ADDR) as client:
            assert client is not None

        mock_ws.close.assert_called_once()

    @patch("paradex_py.paradex_api_key.ParadexWebsocketClient")
    @patch("paradex_py.paradex_api_key.ParadexApiClient")
    @pytest.mark.asyncio
    async def test_paradex_api_key_async_with(self, MockApiClient, MockWsClient):
        MockApiClient.return_value.fetch_system_config.return_value = MOCK_SYSTEM_CONFIG
        mock_ws = MockWsClient.return_value
        mock_ws.close = AsyncMock()

        async with ParadexApiKey(env=TESTNET, api_key=API_KEY) as client:
            assert client is not None

        mock_ws.close.assert_called_once()

    @patch("paradex_py.paradex_api_key.ParadexWebsocketClient")
    @patch("paradex_py.paradex_api_key.ParadexApiClient")
    @pytest.mark.asyncio
    async def test_async_with_returns_self(self, MockApiClient, MockWsClient):
        MockApiClient.return_value.fetch_system_config.return_value = MOCK_SYSTEM_CONFIG
        MockWsClient.return_value.close = AsyncMock()

        p = ParadexApiKey(env=TESTNET, api_key=API_KEY)
        result = await p.__aenter__()
        assert result is p
        await p.__aexit__(None, None, None)

    @patch("paradex_py.paradex_api_key.ParadexWebsocketClient")
    @patch("paradex_py.paradex_api_key.ParadexApiClient")
    @pytest.mark.asyncio
    async def test_aexit_returns_false(self, MockApiClient, MockWsClient):
        """__aexit__ must return False so exceptions propagate normally."""
        MockApiClient.return_value.fetch_system_config.return_value = MOCK_SYSTEM_CONFIG
        MockWsClient.return_value.close = AsyncMock()

        p = ParadexApiKey(env=TESTNET, api_key=API_KEY)
        await p.__aenter__()
        result = await p.__aexit__(None, None, None)
        assert result is False


# ---------------------------------------------------------------------------
# ParadexSubkey with ws_enabled=False
# ---------------------------------------------------------------------------


class TestParadexSubkeyWsDisabled:
    @patch("paradex_py.paradex_l2.SubkeyAccount")
    @patch("paradex_py.paradex_l2.ParadexWebsocketClient")
    @patch("paradex_py.paradex_l2.ParadexApiClient")
    def test_ws_client_is_none(self, MockApiClient, MockWsClient, MockSubkeyAccount):
        MockApiClient.return_value.fetch_system_config.return_value = MOCK_SYSTEM_CONFIG
        p = ParadexSubkey(env=TESTNET, l2_private_key=L2_KEY, l2_address=L2_ADDR, ws_enabled=False)
        assert p.ws_client is None

    @patch("paradex_py.paradex_l2.SubkeyAccount")
    @patch("paradex_py.paradex_l2.ParadexWebsocketClient")
    @patch("paradex_py.paradex_l2.ParadexApiClient")
    def test_capabilities_preserved_when_ws_disabled(self, MockApiClient, MockWsClient, MockSubkeyAccount):
        MockApiClient.return_value.fetch_system_config.return_value = MOCK_SYSTEM_CONFIG
        p = ParadexSubkey(env=TESTNET, l2_private_key=L2_KEY, l2_address=L2_ADDR, ws_enabled=False)
        assert p.auth_level == AuthLevel.TRADING
        assert p.can_trade is True
        assert p.can_withdraw is False


# ---------------------------------------------------------------------------
# close() on partially-initialized client
# ---------------------------------------------------------------------------


class TestClosePartialInit:
    @pytest.mark.asyncio
    async def test_close_before_ws_client_set(self):
        """close() must not raise AttributeError if ws_client was never assigned."""
        from paradex_py._client_base import _ClientBase

        obj = object.__new__(_ClientBase)
        # Neither ws_client nor api_client are set — simulates constructor raising early
        await obj.close()  # must not raise

    @pytest.mark.asyncio
    async def test_close_with_none_ws_client(self):
        """close() is safe when ws_client is explicitly None."""
        from paradex_py._client_base import _ClientBase

        obj = object.__new__(_ClientBase)
        obj.ws_client = None
        # api_client not set
        await obj.close()  # must not raise

    @patch("paradex_py.paradex_api_key.ParadexWebsocketClient")
    @patch("paradex_py.paradex_api_key.ParadexApiClient")
    @pytest.mark.asyncio
    async def test_close_with_ws_enabled_false(self, MockApiClient, MockWsClient):
        """close() on a ws_enabled=False client closes only the HTTP client."""
        mock_api = MockApiClient.return_value
        mock_api.fetch_system_config.return_value = MOCK_SYSTEM_CONFIG
        mock_api.client = MagicMock()

        p = ParadexApiKey(env=TESTNET, api_key=API_KEY, ws_enabled=False)
        await p.close()

        MockWsClient.return_value.close.assert_not_called()
        mock_api.client.close.assert_called_once()


# ---------------------------------------------------------------------------
# ParadexEvm — full L2 account via EVM key
# ---------------------------------------------------------------------------


class TestParadexEvm:
    @patch("paradex_py.paradex_evm.EvmAccount")
    @patch("paradex_py.paradex_evm.ParadexWebsocketClient")
    @patch("paradex_py.paradex_evm.ParadexApiClient")
    def test_successful_init(self, MockApiClient, MockWsClient, MockEvmAccount):
        mock_api = MockApiClient.return_value
        mock_api.fetch_system_config.return_value = MOCK_SYSTEM_CONFIG

        p = ParadexEvm(env=TESTNET, evm_address=EVM_ADDR, evm_private_key=EVM_KEY)

        MockApiClient.assert_called_once_with(env=TESTNET, logger=None)
        mock_api.fetch_system_config.assert_called_once()
        MockEvmAccount.assert_called_once_with(
            config=MOCK_SYSTEM_CONFIG,
            env=TESTNET,
            evm_address=EVM_ADDR,
            evm_private_key=EVM_KEY,
        )
        mock_api.init_account_evm.assert_called_once_with(MockEvmAccount.return_value)
        assert p.config is MOCK_SYSTEM_CONFIG

    @patch("paradex_py.paradex_evm.EvmAccount")
    @patch("paradex_py.paradex_evm.ParadexWebsocketClient")
    @patch("paradex_py.paradex_evm.ParadexApiClient")
    def test_ws_timeout_forwarded(self, MockApiClient, MockWsClient, MockEvmAccount):
        MockApiClient.return_value.fetch_system_config.return_value = MOCK_SYSTEM_CONFIG
        ParadexEvm(env=TESTNET, evm_address=EVM_ADDR, evm_private_key=EVM_KEY, ws_timeout=42)
        MockWsClient.assert_called_once_with(
            env=TESTNET, logger=None, ws_timeout=42, api_client=MockApiClient.return_value, sbe_enabled=False
        )

    @patch("paradex_py.paradex_evm.EvmAccount")
    @patch("paradex_py.paradex_evm.ParadexWebsocketClient")
    @patch("paradex_py.paradex_evm.ParadexApiClient")
    def test_ws_enabled_false_skips_ws_client(self, MockApiClient, MockWsClient, MockEvmAccount):
        MockApiClient.return_value.fetch_system_config.return_value = MOCK_SYSTEM_CONFIG
        p = ParadexEvm(env=TESTNET, evm_address=EVM_ADDR, evm_private_key=EVM_KEY, ws_enabled=False)
        MockWsClient.assert_not_called()
        assert p.ws_client is None

    def test_missing_env_raises(self):
        with pytest.raises((ValueError, TypeError)):
            ParadexEvm(env=None, evm_address=EVM_ADDR, evm_private_key=EVM_KEY)

    @patch("paradex_py.paradex_evm.ParadexApiClient")
    def test_missing_evm_address_raises(self, MockApiClient):
        MockApiClient.return_value.fetch_system_config.return_value = MOCK_SYSTEM_CONFIG
        with pytest.raises(ValueError):
            ParadexEvm(env=TESTNET, evm_address="", evm_private_key=EVM_KEY)

    @patch("paradex_py.paradex_evm.ParadexApiClient")
    def test_missing_evm_private_key_raises(self, MockApiClient):
        MockApiClient.return_value.fetch_system_config.return_value = MOCK_SYSTEM_CONFIG
        with pytest.raises(ValueError):
            ParadexEvm(env=TESTNET, evm_address=EVM_ADDR, evm_private_key="")

    @patch("paradex_py.paradex_evm.EvmAccount")
    @patch("paradex_py.paradex_evm.ParadexWebsocketClient")
    @patch("paradex_py.paradex_evm.ParadexApiClient")
    def test_capabilities(self, MockApiClient, MockWsClient, MockEvmAccount):
        """Full account: withdraw yes, trade no (needs subkey), auth FULL."""
        MockApiClient.return_value.fetch_system_config.return_value = MOCK_SYSTEM_CONFIG
        p = ParadexEvm(env=TESTNET, evm_address=EVM_ADDR, evm_private_key=EVM_KEY)
        assert p.auth_level == AuthLevel.FULL
        assert p.is_authenticated is True
        assert p.can_trade is False
        assert p.can_withdraw is True

    @patch("paradex_py.paradex_evm.EvmAccount")
    @patch("paradex_py.paradex_evm.ParadexWebsocketClient")
    @patch("paradex_py.paradex_evm.ParadexApiClient")
    def test_create_trading_subkey_registers_and_returns_subkey(self, MockApiClient, MockWsClient, MockEvmAccount):
        mock_api = MockApiClient.return_value
        mock_api.fetch_system_config.return_value = MOCK_SYSTEM_CONFIG
        MockEvmAccount.return_value.l2_address = 0xDEADBEEF

        p = ParadexEvm(env=TESTNET, evm_address=EVM_ADDR, evm_private_key=EVM_KEY)

        with (
            patch("paradex_py.paradex_evm.KeyPair") as MockKeyPair,
            patch("paradex_py.paradex_evm.secrets") as MockSecrets,
            patch("paradex_py.paradex_subkey.ParadexSubkey") as MockSubkeyClass,
        ):
            MockSecrets.randbelow.return_value = 0x1234
            mock_kp = MagicMock()
            mock_kp.public_key = 0x5678
            MockKeyPair.from_private_key.return_value = mock_kp

            result = p.create_trading_subkey(name="test-key")

        MockSecrets.randbelow.assert_called_once_with(2**251)
        MockKeyPair.from_private_key.assert_called_once_with(0x1234)
        mock_api.create_subkey.assert_called_once_with(
            {"name": "test-key", "public_key": hex(0x5678), "state": "active"}
        )
        MockSubkeyClass.assert_called_once_with(
            env=TESTNET,
            l2_private_key=hex(0x1234),
            l2_address=hex(0xDEADBEEF),
        )
        assert result is MockSubkeyClass.return_value

    @patch("paradex_py.paradex_evm.EvmAccount")
    @patch("paradex_py.paradex_evm.ParadexWebsocketClient")
    @patch("paradex_py.paradex_evm.ParadexApiClient")
    def test_create_trading_subkey_default_name(self, MockApiClient, MockWsClient, MockEvmAccount):
        mock_api = MockApiClient.return_value
        mock_api.fetch_system_config.return_value = MOCK_SYSTEM_CONFIG
        MockEvmAccount.return_value.l2_address = 0xDEADBEEF

        p = ParadexEvm(env=TESTNET, evm_address=EVM_ADDR, evm_private_key=EVM_KEY)

        with (
            patch("paradex_py.paradex_evm.KeyPair") as MockKeyPair,
            patch("paradex_py.paradex_evm.secrets") as MockSecrets,
            patch("paradex_py.paradex_subkey.ParadexSubkey"),
        ):
            MockSecrets.randbelow.return_value = 0x1234
            MockKeyPair.from_private_key.return_value.public_key = 0x5678
            p.create_trading_subkey()

        mock_api.create_subkey.assert_called_once_with(
            {"name": "trading", "public_key": hex(0x5678), "state": "active"}
        )


# ---------------------------------------------------------------------------
# Import smoke test
# ---------------------------------------------------------------------------


def test_all_classes_importable_from_paradex_py():
    from paradex_py import AuthLevel, ParadexApiKey, ParadexL2, ParadexSubkey  # noqa: F401


def test_environment_importable_from_paradex_py():
    from paradex_py import PROD, TESTNET, Environment  # noqa: F401

    assert PROD == "prod"
    assert TESTNET == "testnet"


def test_invalid_env_string_raises():
    with pytest.raises(ValueError, match="mainnet"):
        ParadexL2(env="mainnet", l2_private_key=L2_KEY, l2_address=L2_ADDR)


def test_invalid_env_string_raises_api_key():
    with pytest.raises(ValueError, match="mainnet"):
        ParadexApiKey(env="mainnet", api_key=API_KEY)
