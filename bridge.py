from web3 import Web3
from web3.providers.rpc import HTTPProvider
from web3.middleware import ExtraDataToPOAMiddleware #Necessary for POA chains
from datetime import datetime
import json
import pandas as pd


def connect_to(chain):
    if chain == 'source':  # The source contract chain is avax
        api_url = f"https://api.avax-test.network/ext/bc/C/rpc" #AVAX C-chain testnet

    if chain == 'destination':  # The destination contract chain is bsc
        api_url = f"https://data-seed-prebsc-1-s1.binance.org:8545/" #BSC testnet

    if chain in ['source','destination']:
        w3 = Web3(Web3.HTTPProvider(api_url))
        # inject the poa compatibility middleware to the innermost layer
        w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
    return w3


def get_contract_info(chain, contract_info):
    """
        Load the contract_info file into a dictionary
        This function is used by the autograder and will likely be useful to you
    """
    try:
        with open(contract_info, 'r')  as f:
            contracts = json.load(f)
    except Exception as e:
        print( f"Failed to read contract info\nPlease contact your instructor\n{e}" )
        return 0
    return contracts[chain]



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
        print( f"Invalid chain: {chain}" )
        return 0
    
    # Connect to the specified chain
    w3 = connect_to(chain)
    
    # Check if connection is successful
    if not w3.is_connected():
        print(f"Failed to connect to {chain} chain")
        return 0
    
    # Get contract information for the specified chain
    contract_info_dict = get_contract_info(chain, contract_info)
    if contract_info_dict == 0:
        return 0
    
    # Create contract instance for the current chain
    contract_address = Web3.to_checksum_address(contract_info_dict['address'])
    contract_abi = contract_info_dict['abi']
    contract = w3.eth.contract(address=contract_address, abi=contract_abi)
    
    # Get the latest block number
    latest_block = w3.eth.block_number
    
    # Define the starting block (5 blocks back from the latest)
    start_block = max(0, latest_block - 4)  # Ensuring we don't go below block 0
    
    print(f"Scanning blocks {start_block} to {latest_block} on {chain} chain")
    
    # If we're on the source chain, we look for Deposit events
    if chain == 'source':
        # Get all Deposit events in the last 5 blocks
        deposit_events = contract.events.Deposit().get_logs(fromBlock=start_block, toBlock=latest_block)
        
        if deposit_events:
            print(f"Found {len(deposit_events)} Deposit events on source chain")
            
            # Connect to the destination chain to call wrap
            dest_w3 = connect_to('destination')
            dest_contract_info = get_contract_info('destination', contract_info)
            dest_contract_address = Web3.to_checksum_address(dest_contract_info['address'])
            dest_contract_abi = dest_contract_info['abi']
            dest_contract = dest_w3.eth.contract(address=dest_contract_address, abi=dest_contract_abi)
            
            # For each Deposit event, call wrap on destination chain
            for event in deposit_events:
                # Extract data from the event
                recipient = event['args']['recipient']
                amount = event['args']['amount']
                nonce = event['args']['nonce']
                
                print(f"Processing Deposit event: recipient={recipient}, amount={amount}, nonce={nonce}")
                
                # Get the private key from contract info for transaction signing
                private_key = dest_contract_info['private_key']
                account = dest_w3.eth.account.from_key(private_key)
                
                # Build the transaction to call wrap function
                try:
                    # Estimate gas for the transaction
                    gas_estimate = dest_contract.functions.wrap(recipient, amount, nonce).estimate_gas({
                        'from': account.address
                    })
                    
                    # Build transaction
                    tx = dest_contract.functions.wrap(recipient, amount, nonce).build_transaction({
                        'from': account.address,
                        'gas': gas_estimate,
                        'gasPrice': dest_w3.eth.gas_price,
                        'nonce': dest_w3.eth.get_transaction_count(account.address)
                    })
                    
                    # Sign and send transaction
                    signed_tx = dest_w3.eth.account.sign_transaction(tx, private_key)
                    tx_hash = dest_w3.eth.send_raw_transaction(signed_tx.rawTransaction)
                    
                    # Wait for transaction receipt
                    tx_receipt = dest_w3.eth.wait_for_transaction_receipt(tx_hash)
                    print(f"Wrap transaction successful on destination chain. Hash: {tx_hash.hex()}")
                
                except Exception as e:
                    print(f"Failed to execute wrap: {e}")
                    
    # If we're on the destination chain, we look for Unwrap events
    elif chain == 'destination':
        # Get all Unwrap events in the last 5 blocks
        unwrap_events = contract.events.Unwrap().get_logs(fromBlock=start_block, toBlock=latest_block)
        
        if unwrap_events:
            print(f"Found {len(unwrap_events)} Unwrap events on destination chain")
            
            # Connect to the source chain to call withdraw
            source_w3 = connect_to('source')
            source_contract_info = get_contract_info('source', contract_info)
            source_contract_address = Web3.to_checksum_address(source_contract_info['address'])
            source_contract_abi = source_contract_info['abi']
            source_contract = source_w3.eth.contract(address=source_contract_address, abi=source_contract_abi)
            
            # For each Unwrap event, call withdraw on source chain
            for event in unwrap_events:
                # Extract data from the event
                recipient = event['args']['recipient']
                amount = event['args']['amount']
                nonce = event['args']['nonce']
                
                print(f"Processing Unwrap event: recipient={recipient}, amount={amount}, nonce={nonce}")
                
                # Get the private key from contract info for transaction signing
                private_key = source_contract_info['private_key']
                account = source_w3.eth.account.from_key(private_key)
                
                # Build the transaction to call withdraw function
                try:
                    # Estimate gas for the transaction
                    gas_estimate = source_contract.functions.withdraw(recipient, amount, nonce).estimate_gas({
                        'from': account.address
                    })
                    
                    # Build transaction
                    tx = source_contract.functions.withdraw(recipient, amount, nonce).build_transaction({
                        'from': account.address,
                        'gas': gas_estimate,
                        'gasPrice': source_w3.eth.gas_price,
                        'nonce': source_w3.eth.get_transaction_count(account.address)
                    })
                    
                    # Sign and send transaction
                    signed_tx = source_w3.eth.account.sign_transaction(tx, private_key)
                    tx_hash = source_w3.eth.send_raw_transaction(signed_tx.rawTransaction)
                    
                    # Wait for transaction receipt
                    tx_receipt = source_w3.eth.wait_for_transaction_receipt(tx_hash)
                    print(f"Withdraw transaction successful on source chain. Hash: {tx_hash.hex()}")
                
                except Exception as e:
                    print(f"Failed to execute withdraw: {e}")
    
    return 1