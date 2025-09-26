from decimal import Decimal

from starknet_py.common import int_from_bytes, int_from_hex
from starknet_py.net.full_node_client import FullNodeClient
from starknet_py.net.signer.stark_curve_signer import KeyPair

from paradex_py.account.account import CustomStarknetChainId, ParadexAccount
from paradex_py.account.starknet import Account as StarknetAccount
from paradex_py.api.models import SystemConfig
from paradex_py.utils import raise_value_error


class SubkeyAccount(ParadexAccount):
    """Subkey account for L2-only API authentication (no on-chain operations).

    This account type is designed for subkey usage where only L2 credentials
    are available and no L1 onboarding is required.

    Args:
        config (SystemConfig): SystemConfig
        l2_private_key (str): L2 private key (required)
        l2_address (str): L2 address of the main account (required)

    Examples:
        >>> from paradex_py.account.subkey_account import SubkeyAccount
        >>> from paradex_py.environment import Environment
        >>> account = SubkeyAccount(
        ...     config=config,
        ...     l2_private_key="0x...",
        ...     l2_address="0x..."
        ... )
    """

    def __init__(
        self,
        config: SystemConfig,
        l2_private_key: str,
        l2_address: str,
    ):
        # Validate required parameters
        if not l2_private_key:
            raise_value_error("SubkeyAccount: L2 private key is required")
        if not l2_address:
            raise_value_error("SubkeyAccount: L2 address is required")

        # Set config
        self.config = config

        # No L1 address for subkeys
        self.l1_address = ""

        # Set L2 credentials
        self.l2_private_key = int_from_hex(l2_private_key)
        self.l2_address = int_from_hex(l2_address)

        # Generate public key from private key
        key_pair = KeyPair.from_private_key(self.l2_private_key)
        self.l2_public_key = key_pair.public_key

        # Create Starknet account for message signing only
        self._setup_starknet_account()

    def _setup_starknet_account(self):
        """Set up the Starknet account for message signing only."""
        # Create Starknet client and account
        client = FullNodeClient(node_url=self.config.starknet_fullnode_rpc_url)
        self.l2_chain_id = int_from_bytes(self.config.starknet_chain_id.encode())

        self.starknet = StarknetAccount(
            client=client,
            address=self.l2_address,
            key_pair=KeyPair.from_private_key(self.l2_private_key),
            chain=CustomStarknetChainId(self.l2_chain_id),
        )

        # Apply the same monkey patch as ParadexAccount
        self._apply_fullnode_headers_patch(client)

    def onboarding_headers(self) -> dict:
        """Override to prevent onboarding for subkeys."""
        return {}

    def transfer_on_l2(self, target_l2_address: str, amount_decimal: Decimal):
        """Override to prevent on-chain operations for subkeys."""
        raise_value_error("SubkeyAccount: On-chain operations not supported for subkeys")
