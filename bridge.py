from web3 import Web3
from web3.providers.rpc import HTTPProvider
from web3.middleware import ExtraDataToPOAMiddleware  # Necessary for POA chains
from datetime import datetime
import json
import pandas as pd

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

# Deploy contract
def deploy_contract(w3, contract_file, *args):
    # Load contract ABI and bytecode
    with open(contract_file, 'r') as file:
        contract_json = json.load(file)
        abi = contract_json['abi']
        bytecode = contract_json['bytecode']
    
    # Get account
    account = w3.eth.account.create()
    private_key = account.key.hex()
    account_address = account.address
    
    print(f"Created account: {account_address}")
    print(f"This account needs to be funded with testnet tokens")
    input("Press Enter once the account is funded...")
    
    # Deploy contract
    contract = w3.eth.contract(abi=abi, bytecode=bytecode)
    
    # Prepare transaction
    construct_txn = contract.constructor(*args).build_transaction({
        'from': account_address,
        'nonce': w3.eth.get_transaction_count(account_address),
        'gas': 3000000,
        'gasPrice': w3.eth.gas_price
    })
    
    # Sign and send transaction
    signed = w3.eth.account.sign_transaction(construct_txn, private_key)
    tx_hash = w3.eth.send_raw_transaction(signed.rawTransaction)
    
    # Wait for transaction receipt
    tx_receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    contract_address = tx_receipt.contractAddress
    
    return contract_address, abi, private_key, account_address

# Deploy bridge contracts
def scan_blocks(chain, contract_info="contract_info.json"):
    """
        chain - (string) should be either "source" or "destination"
        Scan the last 5 blocks of the source and destination chains
        Look for 'Deposit' events on the source chain and 'Unwrap' events on the destination chain
        When Deposit events are found on the source chain, call the 'wrap' function the destination chain
        When Unwrap events are found on the destination chain, call the 'withdraw' function on the source chain
    """

    # This is different from Bridge IV where chain was "avax" or "bsc"
    if chain not in ['source','destination']:
        print(f"Invalid chain: {chain}")
        return 0
    
    # Connect to the specified chain
    w3 = connect_to(chain)
    
    # Get contract info for both source and destination chains
    source_info = get_contract_info('source', contract_info)
    destination_info = get_contract_info('destination', contract_info)
    
    # Create contract instances for both chains
    source_contract = w3.eth.contract(
        address=w3.to_checksum_address(source_info['address']), 
        abi=source_info['abi']
    )
    
    dest_w3 = connect_to('destination')
    destination_contract = dest_w3.eth.contract(
        address=dest_w3.to_checksum_address(destination_info['address']), 
        abi=destination_info['abi']
    )
    
    # Get the current block number
    current_block = w3.eth.block_number
    
    # Define the start block (5 blocks back from current)
    start_block = max(0, current_block - 5)
    
    print(f"Scanning {chain} chain from block {start_block} to {current_block}")
    
    # Define which events to look for based on the chain
    if chain == 'source':
        # Look for Deposit events on source chain
        deposit_events = source_contract.events.Deposit().get_logs(fromBlock=start_block, toBlock=current_block)
        
        # Process each Deposit event
        for event in deposit_events:
            token = event.args.token
            recipient = event.args.recipient
            amount = event.args.amount
            
            print(f"Deposit event found: Token={token}, Recipient={recipient}, Amount={amount}")
            
            # Call wrap function on destination chain
            try:
                # Use your account as the warden
                warden_account = '0x86a11d271dA11aa145cAE9f8396b09Aa4C0530Bb'  # Your provided account address
                
                # Call the wrap function on the destination contract
                tx = destination_contract.functions.wrap(
                    token,
                    recipient,
                    amount
                ).build_transaction({
                    'from': warden_account,
                    'nonce': dest_w3.eth.get_transaction_count(warden_account),
                    'gas': 200000,  # Adjust as needed
                    'gasPrice': dest_w3.eth.gas_price
                })
                
                # Sign and send the transaction
                private_key = '0x82429e0e75ae4201759386e760a55601f6280a8c025366f90f07460915dc2ff4'  # Your provided private key
                signed_tx = dest_w3.eth.account.sign_transaction(tx, private_key)
                tx_hash = dest_w3.eth.send_raw_transaction(signed_tx.rawTransaction)
                
                # Wait for the transaction to be mined
                receipt = dest_w3.eth.wait_for_transaction_receipt(tx_hash)
                print(f"Wrap transaction successful: {tx_hash.hex()}")
                
            except Exception as e:
                print(f"Error processing Deposit event: {e}")
    
    elif chain == 'destination':
        # Look for Unwrap events on destination chain
        unwrap_events = destination_contract.events.Unwrap().get_logs(fromBlock=start_block, toBlock=current_block)
        
        # Process each Unwrap event
        for event in unwrap_events:
            underlying_token = event.args.underlying_token
            to = event.args.to  # Recipient
            amount = event.args.amount
            
            print(f"Unwrap event found: Token={underlying_token}, Recipient={to}, Amount={amount}")
            
            # Call withdraw function on source chain
            try:
                # Use your account as the warden
                warden_account = '0x86a11d271dA11aa145cAE9f8396b09Aa4C0530Bb'  # Your provided account address
                
                source_w3 = connect_to('source')
                
                # Call the withdraw function on the source contract
                tx = source_contract.functions.withdraw(
                    underlying_token,
                    to,
                    amount
                ).build_transaction({
                    'from': warden_account,
                    'nonce': source_w3.eth.get_transaction_count(warden_account),
                    'gas': 200000,  # Adjust as needed
                    'gasPrice': source_w3.eth.gas_price
                })
                
                # Sign and send the transaction
                private_key = '0x82429e0e75ae4201759386e760a55601f6280a8c025366f90f07460915dc2ff4'  # Your provided private key
                signed_tx = source_w3.eth.account.sign_transaction(tx, private_key)
                tx_hash = source_w3.eth.send_raw_transaction(signed_tx.rawTransaction)
                
                # Wait for the transaction to be mined
                receipt = source_w3.eth.wait_for_transaction_receipt(tx_hash)
                print(f"Withdraw transaction successful: {tx_hash.hex()}")
                
            except Exception as e:
                print(f"Error processing Unwrap event: {e}")
    
    return 1