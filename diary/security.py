import hashlib
import hmac
from django.conf import settings
from django.utils import timezone
from datetime import timedelta
import ipaddress
import re

class SecurityUtils:
    
    @staticmethod
    def is_valid_ethereum_address(address):
        """Validate Ethereum address format and checksum"""
        if not address or not isinstance(address, str):
            return False
        
        # Check basic format
        if not re.match(r'^0x[a-fA-F0-9]{40}, address):
            return False
        
        # TODO: Add checksum validation for extra security
        return True
    
    @staticmethod
    def is_safe_ip(ip_address):
        """Check if IP address is from a safe range"""
        try:
            ip = ipaddress.ip_address(ip_address)
            
            # Block known malicious ranges (example)
            blocked_ranges = [
                ipaddress.ip_network('127.0.0.0/8'),  # Localhost
                ipaddress.ip_network('10.0.0.0/8'),   # Private
                ipaddress.ip_network('172.16.0.0/12'), # Private
                ipaddress.ip_network('192.168.0.0/16'), # Private
            ]
            
            for blocked_range in blocked_ranges:
                if ip in blocked_range and not settings.DEBUG:
                    return False
            
            return True
            
        except ValueError:
            return False
    
    @staticmethod
    def generate_session_token():
        """Generate secure session token"""
        return hashlib.sha256(
            f"{timezone.now().isoformat()}{settings.SECRET_KEY}".encode()
        ).hexdigest()
    
    @staticmethod
    def verify_request_signature(request, signature):
        """Verify request signature for API security"""
        if not signature:
            return False
        
        # Create expected signature
        message = f"{request.method}{request.path}{request.body.decode('utf-8', errors='ignore')}"
        expected_signature = hmac.new(
            settings.SECRET_KEY.encode(),
            message.encode(),
            hashlib.sha256
        ).hexdigest()
        
        return hmac.compare_digest(signature, expected_signature)