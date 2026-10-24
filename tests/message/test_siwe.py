import base64
import re
from datetime import datetime, timedelta, timezone

import pytest

from paradex_py.message.siwe import (
    SIWE_DOMAIN,
    build_parent_link_message,
    build_parent_link_statement,
    build_siwe_message,
    encode_siwe_message,
    siwe_domain,
)

WALLET = "0xd2c7314539dCe7752c8120af4eC2AA750Cf2035e"
ISSUED_AT = datetime(2026, 10, 22, 12, 0, 0, tzinfo=timezone.utc)


@pytest.mark.parametrize(
    "account, expected",
    [
        (
            0x129C135ED63DF9353885E292BE4426B8ED6122B13C6C0E1BB787288A1F5ADFA,
            "0x129c135ed63df9353885e292be4426b8ed6122b13c6c0e1bb787288a1f5adfa",
        ),
        (int("0x0000000AbC", 16), "0xabc"),
        (0, "0x0"),
    ],
)
def test_parent_link_statement_writes_the_account_in_canonical_hex(account, expected):
    assert (
        build_parent_link_statement(account, "PRIVATE_SN_POTC_SEPOLIA")
        == f"Link this wallet as the parent of Paradex account {expected} on PRIVATE_SN_POTC_SEPOLIA"
    )


def test_parent_link_statement_keeps_the_chain_id_verbatim():
    assert build_parent_link_statement(0xABC, "PRIVATE_SN_PARACLEAR_MAINNET").endswith(
        " on PRIVATE_SN_PARACLEAR_MAINNET"
    )


def test_parent_link_message_is_exact():
    message = build_parent_link_message(
        domain="app.testnet.paradex.trade",
        wallet=WALLET.lower(),
        account=int("0x0129c135ed63df9353885e292be4426b8ed6122b13c6c0e1bb787288a1f5adfa", 16),
        starknet_chain_id="PRIVATE_SN_POTC_SEPOLIA",
        l1_chain_id="11155111",
        now=ISSUED_AT,
        nonce="0123456789abcdef0123456789abcdef",
    )

    assert message == (
        "app.testnet.paradex.trade wants you to sign in with your Ethereum account:\n"
        "0xd2c7314539dCe7752c8120af4eC2AA750Cf2035e\n"
        "\n"
        "Link this wallet as the parent of Paradex account"
        " 0x129c135ed63df9353885e292be4426b8ed6122b13c6c0e1bb787288a1f5adfa on PRIVATE_SN_POTC_SEPOLIA\n"
        "\n"
        "URI: https://app.testnet.paradex.trade\n"
        "Version: 1\n"
        "Chain ID: 11155111\n"
        "Nonce: 0123456789abcdef0123456789abcdef\n"
        "Issued At: 2026-10-22T12:00:00Z\n"
        "Expiration Time: 2026-10-22T12:05:00Z"
    )


def _field(message: str, pattern: str) -> str:
    match = re.search(pattern, message, re.M)
    assert match is not None, pattern
    return match.group(1)


def _time_field(message: str, name: str) -> datetime:
    value = _field(message, rf"^{name}: (.+)$")
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def test_parent_link_message_defaults_to_now_and_a_random_nonce():
    before = datetime.now(timezone.utc).replace(microsecond=0)
    first = build_parent_link_message("app.paradex.trade", WALLET, 0xABC, "PRIVATE_SN_PARACLEAR_MAINNET", 1)
    second = build_parent_link_message("app.paradex.trade", WALLET, 0xABC, "PRIVATE_SN_PARACLEAR_MAINNET", 1)

    nonce = r"^Nonce: ([0-9a-f]{32})$"
    assert _field(first, nonce) != _field(second, nonce)

    issued_at = _time_field(first, "Issued At")
    expiration = _time_field(first, "Expiration Time")
    assert before <= issued_at <= datetime.now(timezone.utc)
    assert expiration - issued_at == timedelta(minutes=5)


def test_siwe_message_without_expiration_omits_the_line():
    message = build_siwe_message(
        domain="app.paradex.trade",
        address=WALLET,
        statement="Paradex Onboarding",
        chain_id=1,
        issued_at=ISSUED_AT,
        nonce="n" * 16,
    )

    assert message.endswith("Issued At: 2026-10-22T12:00:00Z")
    assert "Expiration Time" not in message


def test_siwe_message_writes_times_in_utc():
    message = build_siwe_message(
        domain="app.paradex.trade",
        address=WALLET,
        statement="Paradex Auth",
        chain_id=1,
        issued_at=ISSUED_AT.astimezone(timezone(timedelta(hours=-5))),
        nonce="n" * 16,
    )

    assert "Issued At: 2026-10-22T12:00:00Z" in message


def test_encode_siwe_message_is_standard_base64():
    message = "app.paradex.trade wants you to sign in with your Ethereum account:\nLink ≥ 1"

    encoded = encode_siwe_message(message)

    assert base64.b64decode(encoded, validate=True).decode() == message


@pytest.mark.parametrize("env", ["prod", "testnet", "nightly"])
def test_siwe_domain_per_environment(env):
    assert siwe_domain(env) == SIWE_DOMAIN[env]


def test_siwe_domain_defaults_to_prod():
    assert siwe_domain("unknown") == "app.paradex.trade"
