import hashlib
import secrets
import time
from datetime import datetime, timedelta
from django.conf import settings
from django.utils import timezone
from eth_account.messages import encode_defunct
from eth_account import Account
import logging

logger = logging.getLogger(__name__)

class Web3Utils:
    
    @staticmethod
    def generate_nonce():
        """Generate a cryptographically secure nonce"""
        return secrets.token_hex(32)
    
    @staticmethod
    def create_auth_message(wallet_address, nonce):
        """Create the message to be signed by the wallet"""
        timestamp = int(time.time())
        template = settings.WEB3_SETTINGS['MESSAGE_TEMPLATE']
        
        return template.format(
            nonce=nonce,
            timestamp=timestamp,
            wallet_address=wallet_address
        )
    
    @staticmethod
    def verify_signature(message, signature, wallet_address):
        """Verify the signature against the message and wallet address"""
        try:
            # Create the message hash
            message_hash = encode_defunct(text=message)
            
            # Recover the address from signature
            recovered_address = Account.recover_message(message_hash, signature=signature)
            
            # Compare addresses (case insensitive)
            return recovered_address.lower() == wallet_address.lower()
            
        except Exception as e:
            logger.error(f"Signature verification failed: {e}")
            return False
    
    @staticmethod
    def is_valid_chain_id(chain_id):
        """Check if chain ID is supported"""
        return chain_id in settings.WEB3_SETTINGS['SUPPORTED_CHAINS']
    
    @staticmethod
    def format_wallet_address(address):
        """Format wallet address consistently"""
        if address:
            return address.lower()
        return None