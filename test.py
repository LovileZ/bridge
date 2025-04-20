from web3 import Web3
from web3.providers.rpc import HTTPProvider
from web3.middleware import ExtraDataToPOAMiddleware  # Necessary for POA chains
from datetime import datetime
import json
import pandas as pd
import os

# Your existing account
ACCOUNT_ADDRESS = "0x86a11d271dA11aa145cAE9f8396b09Aa4C0530Bb"
PRIVATE_KEY = "0x82429e0e75ae4201759386e760a55601f6280a8c025366f90f07460915dc2ff4"

# Connect to networks
def connect_to(chain):
    if chain == 'source':  # AVAX C-chain testnet
        api_url = "https://api.avax-test.network/ext/bc/C/rpc"
    elif chain == 'destination':  # BSC testnet
        api_url = "https://data-seed-prebsc-1-s1.binance.org:8545/"
    
    w3 = Web3(HTTPProvider(api_url))
    # Inject the poa compatibility middleware to the innermost layer
    w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
    return w3

# Deploy contract from JSON file with ABI and bytecode
def deploy_contract(w3, contract_file, admin_address):
    try:
        # Load contract JSON
        with open(contract_file, 'r') as file:
            contract_json = json.load(file)
            bytecode = contract_json['data']['bytecode']['object']
            abi = contract_json['abi']
        
        # Verify contract JSON contents
        if not bytecode or not abi:
            print(f"Error: Invalid contract file {contract_file}")
            print(f"Bytecode present: {bool(bytecode)}")
            print(f"ABI present: {bool(abi)}")
            return None, None, None, None
        
        # Use the provided account info
        warden_address = ACCOUNT_ADDRESS
        private_key = PRIVATE_KEY
        
        print(f"Using account: {warden_address}")
        print("This account should be funded with testnet tokens")
        
        # Deploy contract with error handling
        try:
            contract = w3.eth.contract(abi=abi, bytecode=bytecode)
            
            # Get current nonce and gas price
            nonce = w3.eth.get_transaction_count(warden_address)
            gas_price = w3.eth.gas_price
            
            print(f"Current nonce: {nonce}")
            print(f"Gas price: {gas_price}")
            
            # Prepare transaction
            construct_txn = contract.constructor(admin_address).build_transaction({
                'from': warden_address,
                'nonce': nonce,
                'gas': 3000000,
                'gasPrice': gas_price
            })
            
            # Sign and send transaction
            signed = w3.eth.account.sign_transaction(construct_txn, private_key)
            tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
            
            # Wait for transaction receipt with timeout
            print(f"Waiting for transaction {tx_hash.hex()} to be mined...")
            tx_receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
            
            if tx_receipt.status != 1:
                print(f"Contract deployment failed. Transaction status: {tx_receipt.status}")
                return None, None, None, None
                
            contract_address = tx_receipt.contractAddress
            print(f"Contract deployed at: {contract_address}")
            
            # Verify contract code was deployed
            deployed_code = w3.eth.get_code(contract_address)
            if deployed_code == b'':
                print("Warning: No contract code found at deployed address")
                return None, None, None, None
                
            return contract_address, abi, private_key, warden_address
            
        except Exception as e:
            print(f"Error during contract deployment: {str(e)}")
            return None, None, None, None
            
    except Exception as e:
        print(f"Error loading contract file: {str(e)}")
        return None, None, None, None

