"""Claim airdrop tokens from a treasury contract on Paradex.

Usage:
    export L1_ADDRESS="0x..."
    export L2_PRIVATE_KEY="0x..."
    export L2_ADDRESS="0x..."
    export TREASURY_CONTRACT_ADDRESS="0x..."
    python examples/claim_dime_airdrop.py

Environment variables:
    L1_ADDRESS                  Ethereum L1 address
    L2_PRIVATE_KEY              Paradex L2 private key (hex)
    L2_ADDRESS                  Expected L2 account address (hex, for verification)
    TREASURY_CONTRACT_ADDRESS   Address of the treasury contract holding tokens
    DRY_RUN                     Set to "false" to execute (default: true)
    LOG_FILE                    Set to "true" to log to file (default: false)
"""

import asyncio
import os

from starknet_py.common import int_from_hex
from starknet_py.hash.selector import get_selector_from_name

from paradex_py import Paradex
from paradex_py.environment import PROD

L1_ADDRESS = os.getenv("L1_ADDRESS", "")
if not L1_ADDRESS:
    raise SystemExit("Error: L1_ADDRESS environment variable is required")

L2_PRIVATE_KEY = os.getenv("L2_PRIVATE_KEY", "")
if not L2_PRIVATE_KEY:
    raise SystemExit("Error: L2_PRIVATE_KEY environment variable is required")

L2_ADDRESS = os.getenv("L2_ADDRESS", "")
if not L2_ADDRESS:
    raise SystemExit("Error: L2_ADDRESS environment variable is required")

AIRDROP_TOKEN = os.getenv("AIRDROP_TOKEN", "DIME")
if not AIRDROP_TOKEN:
    raise SystemExit("Error: AIRDROP_TOKEN environment variable is required")

TREASURY_CONTRACT_ADDRESS = os.getenv("TREASURY_CONTRACT_ADDRESS", "")
if not TREASURY_CONTRACT_ADDRESS:
    raise SystemExit("Error: TREASURY_CONTRACT_ADDRESS environment variable is required")
TREASURY_CONTRACT_ADDRESS = int_from_hex(TREASURY_CONTRACT_ADDRESS)

DRY_RUN = os.getenv("DRY_RUN", "TRUE").lower() == "true"
LOG_FILE = os.getenv("LOG_FILE", "FALSE").lower() == "true"

if LOG_FILE:
    from paradex_py.common.file_logging import file_logger

    logger = file_logger
else:
    from paradex_py.common.console_logging import console_logger

    logger = console_logger


