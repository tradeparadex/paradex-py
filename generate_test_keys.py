#!/usr/bin/env python3
"""
Generate Ethereum private keys and addresses for testing.
Uses eth-account for proper Ethereum key generation.
"""

import json
import secrets

from eth_account import Account


def generate_ethereum_keypair():
    """Generate a random Ethereum private key and corresponding address."""
    # Generate a cryptographically secure random private key (32 bytes)
    private_key_bytes = secrets.randbits(256).to_bytes(32, "big")

    # Create account from private key
    account = Account.from_key(private_key_bytes)

    # Get the private key as hex string
    private_key_hex = "0x" + private_key_bytes.hex()

    # Get the address (already checksummed)
    address = account.address

    return private_key_hex, address


def main():
    """Generate 3 Ethereum keypairs and save to file."""
    print("Generating 3 Ethereum keypairs...")

    accounts = []
    for i in range(3):
        private_key, address = generate_ethereum_keypair()
        account = {"name": f"account_{i+1}", "l1_private_key": private_key, "l1_address": address}
        accounts.append(account)
        print(f"Account {i+1}: {address}")

    # Save to JSON file
    with open("test_accounts.json", "w") as f:
        json.dump(accounts, f, indent=2)

    print(f"\nGenerated {len(accounts)} accounts and saved to test_accounts.json")

    # Also create a simple Python file for easy import
    with open("test_accounts.py", "w") as f:
        f.write("# Generated Ethereum test accounts\n")
        f.write("# DO NOT USE IN PRODUCTION - FOR TESTING ONLY\n\n")
        f.write("TEST_ACCOUNTS = [\n")
        for account in accounts:
            f.write("    {{\n")
            f.write(f"        'name': '{account['name']}',\n")
            f.write(f"        'l1_private_key': '{account['l1_private_key']}',\n")
            f.write(f"        'l1_address': '{account['l1_address']}'\n")
            f.write("    }},\n")
        f.write("]\n")

    print("Also saved to test_accounts.py for easy import")


if __name__ == "__main__":
    main()
