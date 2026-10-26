"""Session-key grants: typed data an account owner signs to let a session key trade.

The owner signs one grant. A scoped, expiring Stark session key then mints
short-lived JWTs and signs orders for the accounts the grant lists. It can
never withdraw. Three messages share one set of field semantics:

- ``SessionGrant``: the owner lets ``sessionKey`` act on ``account`` and its
  listed ``subaccounts``, within ``scopes`` and ``limits``, until ``expiresAt``.
- ``PasskeyGrant``: the owner lets a passkey open sessions within a ``ceiling``.
- ``SessionMint``: what a passkey signs (as the WebAuthn challenge) to open one
  session within that ceiling.

Each has two encodings with the same field names and order:

- EIP-712 for EVM (EIP-191) owners. The domain is
  ``{name: "Paradex Session", version: "1", chainId: <wallet's current chain>}``,
  so the wallet never has to switch networks. The Paradex chain and environment
  are message fields.
- SNIP-12 revision 1 (Poseidon) for Stark-key owners, with the domain
  ``{name: "Paradex Session", version: "1", chainId: <Paradex chain>, revision: "1"}``.

Hashes must match the server byte for byte, so the field order, type names and
string forms here are part of the wire contract. Addresses and keys are
rendered as lowercase ``0x`` hex with no leading zeros (``hex(int(x, 16))``),
the same form the SDK uses for ``PARADEX-STARKNET-ACCOUNT``.

Examples:
    >>> grant = SessionGrant.new(
    ...     paradex_chain="PRIVATE_SN_PARACLEAR_MAINNET",
    ...     environment="mainnet",
    ...     account="0x1234",
    ...     session_key="0x5678",
    ...     label="my bot",
    ...     scopes=["trade"],
    ...     limits=Limits("25000", "100000", "500000", "5000", "10", ["BTC-USD-PERP"]),
    ...     ttl_seconds=7 * 24 * 3600,
    ... )
    >>> typed_data = grant.eip712_typed_data(signature_chain_id=1)  # for any EIP-712 signer
    >>> signature = grant.sign_eip712("0x<owner-eth-private-key>", signature_chain_id=1)
"""

from __future__ import annotations

import base64
import re
import secrets
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from fnmatch import fnmatchcase
from types import MappingProxyType
from typing import Any, cast

from eth_account import Account as EthAccount
from eth_account.messages import _hash_eip191_message, encode_typed_data
from starknet_py.constants import FIELD_PRIME
from starknet_py.hash.utils import message_signature
from starknet_py.net.models.typed_data import TypedDataDict
from starknet_py.utils.typed_data import TypedData

from paradex_py.utils import raise_value_error

__all__ = [
    "ALL_MARKETS",
    "DEFAULT_LIMIT_CAPS",
    "DOMAIN_NAME",
    "DOMAIN_VERSION",
    "GRANTABLE_SCOPES",
    "NO_LIMIT",
    "REFUSED_SCOPES",
    "Builder",
    "Ceiling",
    "Limits",
    "Passkey",
    "PasskeyGrant",
    "SessionGrant",
    "SessionMint",
    "grant_environment",
    "new_nonce",
]

DOMAIN_NAME = "Paradex Session"
DOMAIN_VERSION = "1"

# Scopes a session may be granted. "read" is always implied and never listed.
GRANTABLE_SCOPES = frozenset({"trade", "trade:rfq", "trade:block", "account:settings"})
# Reserved names the server refuses: a session never withdraws, and isolated margin is wound down.
REFUSED_SCOPES = frozenset({"withdraw:owner", "trade:isolated"})
# Scopes the server caps at 7 days whatever the session kind.
_SHORT_LIVED_SCOPES = frozenset({"trade:block", "account:settings"})
# Scopes only first-party grants may carry; a grant that approves a builder may not.
_FIRST_PARTY_SCOPES = frozenset({"trade:block", "account:settings"})

# SDK environment names that differ from the environment a grant names.
_GRANT_ENVIRONMENT = {"prod": "mainnet"}

DAY_SECONDS = 24 * 3600
SHORT_LIVED_SCOPE_MAX_SECONDS = 7 * DAY_SECONDS
# The longest any session lives (IP-pinned API sessions); browser sessions are capped lower by the server.
SESSION_MAX_SECONDS = 180 * DAY_SECONDS
NO_BUILDER = "0x0"

