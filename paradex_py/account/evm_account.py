import types
from datetime import datetime, timedelta, timezone

from eth_account import Account
from eth_keys.datatypes import PrivateKey
from httpx import AsyncClient
from starknet_py.common import int_from_bytes, int_from_hex
from starknet_py.net.full_node_client import FullNodeClient
from starknet_py.net.http_client import HttpMethod

from paradex_py.account.account import CustomStarknetChainId
from paradex_py.account.eip191_signer import Eip191Signer
from paradex_py.account.starknet import Account as StarknetAccount
from paradex_py.account.utils import derive_l2_address_eip191, sign_eip191_message
from paradex_py.api.models import SystemConfig
from paradex_py.environment import Environment
from paradex_py.message.siwe import (
    SIWE_AUTH_STATEMENT,
    SIWE_EXPIRY_SECONDS,
    SIWE_ONBOARDING_STATEMENT,
    build_siwe_message,
    encode_siwe_message,
    siwe_domain,
)
from paradex_py.utils import raise_value_error


class EvmAccount:
    """Paradex account authenticated via EVM key using SIWE (ERC-4361).

    The Starknet address is deterministically derived from the EVM address using
    Argent v0.5.0 direct deployment (no proxy). Trading requires a registered subkey.

    Args:
        config (SystemConfig): System configuration (must have paraclear_evm_account_hash).
        env (Environment): Environment (used to select the SIWE domain).
        evm_address (str): Ethereum address (checksummed or lowercase hex).
        evm_private_key (str): Ethereum private key (hex string with 0x prefix).
        l2_address (str, optional): Pre-resolved L2 address; derived from the EVM
            address when omitted.
        is_onboarded (bool, optional): Cached onboarding state; ``True`` skips the
            auto-onboarding path.
        is_vault_operator (bool, optional): The session targets an EVM vault
            operator sub-account (requires ``l2_address``). Operators are onboarded
            by vault creation — ``onboarding_headers()`` raises for them.

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
        l2_address: str | None = None,
        is_onboarded: bool | None = None,
        rpc_version: str | None = None,
        is_vault_operator: bool = False,
    ):
        if not evm_address:
            raise_value_error("EvmAccount: EVM address is required")
        if not evm_private_key:
            raise_value_error("EvmAccount: EVM private key is required")
        if is_vault_operator and l2_address is None:
            raise_value_error("EvmAccount: a vault operator account requires a pre-resolved l2_address")

        self.config = config
        self.env = env
        self._evm_private_key = evm_private_key
        self._rpc_version = rpc_version

        # Normalise address to checksum format
        self._eth_account = Account.from_key(evm_private_key)
        self.l1_address = self._eth_account.address  # checksum address
        self.evm_address = self.l1_address

        # Uncompressed secp256k1 public key: "0x04" + 128-char hex (x || y)
        _priv_key_obj = PrivateKey(bytes(self._eth_account.key))
        self.evm_public_key_uncompressed = "0x04" + _priv_key_obj.public_key.to_bytes().hex()

        if l2_address is not None:
            self.l2_address = int_from_hex(l2_address)
        else:
            # Backwards-compat fallback: callers that construct EvmAccount directly
            # (without going through the ParadexEvm orchestrator) still get their
            # address derived for them. The orchestrator always resolves the address
            # outside via the same helper, so this branch is only hit for direct
            # construction and is intended for eventual removal.
            self.l2_address = derive_l2_address_eip191(config, self.evm_address)
        self.is_onboarded = is_onboarded
        self.is_vault_operator = is_vault_operator

        # StarkNet account backed by an EIP-191 signer, so on-chain operations
        # (deposit / withdraw / transfer / guardian) can be signed with the
        # Ethereum key. The account contract validates the resulting
        # SignerSignature via secp256k1/EIP-191 on-chain.
        self.l2_chain_id = int_from_bytes(config.starknet_chain_id.encode())
        self.jwt_token: str | None = None
        self.starknet = self._build_starknet_account()
        self._apply_fullnode_jwt_patch(self.starknet.client)

    def _apply_fullnode_jwt_patch(self, client) -> None:
        """Attach the account's JWT to fullnode RPC requests.

        An EVM account authenticates with the ``Authorization: Bearer <jwt>``
        token obtained during SIWE auth and sends it on each RPC call.
        """
        current_self = self

        # Skip starknet_py's RPC spec-version probe (it only emits a warning on
        # mismatch); the endpoint may report a newer spec than the pinned
        # EXPECTED_RPC_VERSION.
        client._client._is_spec_version_verified = True

        async def jwt_make_request(
            self,
            session: AsyncClient,
            address: str,
            http_method: HttpMethod,
            params: dict,
            payload: dict,
        ) -> dict:
            headers = {"Content-Type": "application/json"}
            if current_self.jwt_token:
                headers["Authorization"] = f"Bearer {current_self.jwt_token}"
            response = await session.request(
                method=http_method.value, url=address, params=params, json=payload, headers=headers
            )
            await self.handle_request_error(response)
            return await response.json()

        client._client._make_request = types.MethodType(jwt_make_request, client._client)

    def _build_starknet_account(self) -> StarknetAccount:
        if self._rpc_version:
            node_url = f"{self.config.starknet_fullnode_rpc_base_url}/rpc/{self._rpc_version}"
        else:
            node_url = self.config.starknet_fullnode_rpc_url
        client = FullNodeClient(node_url=node_url)
        chain = CustomStarknetChainId(self.l2_chain_id)
        signer = Eip191Signer(self._evm_private_key, int(chain))
        return StarknetAccount(
            client=client,
            address=self.l2_address,
            signer=signer,
            chain=chain,  # ty: ignore[invalid-argument-type]
        )

    # ------------------------------------------------------------------
    # SIWE helpers
    # ------------------------------------------------------------------

    def _siwe_domain(self) -> str:
        return siwe_domain(self.env)

    def _build_siwe_onboarding(self) -> str:
        """Build ERC-4361 SIWE onboarding message (no expirationTime)."""
        return build_siwe_message(
            domain=self._siwe_domain(),
            address=self.evm_address,
            statement=SIWE_ONBOARDING_STATEMENT,
            chain_id=self.config.l1_chain_id,
            issued_at=datetime.now(timezone.utc),
        )

    def _build_siwe_auth(self) -> str:
        """Build ERC-4361 SIWE auth message (with expirationTime)."""
        now = datetime.now(timezone.utc)
        return build_siwe_message(
            domain=self._siwe_domain(),
            address=self.evm_address,
            statement=SIWE_AUTH_STATEMENT,
            chain_id=self.config.l1_chain_id,
            issued_at=now,
            expiration_time=now + timedelta(seconds=SIWE_EXPIRY_SECONDS),
        )

    def _sign_eip191(self, message: str) -> str:
        """Sign a plaintext message with EIP-191 personal_sign."""
        return sign_eip191_message(message, self._eth_account.key)

    # ------------------------------------------------------------------
    # Auth header builders (same interface as ParadexAccount)
    # ------------------------------------------------------------------

    def onboarding_headers(self) -> dict:
        if self.is_vault_operator:
            raise_value_error(
                "EvmAccount: vault operator accounts are onboarded by vault creation "
                "(POST /vaults with operator_signer_type=eip191); they cannot be "
                "onboarded via POST /v2/onboarding. If auth failed with NOT_ONBOARDED, "
                "the operator does not exist yet — create the vault first."
            )
        siwe = self._build_siwe_onboarding()
        return {
            "PARADEX-STARKNET-ACCOUNT": hex(self.l2_address),
            "PARADEX-EVM-SIGNATURE": self._sign_eip191(siwe),
            "PARADEX-SIWE-MESSAGE": encode_siwe_message(siwe),
        }

    def auth_headers(self) -> dict:
        siwe = self._build_siwe_auth()
        return {
            "PARADEX-STARKNET-ACCOUNT": hex(self.l2_address),
            "PARADEX-EVM-SIGNATURE": self._sign_eip191(siwe),
            "PARADEX-SIWE-MESSAGE": encode_siwe_message(siwe),
        }

    def set_jwt_token(self, jwt_token: str) -> None:
        self.jwt_token = jwt_token
