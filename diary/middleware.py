from django.http import JsonResponse
import time
from django.utils.deprecation import MiddlewareMixin

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
