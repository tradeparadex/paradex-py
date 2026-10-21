"""Sign-In with Ethereum (EIP-4361) messages, signed with an Ethereum key via EIP-191."""

import base64
import secrets
from datetime import datetime, timedelta, timezone

from eth_utils.address import to_checksum_address

# The domain each environment's SIWE messages name; the server accepts only these.
SIWE_DOMAIN: dict[str, str] = {
    "prod": "app.paradex.trade",
    "testnet": "app.testnet.paradex.trade",
    "nightly": "app.nightly.paradex.trade",
}

# How long a signed message stays valid, matching the Paradex web app. The server
# accepts at most 5 minutes between Issued At and Expiration Time.
SIWE_EXPIRY_SECONDS = 5 * 60

SIWE_ONBOARDING_STATEMENT = "Paradex Onboarding"
SIWE_AUTH_STATEMENT = "Paradex Auth"


def siwe_domain(env: str) -> str:
    """The SIWE domain for an environment, defaulting to production's."""
    return SIWE_DOMAIN.get(str(env), SIWE_DOMAIN["prod"])


def _siwe_time(t: datetime) -> str:
    return t.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_siwe_message(
    domain: str,
    address: str,
    statement: str,
    chain_id: int | str,
    issued_at: datetime,
    expiration_time: datetime | None = None,
    nonce: str | None = None,
) -> str:
    """Build an EIP-4361 message.

    Args:
        domain (str): domain the message is for, also used for the URI
        address (str): Ethereum address that signs, EIP-55 checksummed
        statement (str): statement line the wallet shows the signer
        chain_id (int | str): Ethereum chain id
        issued_at (datetime): Issued At, timezone aware
        expiration_time (datetime, optional): Expiration Time. Omitted when None.
        nonce (str, optional): Nonce. A random 32-character hex string when None.

    Returns:
        str: the message to sign
    """
    lines = [
        f"{domain} wants you to sign in with your Ethereum account:",
        address,
        "",
        statement,
        "",
        f"URI: https://{domain}",
        "Version: 1",
        f"Chain ID: {chain_id}",
        f"Nonce: {nonce if nonce is not None else secrets.token_hex(16)}",
        f"Issued At: {_siwe_time(issued_at)}",
    ]
    if expiration_time is not None:
        lines.append(f"Expiration Time: {_siwe_time(expiration_time)}")
    return "\n".join(lines)


def encode_siwe_message(message: str) -> str:
    """Base64-encode a SIWE message for a request header."""
    return base64.b64encode(message.encode()).decode()


def build_parent_link_statement(account: int, starknet_chain_id: str) -> str:
    """The statement an Ethereum wallet signs to prove it is the parent of a Paradex account.

    Args:
        account (int): Paradex account address. It is written in lowercase hex with
            the 0x prefix and no leading zeros.
        starknet_chain_id (str): ``starknet_chain_id`` from the system config, verbatim

    Returns:
        str: the statement the server expects, byte for byte
    """
    return f"Link this wallet as the parent of Paradex account {hex(account)} on {starknet_chain_id}"


def build_parent_link_message(
    domain: str,
    wallet: str,
    account: int,
    starknet_chain_id: str,
    l1_chain_id: int | str,
    now: datetime | None = None,
    nonce: str | None = None,
) -> str:
    """Build the SIWE message that links an Ethereum wallet as a Paradex account's parent.

    Sent on ``POST /v1/onboarding`` when a new account is created. The message is valid
    for ``SIWE_EXPIRY_SECONDS`` from ``now``.

    Args:
        domain (str): SIWE domain of the environment (see ``siwe_domain``)
        wallet (str): parent Ethereum address, in any case
        account (int): Paradex account address
        starknet_chain_id (str): ``starknet_chain_id`` from the system config
        l1_chain_id (int | str): Ethereum chain id from the system config
        now (datetime, optional): Issued At. The current time when None.
        nonce (str, optional): Nonce. Random when None.

    Returns:
        str: the message to sign
    """
    issued_at = now if now is not None else datetime.now(timezone.utc)
    return build_siwe_message(
        domain=domain,
        address=to_checksum_address(wallet),
        statement=build_parent_link_statement(account, starknet_chain_id),
        chain_id=l1_chain_id,
        issued_at=issued_at,
        expiration_time=issued_at + timedelta(seconds=SIWE_EXPIRY_SECONDS),
        nonce=nonce,
    )
