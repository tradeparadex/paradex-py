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

import re
import secrets
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, cast

from eth_account import Account as EthAccount
from eth_account.messages import _hash_eip191_message, encode_typed_data
from starknet_py.hash.utils import message_signature
from starknet_py.net.models.typed_data import TypedDataDict
from starknet_py.utils.typed_data import TypedData

from paradex_py.utils import raise_value_error

__all__ = [
    "DOMAIN_NAME",
    "DOMAIN_VERSION",
    "GRANTABLE_SCOPES",
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

ENVIRONMENTS = frozenset({"mainnet", "testnet", "nightly"})
# SDK environment name -> the environment a grant names.
_GRANT_ENVIRONMENT = {"prod": "mainnet", "testnet": "testnet", "nightly": "nightly"}

DAY_SECONDS = 24 * 3600
SHORT_LIVED_SCOPE_MAX_SECONDS = 7 * DAY_SECONDS
# The longest any session lives (IP-pinned API sessions); browser sessions are capped lower by the server.
SESSION_MAX_SECONDS = 180 * DAY_SECONDS
NO_BUILDER = "0x0"

_NONCE_BITS = 128
_SHORTSTRING_MAX = 31
_PLAIN_DECIMAL = re.compile(r"^(0|[1-9]\d*)(\.\d+)?$")
_UINT64_MAX = 2**64 - 1


def new_nonce() -> str:
    """Return a fresh 128-bit random nonce as ``0x`` hex."""
    return hex(secrets.randbits(_NONCE_BITS))


def grant_environment(env: str) -> str:
    """Map an SDK environment (``prod``/``testnet``/``nightly``) to a grant's ``environment``."""
    if env not in _GRANT_ENVIRONMENT:
        raise_value_error(f"Unknown environment {env!r}; expected one of {sorted(_GRANT_ENVIRONMENT)}")
    return _GRANT_ENVIRONMENT[env]


def _hex(value: str | int, what: str) -> str:
    """Render a felt or address in the canonical ``0x`` form, rejecting what is not one."""
    try:
        number = value if isinstance(value, int) else int(value, 16)
    except (TypeError, ValueError):
        raise_value_error(f"{what} must be a 0x hex string, got {value!r}")
    if number < 0 or number.bit_length() > 252:
        raise_value_error(f"{what} is out of the felt range: {value!r}")
    return hex(number)


def _decimal(value: str, what: str, *, required: bool) -> str:
    if not isinstance(value, str):
        raise_value_error(f"{what} must be a decimal string, got {value!r}")
    if value == "" and not required:
        return value
    if not _PLAIN_DECIMAL.match(value):
        raise_value_error(f"{what} must be a plain non-negative decimal like '25000' or '0.0005', got {value!r}")
    return value


def _shortstring(value: str, what: str) -> str:
    if not isinstance(value, str) or not value or len(value) > _SHORTSTRING_MAX or not value.isascii():
        raise_value_error(f"{what} must be 1-{_SHORTSTRING_MAX} ASCII characters, got {value!r}")
    return value


def _uint64(value: int, what: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= _UINT64_MAX:
        raise_value_error(f"{what} must be a uint64, got {value!r}")
    return value


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
    rendered = _hex(nonce, "nonce")
    if int(rendered, 16).bit_length() > _NONCE_BITS:
        raise_value_error(f"nonce must fit in {_NONCE_BITS} bits, got {nonce!r}")
    return rendered


def _subaccounts(account: str, subaccounts: Sequence[str]) -> list[str]:
    rendered = [_hex(address, "subaccount") for address in subaccounts]
    if len(set(rendered)) != len(rendered):
        raise_value_error(f"subaccounts must not repeat: {rendered}")
    if account in rendered:
        raise_value_error("subaccounts must not list the anchor account itself")
    return rendered


def _window(issued_at: int, expires_at: int) -> None:
    _uint64(issued_at, "issuedAt")
    _uint64(expires_at, "expiresAt")
    if expires_at <= issued_at:
        raise_value_error(f"expiresAt ({expires_at}) must be after issuedAt ({issued_at})")


def _require_ascii(value: Any, path: str = "message") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            _require_ascii(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _require_ascii(item, f"{path}[{index}]")
    elif isinstance(value, str) and not value.isascii():
        raise_value_error(f"{path} must be ASCII for SNIP-12 signing, got {value!r}")


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
    ("subaccounts", "string[]", "ContractAddress*"),
    ("credentialId", "string", "string"),
    ("sessionKey", "string", "felt"),
    ("scopes", "string[]", "shortstring*"),
    ("limits", "Limits", "Limits"),
    ("nonce", "string", "felt"),
    ("expiresAt", "uint64", "timestamp"),
)


@dataclass(frozen=True)
class Limits:
    """Trading limits, as USD decimal strings (``maxLeverage`` is a multiplier).

    An empty string leaves that limit at the server default; builder grants must state every one.
    ``markets`` lists symbols or patterns such as ``"*-USD-PERP"``; empty means the server default.
    """

    max_order_notional: str
    max_open_notional: str
    daily_notional: str
    max_loss: str
    max_leverage: str
    markets: Sequence[str] = ()

    def to_message(self, *, every_limit_stated: bool = False) -> dict[str, Any]:
        return {
            "maxOrderNotional": _decimal(self.max_order_notional, "maxOrderNotional", required=every_limit_stated),
            "maxOpenNotional": _decimal(self.max_open_notional, "maxOpenNotional", required=every_limit_stated),
            "dailyNotional": _decimal(self.daily_notional, "dailyNotional", required=every_limit_stated),
            "maxLoss": _decimal(self.max_loss, "maxLoss", required=every_limit_stated),
            "maxLeverage": _decimal(self.max_leverage, "maxLeverage", required=every_limit_stated),
            "markets": [_shortstring(market, "market") for market in self.markets],
        }


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
        return int(self.account, 16) != 0

    def to_message(self) -> dict[str, Any]:
        return {
            "account": _hex(self.account, "builder.account"),
            "maxFeeRate": _decimal(self.max_fee_rate, "builder.maxFeeRate", required=True),
            "expiresAt": _uint64(self.expires_at, "builder.expiresAt"),
        }


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
        message = self.to_message()
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
        environment: ``"mainnet"``, ``"testnet"`` or ``"nightly"`` (testnet and nightly share chain ids).
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
        if self.builder.is_set and self.builder.expires_at and self.builder.expires_at > self.expires_at:
            raise_value_error("builder.expiresAt must not outlive the session")
        if self.environment not in ENVIRONMENTS:
            raise_value_error(f"environment must be one of {sorted(ENVIRONMENTS)}, got {self.environment!r}")
        if not isinstance(self.label, str):
            raise_value_error("label must be a string")
        return {
            "paradexChain": _shortstring(self.paradex_chain, "paradexChain"),
            "environment": self.environment,
            "account": account,
            "sessionKey": _hex(self.session_key, "sessionKey"),
            "label": self.label,
            "scopes": scopes,
            # Builder grants come with every limit stated.
            "limits": self.limits.to_message(every_limit_stated=self.builder.is_set),
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
            "pubkeyX": self.pubkey_x,
            "pubkeyY": self.pubkey_y,
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

    def to_message(self, account: str) -> dict[str, Any]:
        if self.max_session_ttl <= 0 or self.max_session_ttl > SESSION_MAX_SECONDS:
            raise_value_error(f"ceiling.maxSessionTtl must be 1..{SESSION_MAX_SECONDS} seconds")
        if self.max_concurrent_sessions <= 0:
            raise_value_error("ceiling.maxConcurrentSessions must be positive")
        return {
            "scopes": _scopes(self.scopes),
            "limits": self.limits.to_message(),
            "subaccounts": _subaccounts(account, self.subaccounts),
            "includeFutureSubaccounts": bool(self.include_future_subaccounts),
            "maxSessionTtl": _uint64(self.max_session_ttl, "maxSessionTtl"),
            "maxConcurrentSessions": _uint64(self.max_concurrent_sessions, "maxConcurrentSessions"),
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
        if self.environment not in ENVIRONMENTS:
            raise_value_error(f"environment must be one of {sorted(ENVIRONMENTS)}, got {self.environment!r}")
        return {
            "paradexChain": _shortstring(self.paradex_chain, "paradexChain"),
            "environment": self.environment,
            "account": account,
            "passkey": self.passkey.to_message(),
            "ceiling": self.ceiling.to_message(account),
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
        if self.environment not in ENVIRONMENTS:
            raise_value_error(f"environment must be one of {sorted(ENVIRONMENTS)}, got {self.environment!r}")
        if not self.credential_id:
            raise_value_error("credentialId is required")
        return {
            "paradexChain": _shortstring(self.paradex_chain, "paradexChain"),
            "environment": self.environment,
            "account": account,
            "subaccounts": _subaccounts(account, self.subaccounts),
            "credentialId": self.credential_id,
            "sessionKey": _hex(self.session_key, "sessionKey"),
            "scopes": _scopes(self.scopes),
            "limits": self.limits.to_message(),
            "nonce": _nonce(self.nonce),
            "expiresAt": _uint64(self.expires_at, "expiresAt"),
        }
