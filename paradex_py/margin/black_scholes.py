"""Black-Scholes pricing and Greeks used by Paradex margin calculations.

`norm_cdf` uses the Abramowitz-Stegun approximation (matches the exchange PM
calculator). `math.erf` would be equally correct but produces tiny numerical
differences vs. the reference implementation; we keep A-S for byte-equality.
"""

import math


def norm_cdf(x: float) -> float:
    a1, a2, a3, a4, a5, p = (
        0.254829592,
        -0.284496736,
        1.421413741,
        -1.453152027,
        1.061405429,
        0.3275911,
    )
    sign = -1 if x < 0 else 1
    x = abs(x) / math.sqrt(2)
    t = 1.0 / (1.0 + p * x)
    y = 1 - (((((a5 * t + a4) * t) + a3) * t + a2) * t + a1) * t * math.exp(-x * x)
    return 0.5 * (1 + sign * y)


def norm_pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


def bs_price(S: float, K: float, T: float, r: float, sigma: float, is_call: bool) -> float:
    """European Black-Scholes option price."""
    if T <= 0 or sigma <= 0:
        return max(0.0, S - K if is_call else K - S)
    cp = 1 if is_call else -1
    d1 = (math.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    return cp * S * norm_cdf(cp * d1) - cp * K * math.exp(-r * T) * norm_cdf(cp * d2)


def bs_delta(S: float, K: float, T: float, r: float, sigma: float, is_call: bool) -> float:
    if T <= 1e-10 or sigma <= 0:
        if is_call:
            return 1.0 if S > K else 0.0
        return -1.0 if S < K else 0.0
    d1 = (math.log(S / K) + (r + 0.5 * sigma * sigma) * T) / (sigma * math.sqrt(T))
    return norm_cdf(d1) if is_call else norm_cdf(d1) - 1.0


def bs_gamma(S: float, K: float, T: float, r: float, sigma: float) -> float:
    if T <= 1e-10 or sigma <= 0:
        return 0.0
    sqT = math.sqrt(T)
    d1 = (math.log(S / K) + (r + 0.5 * sigma * sigma) * T) / (sigma * sqT)
    return norm_pdf(d1) / (S * sigma * sqT)


def bs_vega(S: float, K: float, T: float, r: float, sigma: float) -> float:
    """Vega per 1% change in IV (i.e. divided by 100)."""
    if T <= 1e-10 or sigma <= 0:
        return 0.0
    sqT = math.sqrt(T)
    d1 = (math.log(S / K) + (r + 0.5 * sigma * sigma) * T) / (sigma * sqT)
    return S * sqT * norm_pdf(d1) / 100.0
