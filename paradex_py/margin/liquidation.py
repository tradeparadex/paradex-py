"""Liquidation-price finder.

Locates the spot at which ``account_value(s) - mmr(s)`` crosses zero. Uses
pluggable mark-to-market and margin functions so callers can adapt it to
either the live SDK margin schema or backtester-style position tracking.

Option portfolios can produce non-monotonic health curves, so the public helper
scans the full search range for every sign-change bracket before refining with
a small Brent/bisection hybrid.
"""

from collections.abc import Callable


def _brent(f: Callable[[float], float], a: float, b: float, tol: float = 1e-8, max_iter: int = 80) -> float | None:
    fa, fb = f(a), f(b)
    if fa * fb > 0:
        return None
    if abs(fa) < abs(fb):
        a, b, fa, fb = b, a, fb, fa
    c, fc = a, fa
    mflag = True
    d = 0.0
    for _ in range(max_iter):
        if abs(fb) < tol:
            return b
        if abs(fa - fc) > 1e-15 and abs(fb - fc) > 1e-15:
            s = (
                a * fb * fc / ((fa - fb) * (fa - fc))
                + b * fa * fc / ((fb - fa) * (fb - fc))
                + c * fa * fb / ((fc - fa) * (fc - fb))
            )
        else:
            s = b - fb * (b - a) / (fb - fa)

        lo, hi = sorted((a, b))
        cond1 = not (lo < s < hi)
        cond2 = mflag and abs(s - b) >= abs(b - c) / 2
        cond3 = (not mflag) and abs(s - b) >= abs(c - d) / 2
        cond4 = mflag and abs(b - c) < tol
        cond5 = (not mflag) and abs(c - d) < tol
        if cond1 or cond2 or cond3 or cond4 or cond5:
            s = 0.5 * (a + b)
            mflag = True
        else:
            mflag = False

        fs = f(s)
        d, c, fc = c, b, fb
        if fa * fs < 0:
            b, fb = s, fs
        else:
            a, fa = s, fs
        if abs(fa) < abs(fb):
            a, b, fa, fb = b, a, fb, fa
        if abs(b - a) < tol:
            return b
    return b


def find_liquidation_price(
    spot: float,
    account_value_at: Callable[[float], float],
    mmr_at: Callable[[float], float],
    *,
    lo_factor: float = 0.01,
    hi_factor: float = 5.0,
    scan_points: int = 300,
) -> dict:
    """Locate liquidation prices on either side of the current spot.

    Args:
        spot: Current underlying price.
        account_value_at(test_spot): Returns account equity at the given spot.
        mmr_at(test_spot): Returns maintenance margin requirement at the spot.
        lo_factor / hi_factor: Spot multipliers used to bracket the search.
        scan_points: Number of evenly spaced points to inspect before Brent
            refinement. Higher values can catch tighter non-monotonic pockets.

    Returns:
        {"down", "up", "nearest", "dist_pct"} — None when no bracketed root
        exists on that side. If multiple roots exist on one side, the nearest
        one to current spot is returned for that side.
    """

    def f(test_spot: float) -> float:
        return account_value_at(test_spot) - mmr_at(test_spot)

    lo, hi = spot * lo_factor, spot * hi_factor
    scan_points = max(2, scan_points)
    step = (hi - lo) / (scan_points - 1)
    roots: list[float] = []

    prev_x = lo
    prev_f = f(prev_x)
    if prev_f == 0:
        roots.append(prev_x)
    for i in range(1, scan_points):
        x = lo + i * step
        fx = f(x)
        if fx == 0:
            roots.append(x)
        elif prev_f * fx < 0:
            root = _brent(f, prev_x, x)
            if root is not None:
                roots.append(root)
        prev_x, prev_f = x, fx

    roots = sorted({round(root, 10): root for root in roots}.values())
    below = [root for root in roots if root < spot]
    above = [root for root in roots if root >= spot]
    liq_down = below[-1] if below else None
    liq_up = above[0] if above else None

    nearest: float | None
    nearest = (liq_down if spot - liq_down < liq_up - spot else liq_up) if liq_down and liq_up else liq_down or liq_up

    dist_pct = abs(spot - nearest) / spot * 100 if nearest else None
    return {"down": liq_down, "up": liq_up, "nearest": nearest, "dist_pct": dist_pct}
