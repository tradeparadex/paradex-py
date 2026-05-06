"""Delta-hedge sizing utilities."""

import math
from collections.abc import Mapping

from ._utils import _req_f


def delta_hedge_size(
    portfolio_delta: float,
    instrument_delta: float,
    *,
    size_increment: float,
) -> tuple[str, float]:
    """Compute the side and size needed to neutralise portfolio delta.

    Adding (side_sign x size x instrument_delta) to portfolio_delta should
    equal zero. Positive portfolio_delta → SELL; negative → BUY. Size is
    rounded down to the nearest `size_increment`. Returns ("NONE", 0) when
    the delta is already within one increment of zero.
    """
    if size_increment <= 0:
        raise ValueError("size_increment must be positive")
    if instrument_delta == 0:
        raise ValueError("instrument_delta must be non-zero")
    if abs(portfolio_delta) < size_increment:
        return "NONE", 0.0

    ratio = -portfolio_delta / instrument_delta
    side = "BUY" if ratio > 0 else "SELL"
    steps = math.floor(round(abs(ratio) / size_increment, 8))
    return side, round(steps * size_increment, 8)


def delta_hedge_size_for_market(
    portfolio_delta: float,
    instrument_delta: float,
    market_spec: Mapping[str, object],
) -> tuple[str, float]:
    """Compute hedge size using the exchange-published order size increment."""
    size_increment = _req_f(market_spec, "order_size_increment", "hedge market")
    return delta_hedge_size(
        portfolio_delta,
        instrument_delta,
        size_increment=size_increment,
    )