# Deploy bridge contracts
def deploy_bridge_contracts():
    # Connect to networks
    source_w3 = connect_to('source')
    dest_w3 = connect_to('destination')
    
    # Check connections
    if not source_w3.is_connected() or not dest_w3.is_connected():
        print("Failed to connect to one or both networks")
        return None
    
    print("Connected to both networks")
    
    # Deploy source contract
    print("\nDeploying Source contract...")
    source_result = deploy_contract(source_w3, 'Source.json', ACCOUNT_ADDRESS)
    if None in source_result:
        print("Source contract deployment failed")
        return None
    
    source_address, source_abi, source_key, source_warden = source_result
    
    # Deploy destination contract
    print("\nDeploying Destination contract...")
    dest_result = deploy_contract(dest_w3, 'Destination.json', ACCOUNT_ADDRESS)
    if None in dest_result:
        print("Destination contract deployment failed")
        return None
        
    dest_address, dest_abi, dest_key, dest_warden = dest_result
    
    # Save contract_info.json for the autograder with only address and ABI
    contract_info = {
        "source": {
            "address": source_address,
            "abi": source_abi
        },
        "destination": {
            "address": dest_address,
            "abi": dest_abi
        }
    }
    
    # Save all info including private keys and warden accounts
    complete_info = {
        "source": {
            "address": source_address,
            "abi": source_abi,
            "warden": source_warden,
            "private_key": source_key
        },
        "destination": {
            "address": dest_address,
            "abi": dest_abi,
            "warden": dest_warden,
            "private_key": dest_key
        },
        "admin": {
            "address": ACCOUNT_ADDRESS,
            "private_key": PRIVATE_KEY
        }
    }
    
    # Save contract_info.json for the autograder
    with open('contract_info.json', 'w') as f:
        json.dump(contract_info, f, indent=2)
    
    # Save complete info to a separate file for our use
    with open('contract_info_complete.json', 'w') as f:
        json.dump(complete_info, f, indent=2)
    
    print("\nContract information saved to contract_info.json")
    print(f"Complete information including warden accounts saved to contract_info_complete.json")
    
    # Grant WARDEN_ROLE to the warden accounts
    print("\nNow granting WARDEN_ROLE to your account...")
    
    # Source contract
    source_contract = source_w3.eth.contract(address=source_address, abi=source_abi)
    warden_role = source_contract.functions.WARDEN_ROLE().call()
    
    grant_tx = source_contract.functions.grantRole(
        warden_role, source_warden
    ).build_transaction({
        'from': ACCOUNT_ADDRESS,
        'nonce': source_w3.eth.get_transaction_count(ACCOUNT_ADDRESS),
        'gas': 200000,
        'gasPrice': source_w3.eth.gas_price
    })
    
    signed_tx = source_w3.eth.account.sign_transaction(grant_tx, PRIVATE_KEY)
    tx_hash = source_w3.eth.send_raw_transaction(signed_tx.raw_transaction)  # Changed from rawTransaction
    receipt = source_w3.eth.wait_for_transaction_receipt(tx_hash)
    
    print(f"WARDEN_ROLE granted to {source_warden} on source contract: {receipt.status}")
    
    # Destination contract
    dest_contract = dest_w3.eth.contract(address=dest_address, abi=dest_abi)
    warden_role = dest_contract.functions.WARDEN_ROLE().call()
    
    grant_tx = dest_contract.functions.grantRole(
        warden_role, dest_warden
    ).build_transaction({
        'from': ACCOUNT_ADDRESS,
        'nonce': dest_w3.eth.get_transaction_count(ACCOUNT_ADDRESS),
        'gas': 200000,
        'gasPrice': dest_w3.eth.gas_price
    })
    
    signed_tx = dest_w3.eth.account.sign_transaction(grant_tx, PRIVATE_KEY)
    tx_hash = dest_w3.eth.send_raw_transaction(signed_tx.raw_transaction)  # Changed from rawTransaction
    receipt = dest_w3.eth.wait_for_transaction_receipt(tx_hash)
    
    print(f"WARDEN_ROLE granted to {dest_warden} on destination contract: {receipt.status}")
    
    return complete_info

