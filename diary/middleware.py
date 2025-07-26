from django.http import JsonResponse
import time
from django.utils.deprecation import MiddlewareMixin
from django.shortcuts import redirect
from django.dispatch import receiver
import json
from django.contrib.auth.signals import user_logged_in
from django.contrib.auth import get_user_model
from .models import WalletSession
import logging

logger = logging.getLogger(__name__)
User = get_user_model()

class Web3SecurityMiddleware(MiddlewareMixin):
    """Enhanced security middleware for Web3 authentication"""
    
    def process_request(self, request):
        # Add security headers for Web3 endpoints
        if request.path.startswith('/api/web3/'):
            # Prevent caching of sensitive endpoints
            request.META['HTTP_CACHE_CONTROL'] = 'no-cache, no-store, must-revalidate'
            request.META['HTTP_PRAGMA'] = 'no-cache'
            request.META['HTTP_EXPIRES'] = '0'
        return None

    def process_response(self, request, response):
        # Add security headers to Web3 API responses
        if request.path.startswith('/api/web3/'):
            response['X-Content-Type-Options'] = 'nosniff'
            response['X-Frame-Options'] = 'DENY'
            response['X-XSS-Protection'] = '1; mode=block'
            response['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        return response

class RateLimitMiddleware(MiddlewareMixin):
    """Enhanced rate limiting for both demo API and Web3 endpoints"""
    
    def __init__(self, get_response):
        self.get_response = get_response
        # Store IP addresses and their last request times
        self.ip_requests = {}
        self.web3_cache = {}  # Separate cache for Web3 endpoints

    def process_request(self, request):
        ip = self.get_client_ip(request)
        current_time = time.time()
        
        # Handle Web3 endpoint rate limiting (20 requests per minute)
        if request.path.startswith('/api/web3/'):
            return self._handle_web3_rate_limit(ip, current_time)
        
        # Handle demo journal API rate limiting (original logic)
        elif request.path == '/api/demo-journal/' and request.method == 'POST':
            return self._handle_demo_rate_limit(ip, current_time)
        
        return None

    def _handle_web3_rate_limit(self, ip, current_time):
        """Handle rate limiting for Web3 endpoints (20 requests per minute per IP)"""
        # Clean old entries (older than 1 minute)
        cutoff_time = current_time - 60  # 1 minute window
        self.web3_cache = {k: v for k, v in self.web3_cache.items() if v['timestamp'] > cutoff_time}
        
        # Check rate limit
        if ip in self.web3_cache:
            if self.web3_cache[ip]['count'] >= 20:
                logger.warning(f"Web3 rate limit exceeded for IP: {ip}")
                return JsonResponse({
                    'error': 'Rate limit exceeded. Please try again later.'
                }, status=429)
            else:
                self.web3_cache[ip]['count'] += 1
        else:
            self.web3_cache[ip] = {'count': 1, 'timestamp': current_time}
        
        return None

    def _handle_demo_rate_limit(self, ip, current_time):
        """Handle rate limiting for demo journal API (original logic)"""
        # Check if this IP has made a request in the last 10 seconds
        if ip in self.ip_requests:
            last_request_time = self.ip_requests[ip]
            # Rate limit to one request per 10 seconds for demo
            if current_time - last_request_time < 10:
                logger.warning(f"Demo API rate limit exceeded for IP: {ip}")
                return JsonResponse(
                    {'error': 'Too many requests. Please wait before trying again.'},
                    status=429
                )

        # Update the last request time for this IP
        self.ip_requests[ip] = current_time

        # Clean up old entries (older than 1 minute)
        self._cleanup_old_entries(current_time)
        
        return None

    def get_client_ip(self, request):
        """Get the real client IP address"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0].strip()
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip

    def _cleanup_old_entries(self, current_time):
        """Remove entries older than 1 minute to prevent memory issues"""
        to_remove = []
        for ip, timestamp in self.ip_requests.items():
            if current_time - timestamp > 60:
                to_remove.append(ip)

        for ip in to_remove:
            self.ip_requests.pop(ip, None)

class PendingEntryMiddleware:
    """Middleware to handle pending journal entries after login"""
    
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Process the request before the view is called
        response = self.get_response(request)

        # We need to check if the user just logged in
        # This is a simple check - see if the user is authenticated and came from the login page
        referer = request.META.get('HTTP_REFERER', '')
        is_authenticated = request.user.is_authenticated
        came_from_login = 'login' in referer

        if is_authenticated and came_from_login:
            # Try to get pending entry from localStorage via a parameter
            if 'pendingEntry' in request.GET:
                try:
                    from .models import Entry, Tag
                    from .views import auto_generate_tags

                    pending_entry = json.loads(request.GET.get('pendingEntry', '{}'))

                    if pending_entry and pending_entry.get('content'):
                        # Create the entry
                        entry = Entry.objects.create(
                            user=request.user,
                            title=pending_entry.get('title', 'Untitled Entry'),
                            content=pending_entry.get('content', ''),
                            mood=pending_entry.get('mood')
                        )

                        # Add tags
                        tags = pending_entry.get('tags', [])
                        if not tags and pending_entry.get('content'):
                            tags = auto_generate_tags(pending_entry.get('content'), pending_entry.get('mood'))

                        if tags:
                            for tag_name in tags:
                                tag, created = Tag.objects.get_or_create(
                                    name=tag_name.lower().strip(),
                                    user=request.user
                                )
                                entry.tags.add(tag)

                        # Redirect to the created entry
                        logger.info(f"Created pending entry for user {request.user.username}")
                        return redirect('entry_detail', entry_id=entry.id)
                except Exception as e:
                    # Log the error but don't crash
                    logger.error(f"Error processing pending entry: {str(e)}")

        return response

class Web3SessionMiddleware(MiddlewareMixin):
    """Middleware to handle Web3 wallet session management"""
    
    def process_request(self, request):
        # Only process for authenticated users
        if not request.user.is_authenticated:
            return None
            
        # Check if user has an active wallet session
        if hasattr(request.user, 'wallet_sessions'):
            try:
                active_session = request.user.wallet_sessions.filter(is_active=True).first()
                if active_session:
                    # Update last activity
                    active_session.update_last_activity()
                    request.wallet_session = active_session
                else:
                    request.wallet_session = None
            except Exception as e:
                logger.error(f"Error updating wallet session: {str(e)}")
                request.wallet_session = None
        else:
            request.wallet_session = None
            
        return None