from django.http import JsonResponse
import time
from django.utils.deprecation import MiddlewareMixin
from django.shortcuts import redirect
from django.dispatch import receiver
import json
from django.contrib.auth.signals import user_logged_in



class RateLimitMiddleware(MiddlewareMixin):
    # Store IP addresses and their last request times
    ip_requests = {}

    def process_request(self, request):
        # Only apply rate limiting to the demo journal API
        if request.path == '/api/demo-journal/' and request.method == 'POST':
            ip = self.get_client_ip(request)
            current_time = time.time()

            # Check if this IP has made a request in the last 10 seconds
            if ip in self.ip_requests:
                last_request_time = self.ip_requests[ip]
                # Rate limit to one request per 10 seconds for demo
                if current_time - last_request_time < 10:
                    return JsonResponse(
                        {'error': 'Too many requests. Please wait before trying again.'},
                        status=429
                    )

            # Update the last request time for this IP
            self.ip_requests[ip] = current_time

            # Clean up old entries (older than 1 minute)
            self._cleanup_old_entries(current_time)

    def get_client_ip(self, request):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip

    def _cleanup_old_entries(self, current_time):
        # Remove entries older than 1 minute to prevent memory issues
        to_remove = []
        for ip, timestamp in self.ip_requests.items():
            if current_time - timestamp > 60:
                to_remove.append(ip)

        for ip in to_remove:
            self.ip_requests.pop(ip, None)

class PendingEntryMiddleware:
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
                        return redirect('entry_detail', entry_id=entry.id)
                except Exception as e:
                    # Log the error but don't crash
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.error(f"Error processing pending entry: {str(e)}")

        return response
