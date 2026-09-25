from decimal import Decimal
from unittest.mock import Mock, patch

import pytest

from paradex_py.api.api_client import ParadexApiClient
from paradex_py.environment import TESTNET

MOCK_CONFIG = {
    "base_asset": "BTC",
    "interval_ms": 1000,
    "frozen_time_ms": 5000,
    "size_limit": "60",
    "delta_limit": "20",
    "vega_limit": "5000",
    "updated_at": 1717171717000,
}


class TestMmpConfig:
    def setup_method(self):
        self.api_client = ParadexApiClient(env=TESTNET)
        self.api_client.account = Mock()
        self.api_client._validate_auth = Mock()

    def test_fetch_mmp_configs(self):
        with patch.object(self.api_client, "get") as mock_get:
            mock_get.return_value = {"account": "0x1234", "enabled": True, "results": [MOCK_CONFIG]}

            configs = self.api_client.fetch_mmp_configs()

            mock_get.assert_called_once_with(api_url=self.api_client.api_url, path="account/mmp", params=None)
            assert configs.account == "0x1234"
            assert configs.enabled is True
            assert configs.results[0].base_asset == "BTC"
            assert configs.results[0].interval_ms == 1000
            assert configs.results[0].vega_limit == "5000"
            self.api_client._validate_auth.assert_called_once()

    def test_fetch_mmp_configs_with_base_asset_filter(self):
        with patch.object(self.api_client, "get") as mock_get:
            mock_get.return_value = {"account": "0x1234", "enabled": True, "results": [MOCK_CONFIG]}

            self.api_client.fetch_mmp_configs(params={"base_asset": "BTC"})

            mock_get.assert_called_once_with(
                api_url=self.api_client.api_url, path="account/mmp", params={"base_asset": "BTC"}
            )

    def test_fetch_mmp_configs_tolerates_new_server_fields(self):
        """Fields the server adds later must not break an already released SDK.

        `unknown` passed to load() does not reach the nested config schema, so
        both levels carry a field this SDK has never heard of.
        """
        with patch.object(self.api_client, "get") as mock_get:
            mock_get.return_value = {
                "account": "0x1234",
                "enabled": True,
                "some_future_field": "ignored",
                "results": [{**MOCK_CONFIG, "some_future_per_entry_field": 1717171722640}],
            }

            configs = self.api_client.fetch_mmp_configs()

            assert configs.results[0].base_asset == "BTC"
            assert configs.results[0].vega_limit == "5000"

    def test_fetch_mmp_configs_when_not_enabled(self):
        """A disabled account still lists its configs, which stay enforced."""
        with patch.object(self.api_client, "get") as mock_get:
            mock_get.return_value = {"account": "0x1234", "enabled": False, "results": []}

            configs = self.api_client.fetch_mmp_configs()

            assert configs.enabled is False
            assert configs.results == []

    def test_set_mmp_config(self):
        with patch.object(self.api_client, "post") as mock_post:
            mock_post.return_value = MOCK_CONFIG

            config = self.api_client.set_mmp_config(
                base_asset="BTC",
                interval_ms=1000,
                frozen_time_ms=5000,
                size_limit=Decimal("60"),
                delta_limit=Decimal("20"),
                vega_limit=Decimal("5000"),
            )

            mock_post.assert_called_once_with(
                api_url=self.api_client.api_url,
                path="account/mmp/BTC",
                payload={
                    "interval_ms": 1000,
                    "frozen_time_ms": 5000,
                    "size_limit": "60",
                    "delta_limit": "20",
                    "vega_limit": "5000",
                },
                params=None,
                headers=None,
            )
            assert config.base_asset == "BTC"
            assert config.updated_at == 1717171717000

    def test_set_mmp_config_omitted_limits_are_sent_as_zero(self):
        """The endpoint is a full upsert, so an omitted limit disables that check."""
        with patch.object(self.api_client, "post") as mock_post:
            mock_post.return_value = MOCK_CONFIG

            self.api_client.set_mmp_config(base_asset="BTC", interval_ms=1000, frozen_time_ms=5000, size_limit=60)

            payload = mock_post.call_args.kwargs["payload"]
            assert payload["size_limit"] == "60"
            assert payload["delta_limit"] == "0"
            assert payload["vega_limit"] == "0"

    def test_set_mmp_config_renders_limits_as_plain_decimals(self):
        """Exponent notation is rejected by the server."""
        with patch.object(self.api_client, "post") as mock_post:
            mock_post.return_value = MOCK_CONFIG

            self.api_client.set_mmp_config(
                base_asset="BTC", interval_ms=1000, frozen_time_ms=5000, vega_limit=Decimal("1E+3")
            )

            assert mock_post.call_args.kwargs["payload"]["vega_limit"] == "1000"

    @pytest.mark.parametrize("interval_ms", [0, 99, 3_600_001])
    def test_set_mmp_config_rejects_interval_out_of_bounds(self, interval_ms):
        """0 is out of range too: removing a config is DELETE only."""
        with pytest.raises(ValueError, match="interval_ms must be"):
            self.api_client.set_mmp_config(
                base_asset="BTC", interval_ms=interval_ms, frozen_time_ms=5000, size_limit=60
            )

    def test_set_mmp_config_rejects_limit_below_min_increment(self):
        """The server requires every limit to be a multiple of 0.0001."""
        with pytest.raises(ValueError, match="size_limit must be a multiple of"):
            self.api_client.set_mmp_config(
                base_asset="BTC", interval_ms=1000, frozen_time_ms=5000, size_limit="0.00005"
            )

    def test_set_mmp_config_accepts_limit_on_min_increment(self):
        with patch.object(self.api_client, "post") as mock_post:
            mock_post.return_value = MOCK_CONFIG

            self.api_client.set_mmp_config(base_asset="BTC", interval_ms=1000, frozen_time_ms=5000, size_limit="0.0001")

            assert mock_post.call_args.kwargs["payload"]["size_limit"] == "0.0001"

    @pytest.mark.parametrize("limit", ["not-a-number", float("inf"), float("nan")])
    def test_set_mmp_config_rejects_limits_that_are_not_numbers(self, limit):
        """Infinity and NaN parse as Decimal but are not limits the server takes."""
        with pytest.raises(ValueError, match="delta_limit must be a decimal number"):
            self.api_client.set_mmp_config(
                base_asset="BTC", interval_ms=1000, frozen_time_ms=5000, size_limit=60, delta_limit=limit
            )

    def test_set_mmp_config_reads_empty_limit_as_disabled(self):
        """The server reads an empty limit as 0, so "" must not blow up here."""
        with patch.object(self.api_client, "post") as mock_post:
            mock_post.return_value = MOCK_CONFIG

            self.api_client.set_mmp_config(
                base_asset="BTC", interval_ms=1000, frozen_time_ms=5000, size_limit=60, delta_limit=""
            )

            assert mock_post.call_args.kwargs["payload"]["delta_limit"] == "0"

    def test_set_mmp_config_rejects_negative_limit(self):
        with pytest.raises(ValueError, match="delta_limit must not be negative"):
            self.api_client.set_mmp_config(
                base_asset="BTC", interval_ms=1000, frozen_time_ms=5000, size_limit=60, delta_limit=-1
            )

    @pytest.mark.parametrize("frozen_time_ms", [-1, 3_600_001])
    def test_set_mmp_config_rejects_frozen_time_out_of_bounds(self, frozen_time_ms):
        with pytest.raises(ValueError, match="frozen_time_ms must be"):
            self.api_client.set_mmp_config(
                base_asset="BTC", interval_ms=1000, frozen_time_ms=frozen_time_ms, size_limit=60
            )

    def test_set_mmp_config_requires_a_limit(self):
        with pytest.raises(ValueError, match="at least one of size_limit"):
            self.api_client.set_mmp_config(base_asset="BTC", interval_ms=1000, frozen_time_ms=5000)

    def test_set_mmp_config_zero_limits_do_not_count(self):
        with pytest.raises(ValueError, match="at least one of size_limit"):
            self.api_client.set_mmp_config(
                base_asset="BTC", interval_ms=1000, frozen_time_ms=5000, size_limit=0, delta_limit="0"
            )

    def test_set_mmp_config_accepts_manual_reset_freeze(self):
        """frozen_time_ms 0 freezes until reset_mmp, and the server accepts it."""
        with patch.object(self.api_client, "post") as mock_post:
            mock_post.return_value = {**MOCK_CONFIG, "frozen_time_ms": 0}

            config = self.api_client.set_mmp_config(base_asset="BTC", interval_ms=1000, frozen_time_ms=0, size_limit=60)

            assert mock_post.call_args.kwargs["payload"]["frozen_time_ms"] == 0
            assert config.frozen_time_ms == 0

    def test_set_mmp_config_tolerates_absurd_limit(self):
        """A limit too large to check locally is the server's to reject, not ours."""
        with patch.object(self.api_client, "post") as mock_post:
            mock_post.return_value = MOCK_CONFIG

            self.api_client.set_mmp_config(
                base_asset="BTC", interval_ms=1000, frozen_time_ms=5000, size_limit=Decimal("1E+30")
            )

            assert mock_post.call_args.kwargs["payload"]["size_limit"] == "1" + "0" * 30

    def test_fetch_mmp_configs_reads_live_status(self):
        with patch.object(self.api_client, "get") as mock_get:
            mock_get.return_value = {
                "account": "0x1234",
                "enabled": True,
                "results": [
                    {
                        **MOCK_CONFIG,
                        "is_frozen": True,
                        "frozen_until": 0,
                        "window_size": "12.5",
                        "window_delta": "-3.2",
                        "window_vega": "840",
                    }
                ],
            }

            config = self.api_client.fetch_mmp_configs().results[0]

            assert config.is_frozen is True
            # 0 means "until a manual reset" here, which is why is_frozen exists.
            assert config.frozen_until == 0
            assert config.window_delta == "-3.2"

    def test_fetch_mmp_configs_without_live_status(self):
        """Live fields are omitted when matching enforces an older config version."""
        with patch.object(self.api_client, "get") as mock_get:
            mock_get.return_value = {"account": "0x1234", "enabled": True, "results": [MOCK_CONFIG]}

            config = self.api_client.fetch_mmp_configs().results[0]

            assert config.is_frozen is None
            assert config.window_size is None

    def test_reset_mmp_all_base_assets(self):
        with patch.object(self.api_client, "post") as mock_post:
            mock_post.return_value = {"results": [{"base_asset": "BTC", "reset_at": 1717171717000}]}

            reset = self.api_client.reset_mmp()

            mock_post.assert_called_once_with(
                api_url=self.api_client.api_url,
                path="account/mmp/reset",
                payload={},
                params=None,
                headers=None,
            )
            assert reset.results[0].base_asset == "BTC"
            assert reset.results[0].reset_at == 1717171717000

    def test_reset_mmp_one_base_asset(self):
        with patch.object(self.api_client, "post") as mock_post:
            mock_post.return_value = {"results": [{"base_asset": "ETH", "reset_at": 1}]}

            self.api_client.reset_mmp("ETH")

            assert mock_post.call_args.kwargs["payload"] == {"base_asset": "ETH"}

    def test_reset_mmp_with_nothing_enabled(self):
        with patch.object(self.api_client, "post") as mock_post:
            mock_post.return_value = {"results": []}

            assert self.api_client.reset_mmp().results == []

    def test_reset_mmp_rejects_empty_base_asset(self):
        """An unset variable must not silently unfreeze every base asset."""
        with pytest.raises(ValueError, match="base_asset must not be empty"):
            self.api_client.reset_mmp("")

    def test_delete_mmp_config(self):
        with patch.object(self.api_client, "delete") as mock_delete:
            mock_delete.return_value = None

            assert self.api_client.delete_mmp_config("BTC") is None

            mock_delete.assert_called_once_with(
                api_url=self.api_client.api_url, path="account/mmp/BTC", params=None, payload=None
            )
