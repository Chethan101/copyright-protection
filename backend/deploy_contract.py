import os
import json
from solcx import compile_source, install_solc
from web3 import Web3

def deploy():
    # Connect to Ganache
    w3 = Web3(Web3.HTTPProvider('http://127.0.0.1:7545'))
    
    if not w3.is_connected():
        print("Failed to connect to Ganache.")
        return

    # Set default account (first account from Ganache)
    w3.eth.default_account = w3.eth.accounts[0]
    
    print(f"Connected to Ganache. Using account: {w3.eth.default_account}")

    # Install solc
    print("Installing solc...")
    install_solc('0.8.0')
    
    # Read contract
    contract_path = os.path.join(os.path.dirname(__file__), 'contracts', 'CopyrightRegistry.sol')
    with open(contract_path, 'r') as f:
        contract_source = f.read()

    print("Compiling contract...")
    # Compile
    compiled_sol = compile_source(
        contract_source,
        output_values=['abi', 'bin'],
        solc_version='0.8.0'
    )
    
    contract_id, contract_interface = compiled_sol.popitem()
    bytecode = contract_interface['bin']
    abi = contract_interface['abi']
    
    print("Deploying contract...")
    CopyrightRegistry = w3.eth.contract(abi=abi, bytecode=bytecode)
    
    # Build transaction
    tx_hash = CopyrightRegistry.constructor().transact()
    
    # Wait for receipt
    tx_receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    
    print(f"Contract deployed at address: {tx_receipt.contractAddress}")
    
    # Save the ABI and address
    output_data = {
        "address": tx_receipt.contractAddress,
        "abi": abi
    }
    
    output_path = os.path.join(os.path.dirname(__file__), 'contract_info.json')
    with open(output_path, 'w') as f:
        json.dump(output_data, f, indent=4)
        
    print(f"Saved contract info to {output_path}")

if __name__ == "__main__":
    deploy()