_NONCE_BITS = 128
_SHORTSTRING_MAX = 31
_PLAIN_DECIMAL = re.compile(r"^(0|[1-9]\d*)(\.\d+)?$")
# Lowercase hex with no leading zeros: non-zero and at most 128 bits, i.e. hex(n).
_NONCE = re.compile(r"^0x[1-9a-f][0-9a-f]{0,31}$")
_P256_COORDINATE = re.compile(r"^0x[0-9a-f]{64}$")
_MARKET = re.compile(r"^[A-Za-z0-9_*-]{1,31}$")
# Optional client-side caps on stated limits, by message field name, refused before signing. None by
# default: the server enforces its own configured caps.
DEFAULT_LIMIT_CAPS: Mapping[str, str] = MappingProxyType({})
# Integers stay below 2^53 so every JSON implementation reads them exactly.
_UINT_MAX = 2**53 - 1


def new_nonce() -> str:
    """Return a fresh random nonce of 128 bits, as lowercase ``0x`` hex with no leading zeros."""
    while True:
        nonce = secrets.randbits(_NONCE_BITS)
        if nonce >> (_NONCE_BITS - 4):  # keep the full width; any non-zero value would be valid
            return hex(nonce)


def grant_environment(env: str) -> str:
    """The ``environment`` a grant names for an SDK environment (``prod`` is ``mainnet``)."""
    return _GRANT_ENVIRONMENT.get(env, env)


def _hex(value: str | int, what: str) -> str:
    """Render a felt or address in the canonical ``0x`` form, rejecting what is not one."""
    try:
        number = value if isinstance(value, int) else int(value, 16)
    except (TypeError, ValueError):
        raise_value_error(f"{what} must be a 0x hex string, got {value!r}")
    if not 0 <= number < FIELD_PRIME:
        raise_value_error(f"{what} is out of the felt range: {value!r}")
    return hex(number)


def _decimal(value: str, what: str) -> str:
    if not isinstance(value, str) or not _PLAIN_DECIMAL.match(value):
        raise_value_error(f"{what} must be a plain non-negative decimal like '25000' or '0.0005', got {value!r}")
    return value


NO_LIMIT = "none"
ALL_MARKETS = "*"
_LIMIT_NAMES = ("maxOrderNotional", "maxOpenNotional", "dailyNotional", "maxLoss", "maxLeverage")


def _limit(value: str, what: str) -> str:
    """A stated limit: a positive plain decimal, or ``"none"`` for no cap."""
    if value == NO_LIMIT:
        return value
    if not isinstance(value, str) or not _PLAIN_DECIMAL.match(value) or Decimal(value) <= 0:
        raise_value_error(f"limits.{what} must be a positive decimal like '25000', or 'none' for no cap, got {value!r}")
    return value


def _shortstring(value: str, what: str) -> str:
    if not isinstance(value, str) or not value or len(value) > _SHORTSTRING_MAX or not _printable_ascii(value):
        raise_value_error(f"{what} must be 1-{_SHORTSTRING_MAX} ASCII characters, got {value!r}")
    return value


def _printable_ascii(value: str) -> bool:
    return value.isascii() and value.isprintable()


