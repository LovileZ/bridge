from web3 import Web3
from web3.providers.rpc import HTTPProvider
from web3.middleware import ExtraDataToPOAMiddleware
import json
import pandas as pd

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
    w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
    return w3

# Register ERC20 tokens
def register_tokens():
    # Load contract info
    try:
        with open('contract_info.json', 'r') as f:
            contract_info = json.load(f)
    except FileNotFoundError:
        print("Error: contract_info.json not found. Run Task 1 first.")
        return
    
    # Load ERC20 tokens from CSV
    try:
        tokens_df = pd.read_csv('erc20s.csv')
        print(f"Loaded {len(tokens_df)} tokens from erc20s.csv")
    except FileNotFoundError:
        print("Error: erc20s.csv not found.")
        return
    
    # Connect to networks
    source_w3 = connect_to('source')
    dest_w3 = connect_to('destination')
    
    if not source_w3.is_connected() or not dest_w3.is_connected():
        print("Error: Failed to connect to one or both networks")
        return
    
    print("Connected to both networks")
    
    # Add nonce trackers
    source_nonce = source_w3.eth.get_transaction_count(ACCOUNT_ADDRESS)
    dest_nonce = dest_w3.eth.get_transaction_count(ACCOUNT_ADDRESS)
    
    # Get contract instances
    source_contract = source_w3.eth.contract(
        address=source_w3.to_checksum_address(contract_info['source']['address']),
        abi=contract_info['source']['abi']
    )
    
    destination_contract = dest_w3.eth.contract(
        address=dest_w3.to_checksum_address(contract_info['destination']['address']),
        abi=contract_info['destination']['abi']
    )
    
    # Filter tokens - "avax" is source chain, "bsc" is destination chain
    source_tokens = tokens_df[tokens_df['chain'] == 'avax']
    if len(source_tokens) == 0:
        print("No avax (source) tokens found in erc20s.csv")
        return
    
    print(f"Found {len(source_tokens)} avax tokens to register on source chain")
    
    # Register tokens on source chain
    for idx, token in source_tokens.iterrows():
        token_address = source_w3.to_checksum_address(token['address'])
        print(f"Processing token {idx+1}/{len(source_tokens)}: {token_address}")
        
        try:
            # Check if token is already registered
            is_approved = False
            try:
                is_approved = source_contract.functions.approved(token_address).call()
            except Exception:
                # Function might not exist, continue with registration
                pass
                
            if is_approved:
                print(f"Token {token_address} is already registered on source chain")
                continue
                
            # Register token
            tx = source_contract.functions.registerToken(token_address).build_transaction({
                'from': ACCOUNT_ADDRESS,
                'nonce': source_nonce,  # Use tracked nonce
                'gas': 200000,
                'gasPrice': source_w3.eth.gas_price
            })
            
            signed_tx = source_w3.eth.account.sign_transaction(tx, PRIVATE_KEY)
            tx_hash = source_w3.eth.send_raw_transaction(signed_tx.raw_transaction)
            source_nonce += 1  # Increment nonce after sending
            print(f"Sent transaction {tx_hash.hex()}, waiting for confirmation...")
            
            receipt = source_w3.eth.wait_for_transaction_receipt(tx_hash)
            if receipt.status == 1:
                print(f"Successfully registered token {token_address} on source chain")
            else:
                print(f"Failed to register token {token_address}, transaction reverted")
                
        except Exception as e:
            print(f"Error registering token {token_address}: {str(e)}")
    
    print("\nNow creating wrapped tokens on destination chain...")
    
    # Create wrapped tokens on destination chain for source tokens
    for idx, token in source_tokens.iterrows():
        token_address = source_w3.to_checksum_address(token['address'])
        print(f"Creating wrapped token {idx+1}/{len(source_tokens)} for {token_address}")
        
        try:
            # Check if wrapped token already exists
            wrapped_token = None
            try:
                wrapped_token = destination_contract.functions.wrapped_tokens(token_address).call()
                if wrapped_token and wrapped_token != '0x0000000000000000000000000000000000000000':
                    print(f"Wrapped token for {token_address} already exists at {wrapped_token}")
                    continue
            except Exception:
                # Function might not exist or other error, continue with creation
                pass
                
            # Generate token name and symbol
            token_name = f"Wrapped Token {token_address[-6:]}"
            token_symbol = f"W{token_address[-4:]}"
            
            # Create wrapped token
            tx = destination_contract.functions.createToken(
                token_address,  # underlying token address from source chain
                token_name,
                token_symbol
            ).build_transaction({
                'from': ACCOUNT_ADDRESS,
                'nonce': dest_nonce,  # Use tracked nonce
                'gas': 3000000,
                'gasPrice': dest_w3.eth.gas_price
            })
            
            signed_tx = dest_w3.eth.account.sign_transaction(tx, PRIVATE_KEY)
            tx_hash = dest_w3.eth.send_raw_transaction(signed_tx.raw_transaction)
            dest_nonce += 1  # Increment nonce after sending
            print(f"Sent transaction {tx_hash.hex()}, waiting for confirmation...")
            
            receipt = dest_w3.eth.wait_for_transaction_receipt(tx_hash)
            if receipt.status == 1:
                print(f"Successfully created wrapped token for {token_address}")
                
                # Try to get the wrapped token address from logs
                try:
                    # Look for Creation event
                    for log in receipt.logs:
                        if len(log.topics) >= 3 and log.topics[0].hex() == '0x35da56d1e11b45782a01b187be7614a425bb39b607fa6461afba42955ce37e6d':
                            wrapped_token_addr = '0x' + log.topics[2].hex()[-40:]
                            print(f"Wrapped token created at address: {wrapped_token_addr}")
                except Exception as e:
                    print(f"Could not extract wrapped token address: {str(e)}")
            else:
                print(f"Failed to create wrapped token for {token_address}, transaction reverted")
                
        except Exception as e:
            print(f"Error creating wrapped token for {token_address}: {str(e)}")
    
    print("\nToken registration complete")

if __name__ == "__main__":
    register_tokens()