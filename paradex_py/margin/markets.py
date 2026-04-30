"""Market metadata and symbol parsing helpers."""

import re
from collections.abc import Mapping
from datetime import datetime, timezone
from types import MappingProxyType
from typing import Any, Final

from .constants import OPTION_EXPIRY_HOUR

MONTH_MAP: Final[Mapping[str, int]] = MappingProxyType(
    {
        "JAN": 1,
        "FEB": 2,
        "MAR": 3,
        "APR": 4,
        "MAY": 5,
        "JUN": 6,
        "JUL": 7,
        "AUG": 8,
        "SEP": 9,
        "OCT": 10,
        "NOV": 11,
        "DEC": 12,
    }
)


def _get_field(obj: Any, key: str) -> Any:
    if isinstance(obj, Mapping):
        return obj.get(key)
    return getattr(obj, key, None)


def market_expiry(market_spec: Any | None) -> datetime | None:
    """Return exchange-published expiry from market metadata, if present.

    Paradex market responses expose ``expiry_at``. Prefer that value when live
    metadata is available; symbol parsing remains an offline fallback.
    """
    raw = _get_field(market_spec, "expiry_at")
    if raw in (None, "", 0, "0"):
        return None
    try:
        ts = float(raw)
    except (TypeError, ValueError):
        return None
    if ts > 10_000_000_000:
        ts /= 1000
    return datetime.fromtimestamp(ts, tz=timezone.utc)


def parse_expiry(s: str) -> datetime | None:
    """Parse ``8MAY26`` into the default option expiry time, or ``None``."""
    match = re.match(r"^(\d{1,2})([A-Z]{3})(\d{2})$", s or "")
    if not match:
        return None
    mon = MONTH_MAP.get(match.group(2))
    if mon is None:
        return None
    return datetime(2000 + int(match.group(3)), mon, int(match.group(1)), OPTION_EXPIRY_HOUR, tzinfo=timezone.utc)


def parse_market(symbol: str, market_spec: Any | None = None) -> dict | None:
    """Parse a Paradex market symbol into its components.

    ``market_spec`` may be a dict or generated ``MarketResp``. When supplied,
    ``expiry_at`` wins over the date encoded in the symbol.

    Returns:
        - {"type": "perp"} for perpetuals
        - {"type": "dated_option", "is_call", "strike", "expiry"} for options
        - {"type": "perp_option", "is_call", "strike"} for perpetual options
        - None if the symbol does not match any known format
    """
    parts = symbol.split("-")
    if parts[-1] == "PERP":
        return {"type": "perp"}
    if parts[-1] in ("C", "P"):
        is_call = parts[-1] == "C"
        if len(parts) == 5:
            p2_num = parts[2].replace(".", "").isdigit()
            strike = float(parts[3] if not p2_num else parts[2])
            exp_str = parts[2] if not p2_num else parts[3]
            return {
                "type": "dated_option",
                "is_call": is_call,
                "strike": strike,
                "expiry": market_expiry(market_spec) or parse_expiry(exp_str),
            }
        if len(parts) == 4:
            return {"type": "perp_option", "is_call": is_call, "strike": float(parts[2])}
    return None