async def main():
    paradex = Paradex(
        env=PROD,
        l1_address=L1_ADDRESS,
        l2_private_key=L2_PRIVATE_KEY,
    )

    # Validate that L2_ADDRESS derived from L1 address and L2 private key
    # matches the expected L2_ADDRESS from the environment variable
    if hex(paradex.account.l2_address) != hex(int(L2_ADDRESS, 16)):
        raise SystemExit(
            "Error: L2_ADDRESS does not match the account address derived from L1 address and L2 private key"
        )
    print(f"\nParadex account to claim: {hex(paradex.account.l2_address)}")

    # Find token address from bridged tokens in system config and initialize the token contract
    token = next(
        (t for t in paradex.config.bridged_tokens if t.symbol == AIRDROP_TOKEN),
        None,
    )
    if token is None:
        available = [t.symbol for t in paradex.config.bridged_tokens]
        raise SystemExit(f"Error: Token '{AIRDROP_TOKEN}' not found. Available: {available}")
    token_address = int_from_hex(token.l2_token_address)
    print(f"Contract address of the token to be claimed ({AIRDROP_TOKEN}): ", hex(token_address))

    token_contract = await paradex.account.starknet.load_contract(token_address, is_cairo0_contract=False)
    if "transfer_from" not in token_contract.functions:
        raise SystemExit(f"Token contract {hex(token_address)} does not have the transfer_from function")
    if "increase_allowance" not in token_contract.functions:
        raise SystemExit(f"Token contract {hex(token_address)} does not have the increase_allowance function")

    # Initialize Paradex Protocol contract (Paraclear)
    paraclear_contract = await paradex.account.starknet.load_contract(
        int_from_hex(paradex.config.paraclear_address), is_cairo0_contract=False
    )
    if "deposit" not in paraclear_contract.functions:
        raise SystemExit(
            f"Paraclear contract {hex(int_from_hex(paradex.config.paraclear_address))} does not have the deposit"
            " function"
        )

    # Fetch token decimals and allowance
    token_decimals = await token_contract.functions["decimals"].call()
    token_decimals = token_decimals[0]

    print(f"Token decimals: {token_decimals}")

    print(f"Fetching allowance from treasury contract {hex(TREASURY_CONTRACT_ADDRESS)}")
    token_allowance = await token_contract.functions["allowance"].call(
        owner=TREASURY_CONTRACT_ADDRESS,
        spender=paradex.account.l2_address,
    )
    token_allowance = token_allowance[0]
    if token_allowance == 0:
        raise SystemExit(f"You have no {AIRDROP_TOKEN} to be claimed")

    token_allowance_in_tokens = token_allowance / 10**token_decimals
    print(f"You are granted to claim {token_allowance_in_tokens} {AIRDROP_TOKEN} tokens")

    paraclear_decimals = paradex.config.paraclear_decimals
    token_amount_paraclear = int(token_allowance * 10**paraclear_decimals / 10**token_decimals)
    print(f"Paradex protocol contract address: {hex(int_from_hex(paradex.config.paraclear_address))}")

    # Prepare the multicall transaction
    calls = [
        token_contract.functions["transfer_from"].prepare_invoke_v3(
            sender=TREASURY_CONTRACT_ADDRESS,
            recipient=paradex.account.l2_address,
            amount=token_allowance,
        ),
        token_contract.functions["increase_allowance"].prepare_invoke_v3(
            spender=paraclear_contract.address,
            added_value=token_allowance,
        ),
        paraclear_contract.functions["deposit"].prepare_invoke_v3(
            token_address=token_address,
            amount=token_amount_paraclear,
        ),
    ]

    if DRY_RUN:
        transfer_from_selector = get_selector_from_name("transfer_from")
        increase_allowance_selector = get_selector_from_name("increase_allowance")
        deposit_selector = get_selector_from_name("deposit")
        print("\n***DRY RUN MODE ***] Skipping transaction execution")
        print(f"By executing this script you will claim {token_allowance_in_tokens} {AIRDROP_TOKEN} tokens")
        print("\nYou will execute the following calls:")

        if len(calls) != 3:
            print(f"\n!!! UNEXPECTED NUMBER OF CALLS: {len(calls)} (expected 3) !!!")
        # Transfer from treasury contract to your L2 account
        print("\n1. Transfer from treasury contract to your L2 account")
        if calls[0].to_addr == token_address:
            print(f"   Contract: {hex(calls[0].to_addr)} [TOKEN CONTRACT]")
        else:
            print(f"   Contract: {hex(calls[0].to_addr)} !!! UNEXPECTED CONTRACT !!!")
        if calls[0].selector == transfer_from_selector:
            print(f"   Selector: {hex(transfer_from_selector)} [TRANSFER FROM]")
        else:
            print(f"   Selector: {calls[0].selector} !!! UNEXPECTED SELECTOR !!!")
        if len(calls[0].calldata) != 4:
            print(f"   Parameters: {calls[0].calldata} !!! UNEXPECTED PARAMETERS (expected 4) !!!")
        else:
            print("   Parameters:")
            sender = calls[0].calldata[0]
            recipient = calls[0].calldata[1]
            if sender == TREASURY_CONTRACT_ADDRESS:
                print(f"     0: {hex(sender)} [SENDER - TREASURY]")
            else:
                print(f"     0: {hex(sender)} !!! UNEXPECTED SENDER !!!")
            if recipient == paradex.account.l2_address:
                print(f"     1: {hex(recipient)} [RECIPIENT - YOUR L2]")
            else:
                print(f"     1: {hex(recipient)} !!! UNEXPECTED RECIPIENT !!!")
            print(f"     2: {calls[0].calldata[2] / 10**token_decimals} [AMOUNT low]")
            print(f"     3: {calls[0].calldata[3] / 10**token_decimals} [AMOUNT high]")

        # Increase allowance to the Paradex protocol contract
        print("\n2. Increase allowance to the Paradex protocol contract")
        if calls[1].to_addr == token_address:
            print(f"   Contract: {hex(calls[1].to_addr)} [TOKEN CONTRACT]")
        else:
            print(f"   Contract: {hex(calls[1].to_addr)} !!! UNEXPECTED CONTRACT !!!")
        if calls[1].selector == increase_allowance_selector:
            print(f"   Selector: {hex(increase_allowance_selector)} [INCREASE ALLOWANCE]")
        else:
            print(f"   Selector: {calls[1].selector} !!! UNEXPECTED SELECTOR !!!")
        if len(calls[1].calldata) != 3:
            print(f"   Parameters: {calls[1].calldata} !!! UNEXPECTED PARAMETERS (expected 3) !!!")
        else:
            print("   Parameters:")
            spender = calls[1].calldata[0]
            if spender == paraclear_contract.address:
                print(f"     0: {hex(spender)} [SPENDER - PARACLEAR]")
            else:
                print(f"     0: {hex(spender)} !!! UNEXPECTED SPENDER !!!")
            print(f"     1: {calls[1].calldata[1] / 10**token_decimals} [ADDED VALUE low]")
            print(f"     2: {calls[1].calldata[2] / 10**token_decimals} [ADDED VALUE high]")

        # Deposit tokens to the Paradex protocol contract
        print(f"\n3. Deposit {AIRDROP_TOKEN} tokens to the Paradex protocol contract")
        paraclear_address = int_from_hex(paradex.config.paraclear_address)
        if calls[2].to_addr == paraclear_address:
            print(f"   Contract: {hex(calls[2].to_addr)} [PARACLEAR]")
        else:
            print(f"   Contract: {hex(calls[2].to_addr)} !!! UNEXPECTED CONTRACT !!!")
        if calls[2].selector == deposit_selector:
            print(f"   Selector: {hex(deposit_selector)} [DEPOSIT]")
        else:
            print(f"   Selector: {calls[2].selector} !!! UNEXPECTED SELECTOR !!!")
        if len(calls[2].calldata) != 2:
            print(f"   Parameters: {calls[2].calldata} !!! UNEXPECTED PARAMETERS (expected 2) !!!")
        else:
            print("   Parameters:")
            print(f"     0: {hex(calls[2].calldata[0])} [TOKEN ADDRESS]")
            print(f"     1: {calls[2].calldata[1] / 10**paraclear_decimals} [AMOUNT]")

        # Final amount validation
        print("\n--- Final Validation ---")
        transfer_from_amount = (calls[0].calldata[2] + (calls[0].calldata[3] << 128)) / 10**token_decimals
        increase_allowance_amount = (calls[1].calldata[1] + (calls[1].calldata[2] << 128)) / 10**token_decimals
        deposit_amount = calls[2].calldata[1] / 10**paraclear_decimals

        print(f"  transfer_from amount:      {transfer_from_amount}")
        print(f"  increase_allowance amount:  {increase_allowance_amount}")
        print(f"  deposit amount:             {deposit_amount}")

        if transfer_from_amount != token_allowance_in_tokens:
            print(f"  !!! transfer_from amount ({transfer_from_amount}) != allowance ({token_allowance_in_tokens}) !!!")
        if increase_allowance_amount != token_allowance_in_tokens:
            print(
                f"  !!! increase_allowance amount ({increase_allowance_amount}) != allowance"
                f" ({token_allowance_in_tokens}) !!!"
            )
        if deposit_amount != token_amount_paraclear / 10**paraclear_decimals:
            print(
                f"  !!! deposit amount ({deposit_amount}) != paraclear amount"
                f" ({token_amount_paraclear / 10**paraclear_decimals}) !!!"
            )

        print("\n")

        print("Nothing executed, your are in DRY RUN mode")
        print("*** DO NOT EXECUTE THIS SCRIPT IF YOU ARE NOT SURE ABOUT IT ***")
        print("*** OR ANY OF THE ABOVE VALIDATIONS ARE NOT CORRECT ***")
        print("\n")
        print("To do the claim set DRY_RUN environment variable to false")
        print("export DRY_RUN=false")
        print("and run the script again")
        print("python examples/claim_dime_airdrop.py")
        print("\n")
        return

    # Execute the multicall transaction
    account_contract = await paradex.account.starknet.load_contract(paradex.account.l2_address, is_cairo0_contract=True)
    need_multisig = await paradex.account.starknet.check_multisig_required(account_contract)
    if need_multisig:
        raise SystemExit("Error: multisig accounts are not supported")

    prepared_invoke = await paradex.account.starknet.prepare_invoke(calls=calls, auto_estimate=True)
    owner_signature = paradex.account.starknet.signer.sign_transaction(prepared_invoke)

    # Simulate before sending
    print("Simulating transaction...")
    signed_invoke = paradex.account.starknet._add_signature(prepared_invoke, owner_signature)
    simulation = await paradex.account.starknet.client.simulate_transactions(transactions=[signed_invoke])
    exec_info = simulation[0].transaction_trace.execute_invocation
    revert_reason = getattr(exec_info, "revert_reason", None)
    if revert_reason:
        raise SystemExit(f"Simulation reverted: {revert_reason}")
    print("Simulation successful!")

    print("\nExecuting transaction...")
    invoke_result = await paradex.account.starknet.invoke(account_contract, prepared_invoke, owner_signature)
    tx_hash = hex(invoke_result.hash)
    print(f"Transaction sent! Hash: {tx_hash}")

    print("Waiting for acceptance...")
    await invoke_result.wait_for_acceptance()
    print("Transaction accepted on chain!")


asyncio.run(main())
