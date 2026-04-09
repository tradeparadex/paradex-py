import base64
import secrets
from datetime import datetime, timedelta, timezone

from eth_account import Account
from eth_account.messages import encode_defunct
from eth_keys import keys as eth_keys
from starknet_py.common import int_from_hex
from starknet_py.hash.address import compute_address

from paradex_py.api.models import SystemConfig
from paradex_py.environment import Environment
from paradex_py.utils import raise_value_error

_SIWE_DOMAIN: dict[str, str] = {
    "prod": "app.paradex.trade",
    "testnet": "app.testnet.paradex.trade",
    "nightly": "app.nightly.paradex.trade",
}

_SIWE_AUTH_EXPIRY_SECONDS = 5 * 60  # 5 minutes, matching Paradex web app


class EvmAccount:
    """Paradex account authenticated via EVM key using SIWE (ERC-4361).

    The Starknet address is deterministically derived from the EVM address using
    Argent v0.5.0 direct deployment (no proxy). Trading requires a registered subkey.

    Args:
        config (SystemConfig): System configuration (must have paraclear_evm_account_hash).
        env (Environment): Environment (used to select the SIWE domain).
        evm_address (str): Ethereum address (checksummed or lowercase hex).
        evm_private_key (str): Ethereum private key (hex string with 0x prefix).

    Examples:
        >>> from paradex_py.account.evm_account import EvmAccount
        >>> account = EvmAccount(
        ...     config=config,
        ...     env="prod",
        ...     evm_address="0x...",
        ...     evm_private_key="0x...",
        ... )
        >>> hex(account.l2_address)
        '0x...'
    """

    def __init__(
        self,
        config: SystemConfig,
        env: Environment,
        evm_address: str,
        evm_private_key: str,
    ):
        if not config.paraclear_evm_account_hash:
            raise_value_error("EvmAccount: paraclear_evm_account_hash not available in system config")
        if not evm_address:
            raise_value_error("EvmAccount: EVM address is required")
        if not evm_private_key:
            raise_value_error("EvmAccount: EVM private key is required")

        self.config = config
        self.env = env

        # Normalise address to checksum format
        self._eth_account = Account.from_key(evm_private_key)
        self.l1_address = self._eth_account.address  # checksum address
        self.evm_address = self.l1_address

        # Uncompressed secp256k1 public key: "0x04" + 128-char hex (x || y)
        _priv_key_obj = eth_keys.PrivateKey(bytes(self._eth_account.key))
        self.evm_public_key_uncompressed = "0x04" + _priv_key_obj.public_key.to_bytes().hex()

        # Derive Starknet address — Argent v0.5.0 direct (no proxy)
        self.l2_address = self._compute_starknet_address()

    # ------------------------------------------------------------------
    # Starknet address derivation
    # ------------------------------------------------------------------

    def _compute_starknet_address(self) -> int:
        """Derive the Starknet address from the EVM address.

        Uses Argent v0.5.0 direct deployment with EIP-191 signer type:
          calldata = [3 (Eip191 variant), eth_address, 1 (Option::None guardian)]
          salt     = eth_address
          deployer = 0
        """
        # paraclear_evm_account_hash is guaranteed non-None by __init__ guard
        evm_class_hash: str = self.config.paraclear_evm_account_hash  # type: ignore[assignment]
        eth_addr_int = int_from_hex(self.evm_address)
        calldata = [3, eth_addr_int, 1]
        return compute_address(
            class_hash=int_from_hex(evm_class_hash),
            constructor_calldata=calldata,
            salt=eth_addr_int,
            deployer_address=0,
        )

    # ------------------------------------------------------------------
    # SIWE helpers
    # ------------------------------------------------------------------

    def _siwe_domain(self) -> str:
        return _SIWE_DOMAIN.get(str(self.env), "app.paradex.trade")

    def _build_siwe_onboarding(self) -> str:
        """Build ERC-4361 SIWE onboarding message (no expirationTime)."""
        domain = self._siwe_domain()
        nonce = secrets.token_hex(16)
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        return (
            f"{domain} wants you to sign in with your Ethereum account:\n"
            f"{self.evm_address}\n"
            "\n"
            "Paradex Onboarding\n"
            "\n"
            f"URI: https://{domain}\n"
            "Version: 1\n"
            f"Chain ID: {self.config.l1_chain_id}\n"
            f"Nonce: {nonce}\n"
            f"Issued At: {now}"
        )

    def _build_siwe_auth(self) -> str:
        """Build ERC-4361 SIWE auth message (with expirationTime)."""
        domain = self._siwe_domain()
        nonce = secrets.token_hex(16)
        now = datetime.now(timezone.utc)
        expiry = now + timedelta(seconds=_SIWE_AUTH_EXPIRY_SECONDS)
        now_str = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        expiry_str = expiry.strftime("%Y-%m-%dT%H:%M:%SZ")
        return (
            f"{domain} wants you to sign in with your Ethereum account:\n"
            f"{self.evm_address}\n"
            "\n"
            "Paradex Auth\n"
            "\n"
            f"URI: https://{domain}\n"
            "Version: 1\n"
            f"Chain ID: {self.config.l1_chain_id}\n"
            f"Nonce: {nonce}\n"
            f"Issued At: {now_str}\n"
            f"Expiration Time: {expiry_str}"
        )

    def _sign_eip191(self, message: str) -> str:
        """Sign a plaintext message with EIP-191 personal_sign."""
        msg = encode_defunct(text=message)
        signed = self._eth_account.sign_message(msg)
        sig_hex = signed.signature.hex()
        return sig_hex if sig_hex.startswith("0x") else "0x" + sig_hex

    # ------------------------------------------------------------------
    # Auth header builders (same interface as ParadexAccount)
    # ------------------------------------------------------------------

    def onboarding_headers(self) -> dict:
        siwe = self._build_siwe_onboarding()
        return {
            "PARADEX-STARKNET-ACCOUNT": hex(self.l2_address),
            "PARADEX-EVM-SIGNATURE": self._sign_eip191(siwe),
            "PARADEX-SIWE-MESSAGE": base64.b64encode(siwe.encode()).decode(),
        }

    def auth_headers(self) -> dict:
        siwe = self._build_siwe_auth()
        return {
            "PARADEX-STARKNET-ACCOUNT": hex(self.l2_address),
            "PARADEX-EVM-SIGNATURE": self._sign_eip191(siwe),
            "PARADEX-SIWE-MESSAGE": base64.b64encode(siwe.encode()).decode(),
        }

    def set_jwt_token(self, jwt_token: str) -> None:
        self.jwt_token = jwt_token
