from django.shortcuts import redirect
from django.urls import reverse
from django.http import JsonResponse
from functools import wraps
from django.conf import settings

class WalletAuthenticationMiddleware:
    """
    Middleware to check wallet connection status for protected views
    """
    def __init__(self, get_response):
        self.get_response = get_response
        
        # Define protected URL patterns
        self.protected_urls = [
            '/dashboard/',
            '/library/',
            '/insights/',
            '/new-entry/',
            '/account/settings/',
            '/api/entries/',
            '/api/insights/',
        ]
        
        # Define public URL patterns
        self.public_urls = [
            '/',
            '/signup/',
            '/login/',
            '/privacy-policy/',
            '/static/',
            '/media/',
            '/api/wallet/',
        ]

    def __call__(self, request):
        # Check if the current path requires wallet authentication
        if self.requires_wallet_auth(request.path):
            # Check wallet connection status from session or headers
            wallet_connected = self.check_wallet_connection(request)
            
            if not wallet_connected:
                # For API requests, return JSON error
                if request.path.startswith('/api/'):
                    return JsonResponse({
                        'error': 'Wallet connection required',
                        'redirect': reverse('account_signup')
                    }, status=401)
                
                # For regular requests, redirect to signup
                return redirect('account_signup')
        
        response = self.get_response(request)
        return response
    
    def requires_wallet_auth(self, path):
        """Check if the given path requires wallet authentication"""
        # Check if it's a public URL
        for public_url in self.public_urls:
            if path.startswith(public_url):
                return False
        
        # Check if it's a protected URL
        for protected_url in self.protected_urls:
            if path.startswith(protected_url):
                return True
        
        # Default to not requiring auth for undefined paths
        return False
    
    def check_wallet_connection(self, request):
        """Check if wallet is connected from session or custom header"""
        # Check session
        if request.session.get('wallet_connected'):
            return True
        
        # Check custom header (for API requests)
        wallet_address = request.headers.get('X-Wallet-Address')
        if wallet_address:
            return True
        
        # Check for wallet auth token
        auth_token = request.headers.get('Authorization')
        if auth_token and auth_token.startswith('Wallet '):
            return True
        
        return False


def wallet_required(view_func):
    """
    Decorator to require wallet connection for specific views
    """
    @wraps(view_func)
    def wrapped_view(request, *args, **kwargs):
        # Check wallet connection
        wallet_connected = (
            request.session.get('wallet_connected') or
            request.headers.get('X-Wallet-Address') or
            (request.headers.get('Authorization', '').startswith('Wallet '))
        )
        
        if not wallet_connected:
            # For AJAX requests
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'error': 'Wallet connection required',
                    'redirect': reverse('account_signup')
                }, status=401)
            
            # For regular requests
            return redirect('account_signup')
        
        return view_func(request, *args, **kwargs)
    
    return wrapped_view


def wallet_optional(view_func):
    """
    Decorator that adds wallet connection info to the view context
    """
    @wraps(view_func)
    def wrapped_view(request, *args, **kwargs):
        # Add wallet info to request
        request.wallet_connected = (
            request.session.get('wallet_connected') or
            request.headers.get('X-Wallet-Address') or
            (request.headers.get('Authorization', '').startswith('Wallet '))
        )
        request.wallet_address = (
            request.session.get('wallet_address') or
            request.headers.get('X-Wallet-Address')
        )
        
        return view_func(request, *args, **kwargs)
    
    return wrapped_view