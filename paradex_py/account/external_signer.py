"""Accounts whose Starknet key is held outside this process."""

import base64
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Protocol

from starknet_py.common import int_from_bytes, int_from_hex
from starknet_py.net.models.typed_data import TypedDataDict

from paradex_py.account.account import ParadexAccount
from paradex_py.account.utils import typed_data_to_message_hash
from paradex_py.api.models import SystemConfig
from paradex_py.utils import raise_value_error


@dataclass(frozen=True)
class ExternalSignature:
    """What goes where the "[r,s]" signature string would, and headers for the same request.

    Args:
        signature (str): value placed in the request wherever the signature goes
        headers (dict[str, str]): headers the request carrying `signature` must send
    """

    signature: str
    headers: dict[str, str] = field(default_factory=dict)


class ExternalSigner(Protocol):
    """Signs Starknet typed-data message hashes with a key this process never sees."""

    def sign_hash(self, message_hash: int) -> ExternalSignature:
        """Sign a Starknet typed-data message hash.

        Args:
            message_hash (int): typed-data message hash for the account's address

        Returns:
            ExternalSignature: the signature and any headers its request must carry
        """
        ...


class HeaderSigner:
    """Signer for a signing proxy that sits between this client and Paradex.

    Each request carries the 32-byte message hash, base64-encoded, in `header`, and
    `signature` wherever the "[r,s]" string goes. The proxy signs the hash and
    replaces `signature` with the real one before forwarding the request.

    Args:
        header (str): name of the header that carries the message hash
        signature (str): stand-in the proxy replaces with the real signature

    Examples:
        >>> signer = HeaderSigner(header="X-Sign-Hash", signature="PROXY_SIGNATURE")
    """

    def __init__(self, header: str, signature: str):
        if not header or not signature:
            raise_value_error("HeaderSigner: header and signature are required")
        self.header = header
        self.signature = signature

    def sign_hash(self, message_hash: int) -> ExternalSignature:
        """Return the stand-in signature and the hash header for one request.

        Args:
            message_hash (int): typed-data message hash for the account's address

        Returns:
            ExternalSignature: the stand-in signature and the header carrying the hash
        """
        payload = base64.b64encode(message_hash.to_bytes(32, "big")).decode()
        return ExternalSignature(signature=self.signature, headers={self.header: payload})


class ExternalSignerAccount(ParadexAccount):
    """An L2 account that signs through an `ExternalSigner` and holds no private key.

    Like a subkey account it is for API use only: no onboarding and no on-chain operations.
    It signs REST requests only, because a WebSocket order has no headers to carry the
    signer's. Each request carries one signature, so a request needing several is refused.
    Not safe to share across threads concurrently: signing and sending a request must not
    interleave with another.

    Args:
        config (SystemConfig): SystemConfig
        l2_address (str): L2 address of the account
        l2_public_key (str): public key of the key the signer holds
        signer (ExternalSigner): produces the signature for each message hash

    Examples:
        >>> from paradex_py.account import ExternalSignerAccount, HeaderSigner
        >>> account = ExternalSignerAccount(
        ...     config=config,
        ...     l2_address="0x...",
        ...     l2_public_key="0x...",
        ...     signer=HeaderSigner(header="X-Sign-Hash", signature="PROXY_SIGNATURE"),
        ... )
    """

    def __init__(self, config: SystemConfig, l2_address: str, l2_public_key: str, signer: ExternalSigner):
        if not l2_address or not l2_public_key:
            raise_value_error("ExternalSignerAccount: L2 address and public key are required")
        self.config = config
        self.l1_address = ""
        self.l2_address = int_from_hex(l2_address)
        self.l2_public_key = int_from_hex(l2_public_key)
        self.l2_chain_id = int_from_bytes(config.starknet_chain_id.encode())
        self.is_onboarded: bool | None = True
        self.signer = signer
        self._request_headers: dict[str, str] = {}

    def _sign_typed_data(self, typed_data: TypedDataDict) -> str:
        if self._request_headers:
            # Clearing first means a refused request never blocks the next one.
            self._request_headers = {}
            raise_value_error(
                "ExternalSignerAccount: a request carries one signature, and an earlier one was never sent."
                " Both are discarded; sign again."
            )
        result = self.signer.sign_hash(typed_data_to_message_hash(typed_data, self.l2_address))
        self._request_headers = dict(result.headers)
        return result.signature

    def take_request_headers(self) -> dict[str, str]:
        headers, self._request_headers = self._request_headers, {}
        return headers

    def auth_headers(self) -> dict:
        # Auth signs and sends in one step, so it leaves another request's pending headers alone.
        pending, self._request_headers = self._request_headers, {}
        try:
            headers = super().auth_headers()
            return {**self.take_request_headers(), **headers}
        finally:
            self._request_headers = pending

    def onboarding_headers(self) -> dict:
        """No onboarding: the account must already exist."""
        return {}

    def transfer_on_l2(self, target_l2_address: str, amount_decimal: Decimal):
        """No on-chain operations: the account holds no key to send a transaction."""
        raise_value_error("ExternalSignerAccount: On-chain operations not supported")
