"""Internal helpers shared across the margin engine."""

from __future__ import annotations

from collections.abc import Mapping
from typing import SupportsFloat, SupportsIndex, TypeAlias, TypeVar, cast

T = TypeVar("T")
FloatLike: TypeAlias = str | bytes | bytearray | SupportsFloat | SupportsIndex


def _require(value: T | None, key: str, ctx: str = "") -> T:
    if value is None or value == "":
        where = f" ({ctx})" if ctx else ""
        raise ValueError(f"required margin field {key!r} is missing{where}")
    return value


def _req_f(d: Mapping[str, object], key: str, ctx: str = "") -> float:
    """Return a required numeric field.

    Use for any value that changes margin, P&L, liquidation, or risk. Missing
    financial inputs raise instead of becoming zero.
    """
    return float(cast(FloatLike, _require(d.get(key), key, ctx)))


def _opt_f(d: Mapping[str, object], key: str) -> float | None:
    """Return an optional numeric field, preserving missing as ``None``."""
    value = d.get(key)
    if value is None or value == "":
        return None
    return float(cast(FloatLike, value))


def _req_str(d: Mapping[str, object], key: str, ctx: str = "") -> str:
    return str(_require(d.get(key), key, ctx))


def _req_dict(d: Mapping[str, object], key: str, ctx: str = "") -> Mapping[str, object]:
    value = _require(d.get(key), key, ctx)
    if not isinstance(value, Mapping):
        where = f" ({ctx})" if ctx else ""
        raise TypeError(f"required margin field {key!r} must be a mapping{where}")
    return cast(Mapping[str, object], value)