def _uint(value: int, what: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= _UINT_MAX:
        raise_value_error(f"{what} must be an integer in [0, 2^53), got {value!r}")
    return value


def _market(value: str) -> str:
    """A market symbol, or a pattern where ``*`` matches any run of characters (``"*"`` alone: all)."""
    # A shortstring without a letter, '*' or '-', or starting 0x/0b/0o, would be read as a number in SNIP-12.
    if (
        not isinstance(value, str)
        or not _MARKET.match(value)
        or not any(c.isalpha() or c in "*-" for c in value)
        or value[:2].lower() in ("0x", "0b", "0o")
        or value.startswith("-")
    ):
        raise_value_error(
            "market must be 1-31 of letters, digits, '_', '*' and '-', with a letter, '*' or '-', "
            f"not starting '-', 0x, 0b or 0o, got {value!r}"
        )
    if "*" in value and value != ALL_MARKETS and ("**" in value or not any(c.isalnum() for c in value)):
        raise_value_error(f"market pattern needs a letter or digit and no '**', got {value!r}")
    return value


def _market_covered(market: str, ceiling: Sequence[str]) -> bool:
    """Whether the ceiling lists a mint's market, or (for a symbol) one of the ceiling's patterns matches it.

    A mint pattern is covered only by the same pattern.
    """
    if market in ceiling:
        return True
    return "*" not in market and any("*" in pattern and fnmatchcase(market, pattern) for pattern in ceiling)


def _p256_coordinate(value: str, what: str) -> str:
    if not isinstance(value, str) or not _P256_COORDINATE.match(value):
        raise_value_error(f"{what} must be 0x and 64 lowercase hex digits, got {value!r}")
    return value


def _environment(value: str) -> str:
    # The server checks the value; the SDK only makes sure it can be encoded.
    return _shortstring(value, "environment")


def _scopes(scopes: Sequence[str]) -> list[str]:
    scope_list = list(scopes)
    if not scope_list:
        raise_value_error("scopes must name at least one scope")
    for scope in scope_list:
        if scope in REFUSED_SCOPES:
            raise_value_error(f"scope {scope!r} is reserved and refused for sessions")
        if scope not in GRANTABLE_SCOPES:
            raise_value_error(f"unknown scope {scope!r}; grantable scopes are {sorted(GRANTABLE_SCOPES)}")
    if len(set(scope_list)) != len(scope_list):
        raise_value_error(f"scopes must not repeat: {scope_list}")
    return scope_list


def _nonce(nonce: str) -> str:
    if not isinstance(nonce, str) or not _NONCE.match(nonce):
        raise_value_error(
            f"nonce must be non-zero lowercase 0x hex of at most 128 bits, no leading zeros, got {nonce!r}"
        )
    return nonce


def _subaccounts(account: str, subaccounts: Sequence[str]) -> list[str]:
    rendered = [_hex(address, "subaccount") for address in subaccounts]
    if len(set(rendered)) != len(rendered):
        raise_value_error(f"subaccounts must not repeat: {rendered}")
    if account in rendered:
        raise_value_error("subaccounts must not list the anchor account itself")
    return rendered


def _window(issued_at: int, expires_at: int) -> None:
    _uint(issued_at, "issuedAt")
    _uint(expires_at, "expiresAt")
    if expires_at <= issued_at:
        raise_value_error(f"expiresAt ({expires_at}) must be after issuedAt ({issued_at})")


def _require_ascii(value: Any, path: str = "message") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            _require_ascii(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _require_ascii(item, f"{path}[{index}]")
    elif isinstance(value, str) and not _printable_ascii(value):
        raise_value_error(f"{path} must be printable ASCII for SNIP-12 signing, got {value!r}")


def _decimal_integers(value: Any) -> Any:
    """SNIP-12 messages carry integers as decimal strings (the hash is the same either way)."""
    if isinstance(value, dict):
        return {key: _decimal_integers(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_decimal_integers(item) for item in value]
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    return value


def _eip712_domain(signature_chain_id: int) -> dict[str, Any]:
    if not isinstance(signature_chain_id, int) or isinstance(signature_chain_id, bool) or signature_chain_id <= 0:
        raise_value_error(f"signature_chain_id must be a positive EVM chain id, got {signature_chain_id!r}")
    return {"name": DOMAIN_NAME, "version": DOMAIN_VERSION, "chainId": signature_chain_id}


def _snip12_domain(paradex_chain: str) -> dict[str, Any]:
    return {"name": DOMAIN_NAME, "version": DOMAIN_VERSION, "chainId": paradex_chain, "revision": "1"}


_EIP712_DOMAIN_TYPE = [
    {"name": "name", "type": "string"},
    {"name": "version", "type": "string"},
    {"name": "chainId", "type": "uint256"},
]
_SNIP12_DOMAIN_TYPE = [
    {"name": "name", "type": "shortstring"},
    {"name": "version", "type": "shortstring"},
    {"name": "chainId", "type": "shortstring"},
    {"name": "revision", "type": "shortstring"},
]


def _fields(spec: Sequence[tuple[str, str, str]], encoding: str) -> list[dict[str, str]]:
    index = 1 if encoding == "eip712" else 2
    return [{"name": entry[0], "type": entry[index]} for entry in spec]


# (name, EIP-712 type, SNIP-12 rev 1 type). Order is part of the hash.
_LIMITS = (
    ("maxOrderNotional", "string", "string"),
    ("maxOpenNotional", "string", "string"),
    ("dailyNotional", "string", "string"),
    ("maxLoss", "string", "string"),
    ("maxLeverage", "string", "string"),
    ("markets", "string[]", "shortstring*"),
)
_BUILDER = (
    ("account", "string", "ContractAddress"),
    ("maxFeeRate", "string", "string"),
    ("expiresAt", "uint64", "timestamp"),
)
_SESSION_GRANT = (
    ("paradexChain", "string", "shortstring"),
    ("environment", "string", "shortstring"),
    ("account", "string", "ContractAddress"),
    ("sessionKey", "string", "felt"),
    ("label", "string", "string"),
    ("scopes", "string[]", "shortstring*"),
    ("limits", "Limits", "Limits"),
    ("builder", "Builder", "Builder"),
    ("subaccounts", "string[]", "ContractAddress*"),
    ("nonce", "string", "felt"),
    ("issuedAt", "uint64", "timestamp"),
    ("expiresAt", "uint64", "timestamp"),
)
_PASSKEY = (
    ("credentialId", "string", "string"),
    ("pubkeyX", "string", "string"),
    ("pubkeyY", "string", "string"),
    ("rpId", "string", "string"),
    ("label", "string", "string"),
)
_CEILING = (
    ("scopes", "string[]", "shortstring*"),
    ("limits", "Limits", "Limits"),
    ("subaccounts", "string[]", "ContractAddress*"),
    ("includeFutureSubaccounts", "bool", "bool"),
    ("maxSessionTtl", "uint64", "u128"),
    ("maxConcurrentSessions", "uint64", "u128"),
)
_PASSKEY_GRANT = (
    ("paradexChain", "string", "shortstring"),
    ("environment", "string", "shortstring"),
    ("account", "string", "ContractAddress"),
    ("passkey", "Passkey", "Passkey"),
    ("ceiling", "Ceiling", "Ceiling"),
    ("builderAccount", "string", "ContractAddress"),
    ("nonce", "string", "felt"),
    ("issuedAt", "uint64", "timestamp"),
    ("expiresAt", "uint64", "timestamp"),
)
_SESSION_MINT = (
    ("paradexChain", "string", "shortstring"),
    ("environment", "string", "shortstring"),
    ("account", "string", "ContractAddress"),
    ("credentialId", "string", "string"),
    ("sessionKey", "string", "felt"),
    ("scopes", "string[]", "shortstring*"),
    ("limits", "Limits", "Limits"),
    ("subaccounts", "string[]", "ContractAddress*"),
    ("nonce", "string", "felt"),
    ("expiresAt", "uint64", "timestamp"),
)


@dataclass(frozen=True)
class Limits:
    """Trading limits, each stated: a positive USD decimal (``maxLeverage`` is a multiplier) or ``"none"``.

    ``"none"`` means no cap from this session; empty strings are refused. ``markets`` lists symbols or
    patterns such as ``"*-USD-PERP"``, or is ``["*"]`` for every permitted market; it may not be empty.
    ``caps`` optionally refuses a stated limit above a value before anything is signed, keyed by message
    field name (e.g. ``{"maxOrderNotional": "250000"}``); ``"none"`` is over any cap. There are no caps
    by default (:data:`DEFAULT_LIMIT_CAPS`); the server enforces its own.
    """

    max_order_notional: str
    max_open_notional: str
    daily_notional: str
    max_loss: str
    max_leverage: str
    markets: Sequence[str] = (ALL_MARKETS,)
    caps: Mapping[str, str] = field(default_factory=lambda: DEFAULT_LIMIT_CAPS, compare=False, repr=False)

    def to_message(self, *, numeric_max_loss: bool = False) -> dict[str, Any]:
        message: dict[str, Any] = {
            "maxOrderNotional": _limit(self.max_order_notional, "maxOrderNotional"),
            "maxOpenNotional": _limit(self.max_open_notional, "maxOpenNotional"),
            "dailyNotional": _limit(self.daily_notional, "dailyNotional"),
            "maxLoss": _limit(self.max_loss, "maxLoss"),
            "maxLeverage": _limit(self.max_leverage, "maxLeverage"),
            "markets": _markets(self.markets),
        }
        if numeric_max_loss and message["maxLoss"] == NO_LIMIT:
            raise_value_error("limits.maxLoss must be a number on builder grants, not 'none'")
        for name, cap in self.caps.items():
            if name not in _LIMIT_NAMES:
                raise_value_error(f"limit cap names an unknown limit {name!r}")
            if message[name] == NO_LIMIT or Decimal(message[name]) > Decimal(cap):
                raise_value_error(f"limits.{name} {message[name]} is over the cap of {cap}")
        return message

    def loss_wording(self) -> str:
        """The plain-words risk line to show the owner before they sign."""
        if self.max_loss == NO_LIMIT:
            return "Cannot withdraw; trading losses are not capped by this session"
        return f"Cannot withdraw; can lose up to {self.max_loss} USD by trading"


def _markets(markets: Sequence[str]) -> list[str]:
    rendered = [_market(market) for market in markets]
    if not rendered:
        raise_value_error("limits.markets must not be empty; use ['*'] for every permitted market")
    if ALL_MARKETS in rendered and len(rendered) > 1:
        raise_value_error("limits.markets: '*' stands alone")
    return rendered


@dataclass(frozen=True)
class Builder:
    """The builder a grant approves, with its maximum fee rate. ``account="0x0"`` means none.

    ``expires_at=0`` makes the approval follow the session's own expiry.
    """

    account: str = NO_BUILDER
    max_fee_rate: str = "0"
    expires_at: int = 0

    @property
    def is_set(self) -> bool:
        return int(_hex(self.account, "builder.account"), 16) != 0

    def to_message(self) -> dict[str, Any]:
        message = {
            "account": _hex(self.account, "builder.account"),
            "maxFeeRate": _decimal(self.max_fee_rate, "builder.maxFeeRate"),
            "expiresAt": _uint(self.expires_at, "builder.expiresAt"),
        }
        if message["account"] == NO_BUILDER and (message["maxFeeRate"] != "0" or message["expiresAt"] != 0):
            raise_value_error('a grant without a builder uses builder {account: "0x0", maxFeeRate: "0", expiresAt: 0}')
        return message


class _TypedMessage:
    """Shared EIP-712 / SNIP-12 rendering, hashing and local signing."""

    _PRIMARY: str
    _SPEC: tuple[tuple[str, str, str], ...]
    _STRUCTS: dict[str, tuple[tuple[str, str, str], ...]]

    paradex_chain: str
    account: str

    def to_message(self) -> dict[str, Any]:
        raise NotImplementedError

    def _types(self, encoding: str) -> dict[str, list[dict[str, str]]]:
        types = {self._PRIMARY: _fields(self._SPEC, encoding)}
        for name, spec in self._STRUCTS.items():
            types[name] = _fields(spec, encoding)
        return types

    def eip712_typed_data(self, signature_chain_id: int) -> dict[str, Any]:
        """The EIP-712 typed data for an EVM owner, ready for ``eth_signTypedData_v4`` or any external signer."""
        return {
            "types": {"EIP712Domain": _EIP712_DOMAIN_TYPE, **self._types("eip712")},
            "primaryType": self._PRIMARY,
            "domain": _eip712_domain(signature_chain_id),
            "message": self.to_message(),
        }

    def eip712_hash(self, signature_chain_id: int) -> bytes:
        """The 32-byte EIP-712 digest the owner's wallet signs."""
        signable = encode_typed_data(full_message=self.eip712_typed_data(signature_chain_id))
        return bytes(_hash_eip191_message(signable))

    def sign_eip712(self, eth_private_key: str, signature_chain_id: int) -> str:
        """Sign with a local EVM key; returns the 65-byte ``0x`` r||s||v signature."""
        signable = encode_typed_data(full_message=self.eip712_typed_data(signature_chain_id))
        signature = EthAccount.sign_message(signable, eth_private_key).signature.hex()
        return signature if signature.startswith("0x") else "0x" + signature

    def snip12_typed_data(self) -> TypedDataDict:
        """The SNIP-12 revision 1 typed data for a Stark-key owner.

        starknet-py encodes SNIP-12 ``string`` values as ASCII only, so free text (labels, passkey
        fields) must be ASCII here. EIP-712 has no such limit.
        """
        message = _decimal_integers(self.to_message())
        _require_ascii(message)
        return cast(
            TypedDataDict,
            {
                "types": {"StarknetDomain": _SNIP12_DOMAIN_TYPE, **self._types("snip12")},
                "primaryType": self._PRIMARY,
                "domain": _snip12_domain(message["paradexChain"]),
                "message": message,
            },
        )

    def snip12_hash(self) -> int:
        """The SNIP-12 message hash, bound to the grant's ``account``."""
        typed_data = TypedData.from_dict(self.snip12_typed_data())
        return typed_data.message_hash(int(_hex(self.account, "account"), 16))

    def sign_snip12(self, stark_private_key: str | int) -> list[str]:
        """Sign with a local Stark key; returns ``[r, s]`` as decimal strings."""
        key = stark_private_key if isinstance(stark_private_key, int) else int(stark_private_key, 16)
        r, s = message_signature(self.snip12_hash(), key)
        return [str(r), str(s)]


@dataclass(frozen=True)
class SessionGrant(_TypedMessage):
    """An owner's grant letting a Stark session key trade the named accounts.

    Args:
        paradex_chain: Paradex chain id string, e.g. ``"PRIVATE_SN_PARACLEAR_MAINNET"``.
        environment: ``"mainnet"`` or ``"testnet"`` (see :func:`grant_environment`); checked by the server.
        account: The anchor account address; its owner signs the grant.
        session_key: The session's Stark public key.
        label: The front end's own label. Display uses the builder's registered name, not this.
        scopes: Granted scopes, from :data:`GRANTABLE_SCOPES`.
        limits: Trading limits.
        builder: Builder approval; ``Builder()`` for none.
        subaccounts: Sub-account addresses the session also covers. Empty means the anchor only.
        nonce: 128-bit random ``0x`` hex, chosen by the client (see :func:`new_nonce`).
        issued_at: Seconds since the epoch.
        expires_at: Seconds since the epoch; the server caps it per scope.
    """

    paradex_chain: str
    environment: str
    account: str
    session_key: str
    label: str
    scopes: Sequence[str]
    limits: Limits
    builder: Builder = field(default_factory=Builder)
    subaccounts: Sequence[str] = ()
    nonce: str = field(default_factory=new_nonce)
    issued_at: int = field(default_factory=lambda: int(time.time()))
    expires_at: int = 0

    _PRIMARY = "SessionGrant"
    _SPEC = _SESSION_GRANT
    _STRUCTS = {"Limits": _LIMITS, "Builder": _BUILDER}  # noqa: RUF012

    @classmethod
    def new(cls, *, ttl_seconds: int, **kwargs: Any) -> SessionGrant:
        """Build a grant issued now, expiring ``ttl_seconds`` later, with a fresh nonce."""
        issued_at = int(time.time())
        return cls(issued_at=issued_at, expires_at=issued_at + ttl_seconds, **kwargs)

    def to_message(self) -> dict[str, Any]:
        """Validate and render the message, refusing what the server would refuse."""
        account = _hex(self.account, "account")
        scopes = _scopes(self.scopes)
        _window(self.issued_at, self.expires_at)
        lifetime = self.expires_at - self.issued_at
        if lifetime > SESSION_MAX_SECONDS:
            raise_value_error(f"a session lives at most {SESSION_MAX_SECONDS // DAY_SECONDS} days")
        if _SHORT_LIVED_SCOPES.intersection(scopes) and lifetime > SHORT_LIVED_SCOPE_MAX_SECONDS:
            raise_value_error("sessions with trade:block or account:settings live at most 7 days")
        if self.builder.is_set and _FIRST_PARTY_SCOPES.intersection(scopes):
            raise_value_error("builder grants may not carry trade:block or account:settings")
        if self.builder.is_set and self.builder.expires_at and self.builder.expires_at > self.expires_at:
            raise_value_error("builder.expiresAt must not outlive the session")
        if not isinstance(self.label, str):
            raise_value_error("label must be a string")
        return {
            "paradexChain": _shortstring(self.paradex_chain, "paradexChain"),
            "environment": _environment(self.environment),
            "account": account,
            "sessionKey": _hex(self.session_key, "sessionKey"),
            "label": self.label,
            "scopes": scopes,
            # A builder grant must cap losses.
            "limits": self.limits.to_message(numeric_max_loss=self.builder.is_set),
            "builder": self.builder.to_message(),
            "subaccounts": _subaccounts(account, self.subaccounts),
            "nonce": _nonce(self.nonce),
            "issuedAt": self.issued_at,
            "expiresAt": self.expires_at,
        }

    @property
    def accounts(self) -> list[str]:
        """Every account the session covers: the anchor first, then the listed sub-accounts."""
        message = self.to_message()
        return [message["account"], *message["subaccounts"]]


@dataclass(frozen=True)
class Passkey:
    """The passkey a ``PasskeyGrant`` registers (P-256 coordinates as ``0x`` hex)."""

    credential_id: str
    pubkey_x: str
    pubkey_y: str
    rp_id: str
    label: str = ""

    def to_message(self) -> dict[str, Any]:
        if not self.credential_id or not self.rp_id:
            raise_value_error("passkey credentialId and rpId are required")
        return {
            "credentialId": self.credential_id,
            "pubkeyX": _p256_coordinate(self.pubkey_x, "passkey.pubkeyX"),
            "pubkeyY": _p256_coordinate(self.pubkey_y, "passkey.pubkeyY"),
            "rpId": self.rp_id,
            "label": self.label,
        }


@dataclass(frozen=True)
class Ceiling:
    """The most a passkey may grant any session it opens."""

    scopes: Sequence[str]
    limits: Limits
    max_session_ttl: int
    max_concurrent_sessions: int
    subaccounts: Sequence[str] = ()
    include_future_subaccounts: bool = False

    def to_message(self, account: str, *, numeric_max_loss: bool = False) -> dict[str, Any]:
        if _uint(self.max_session_ttl, "maxSessionTtl") == 0 or self.max_session_ttl > SESSION_MAX_SECONDS:
            raise_value_error(f"ceiling.maxSessionTtl must be 1..{SESSION_MAX_SECONDS} seconds")
        if _uint(self.max_concurrent_sessions, "maxConcurrentSessions") == 0:
            raise_value_error("ceiling.maxConcurrentSessions must be positive")
        return {
            "scopes": _scopes(self.scopes),
            "limits": self.limits.to_message(numeric_max_loss=numeric_max_loss),
            "subaccounts": _subaccounts(account, self.subaccounts),
            "includeFutureSubaccounts": bool(self.include_future_subaccounts),
            "maxSessionTtl": _uint(self.max_session_ttl, "maxSessionTtl"),
            "maxConcurrentSessions": _uint(self.max_concurrent_sessions, "maxConcurrentSessions"),
        }


@dataclass(frozen=True)
class PasskeyGrant(_TypedMessage):
    """An owner's grant letting a passkey open sessions within ``ceiling``.

    ``builder_account="0x0"`` binds the passkey to the Paradex app; any other address binds it to that
    builder. ``include_future_subaccounts`` is allowed only for the Paradex app's own passkeys.
    """

    paradex_chain: str
    environment: str
    account: str
    passkey: Passkey
    ceiling: Ceiling
    builder_account: str = NO_BUILDER
    nonce: str = field(default_factory=new_nonce)
    issued_at: int = field(default_factory=lambda: int(time.time()))
    expires_at: int = 0

    _PRIMARY = "PasskeyGrant"
    _SPEC = _PASSKEY_GRANT
    _STRUCTS = {"Passkey": _PASSKEY, "Ceiling": _CEILING, "Limits": _LIMITS}  # noqa: RUF012

    def to_message(self) -> dict[str, Any]:
        account = _hex(self.account, "account")
        builder_account = _hex(self.builder_account, "builderAccount")
        if self.ceiling.include_future_subaccounts and int(builder_account, 16) != 0:
            raise_value_error("includeFutureSubaccounts is allowed only on first-party passkeys (builderAccount 0x0)")
        _window(self.issued_at, self.expires_at)
        return {
            "paradexChain": _shortstring(self.paradex_chain, "paradexChain"),
            "environment": _environment(self.environment),
            "account": account,
            "passkey": self.passkey.to_message(),
            # A builder passkey must cap losses.
            "ceiling": self.ceiling.to_message(account, numeric_max_loss=int(builder_account, 16) != 0),
            "builderAccount": builder_account,
            "nonce": _nonce(self.nonce),
            "issuedAt": self.issued_at,
            "expiresAt": self.expires_at,
        }


@dataclass(frozen=True)
class SessionMint(_TypedMessage):
    """What a passkey signs to open one session; its hash is the WebAuthn challenge."""

    paradex_chain: str
    environment: str
    account: str
    credential_id: str
    session_key: str
    scopes: Sequence[str]
    limits: Limits
    expires_at: int
    subaccounts: Sequence[str] = ()
    nonce: str = field(default_factory=new_nonce)

    _PRIMARY = "SessionMint"
    _SPEC = _SESSION_MINT
    _STRUCTS = {"Limits": _LIMITS}  # noqa: RUF012

    def to_message(self) -> dict[str, Any]:
        account = _hex(self.account, "account")
        if not self.credential_id:
            raise_value_error("credentialId is required")
        return {
            "paradexChain": _shortstring(self.paradex_chain, "paradexChain"),
            "environment": _environment(self.environment),
            "account": account,
            "credentialId": self.credential_id,
            "sessionKey": _hex(self.session_key, "sessionKey"),
            "scopes": _scopes(self.scopes),
            "limits": self.limits.to_message(),
            "subaccounts": _subaccounts(account, self.subaccounts),
            "nonce": _nonce(self.nonce),
            "expiresAt": _uint(self.expires_at, "expiresAt"),
        }

    def webauthn_challenge(self) -> str:
        """The WebAuthn challenge: base64url (unpadded) of the 32-byte big-endian SNIP-12 hash."""
        digest = self.snip12_hash().to_bytes(32, "big")
        return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()

    def check_within(self, grant: PasskeyGrant, *, now: int | None = None) -> None:
        """Refuse a mint the server would refuse against ``grant``'s ceiling, before the passkey signs it.

        Under a numeric ceiling limit the mint states a number at or below it; under a ``"none"`` ceiling
        limit anything goes. Markets must be a subset of the ceiling's, unless the ceiling is ``["*"]``.
        """
        message, granted = self.to_message(), grant.to_message()
        ceiling = granted["ceiling"]
        for name in ("account", "paradexChain", "environment"):
            if message[name] != granted[name]:
                raise_value_error(f"mint {name} is not the grant's")
        if message["credentialId"] != granted["passkey"]["credentialId"]:
            raise_value_error("mint credentialId is not the grant's passkey")
        if not set(message["scopes"]) <= set(ceiling["scopes"]):
            raise_value_error(f"mint scopes {message['scopes']} exceed the ceiling's {ceiling['scopes']}")
        _check_limits_within(message["limits"], ceiling["limits"])
        if not ceiling["includeFutureSubaccounts"] and not set(message["subaccounts"]) <= set(ceiling["subaccounts"]):
            raise_value_error("mint lists sub-accounts the ceiling does not")
        now = int(time.time()) if now is None else now
        if message["expiresAt"] <= now:
            raise_value_error("mint has already expired")
        if message["expiresAt"] > min(granted["expiresAt"], now + ceiling["maxSessionTtl"]):
            raise_value_error("mint outlives the grant or the ceiling's maxSessionTtl")


def _check_limits_within(mint: dict[str, Any], ceiling: dict[str, Any]) -> None:
    for name in _LIMIT_NAMES:
        if ceiling[name] == NO_LIMIT:
            continue  # anything goes under an uncapped ceiling
        if mint[name] == NO_LIMIT or Decimal(mint[name]) > Decimal(ceiling[name]):
            raise_value_error(f"limits.{name} must be a number at most the ceiling's {ceiling[name]}")
    if ceiling["markets"] != [ALL_MARKETS] and not all(
        _market_covered(market, ceiling["markets"]) for market in mint["markets"]
    ):
        raise_value_error("limits.markets must be covered by the ceiling's markets")