# Register ERC20 tokens
def register_tokens():
    # Load contract info with private keys
    with open('contract_info_complete.json', 'r') as f:
        contract_info = json.load(f)
    
    # Load ERC20 tokens from CSV
    tokens_df = pd.read_csv('erc20s.csv')
    
    # Connect to networks
    source_w3 = connect_to('source')
    dest_w3 = connect_to('destination')
    
    # Get contract instances
    source_contract = source_w3.eth.contract(
        address=source_w3.to_checksum_address(contract_info['source']['address']),
        abi=contract_info['source']['abi']
    )
    
    destination_contract = dest_w3.eth.contract(
        address=dest_w3.to_checksum_address(contract_info['destination']['address']),
        abi=contract_info['destination']['abi']
    )
    
    # Filter tokens by chain
    source_tokens = tokens_df[tokens_df['chain'] == 'source']
    
    # Register tokens on source chain
    for _, token in source_tokens.iterrows():
        token_address = source_w3.to_checksum_address(token['address'])
        
        # Register token (requires ADMIN_ROLE)
        admin_address = contract_info['admin']['address']
        admin_key = contract_info['admin']['private_key']
        
        tx = source_contract.functions.registerToken(token_address).build_transaction({
            'from': admin_address,
            'nonce': source_w3.eth.get_transaction_count(admin_address),
            'gas': 200000,
            'gasPrice': source_w3.eth.gas_price
        })
        
        signed_tx = source_w3.eth.account.sign_transaction(tx, admin_key)
        tx_hash = source_w3.eth.send_raw_transaction(signed_tx.raw_transaction)  # Changed from rawTransaction
        receipt = source_w3.eth.wait_for_transaction_receipt(tx_hash)
        
        print(f"Registered token {token_address} on source chain: {receipt.status}")
    
    # Create wrapped tokens on destination chain
    for _, token in source_tokens.iterrows():
        token_address = source_w3.to_checksum_address(token['address'])
        
        # Create wrapped token (requires CREATOR_ROLE)
        admin_address = contract_info['admin']['address']
        admin_key = contract_info['admin']['private_key']
        
        # Generate a token name and symbol
        token_name = f"Wrapped Token {token_address[-6:]}"
        token_symbol = f"W{token_address[-4:]}"
        
        # Call createToken function
        tx = destination_contract.functions.createToken(
            token_address,  # underlying token address from source chain
            token_name,
            token_symbol
        ).build_transaction({
            'from': admin_address,
            'nonce': dest_w3.eth.get_transaction_count(admin_address),
            'gas': 3000000,
            'gasPrice': dest_w3.eth.gas_price
        })
        
        signed_tx = dest_w3.eth.account.sign_transaction(tx, admin_key)
        tx_hash = dest_w3.eth.send_raw_transaction(signed_tx.raw_transaction)  # Changed from rawTransaction
        receipt = dest_w3.eth.wait_for_transaction_receipt(tx_hash)
        
        print(f"Created wrapped token for {token_address} on destination chain: {receipt.status}")

# Update bridge.py
def update_bridge_py():
    # Read the bridge.py file
    with open('bridge.py', 'r') as f:
        bridge_code = f.read()
    
    # Replace the hardcoded private key with code to load from contract_info_complete.json
    updated_code = bridge_code.replace(
        "private_key = 'your_private_key_here'  # Replace with actual private key or secure access method",
        f"private_key = '{PRIVATE_KEY}'  # Your account private key"
    )
    
    # Update the warden account handling for destination chain
    updated_code = updated_code.replace(
        "warden_account = dest_w3.eth.accounts[0]  # This should be your warden account",
        f"warden_account = '{ACCOUNT_ADDRESS}'  # Your account address"
    )
    
    # Update the warden account handling for source chain
    updated_code = updated_code.replace(
        "warden_account = source_w3.eth.accounts[0]  # This should be your warden account",
        f"warden_account = '{ACCOUNT_ADDRESS}'  # Your account address"
    )
    
    # Write the updated code back to bridge.py
    with open('bridge.py', 'w') as f:
        f.write(updated_code)
    
    print("bridge.py updated with your account address and private key")

# Main function
def main():
    print("===== STEP 1: Deploying Bridge Contracts =====")
    deploy_bridge_contracts()
    
    print("\n===== STEP 2: Registering ERC20 Tokens =====")
    register_tokens()
    
    print("\n===== STEP 3: Updating bridge.py =====")
    update_bridge_py()
    
    print("\n===== All tasks completed successfully =====")
    print("You can now run the bridge by executing:")
    print("python bridge.py source    # To monitor the source chain")
    print("python bridge.py destination    # To monitor the destination chain")

if __name__ == "__main__":
    main()