from django.http import JsonResponse
from django.db import connection
from django.core.cache import cache
from django.utils import timezone
from .models import User, WalletSession, Web3Nonce
import time

def health_check(request):
    """Health check endpoint for monitoring"""
    
    health_status = {
        'status': 'healthy',
        'timestamp': timezone.now().isoformat(),
        'checks': {}
    }
    
    try:
        # Database check
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            health_status['checks']['database'] = 'healthy'
    except Exception as e:
        health_status['checks']['database'] = f'unhealthy: {str(e)}'
        health_status['status'] = 'unhealthy'
    
    try:
        # Cache check
        cache_key = f'health_check_{int(time.time())}'
        cache.set(cache_key, 'test', 30)
        cache.get(cache_key)
        health_status['checks']['cache'] = 'healthy'
    except Exception as e:
        health_status['checks']['cache'] = f'unhealthy: {str(e)}'
        health_status['status'] = 'unhealthy'
    
    try:
        # Web3 components check
        active_sessions = WalletSession.objects.filter(is_active=True).count()
        pending_nonces = Web3Nonce.objects.filter(is_used=False, expires_at__gt=timezone.now()).count()
        
        health_status['checks']['web3'] = {
            'status': 'healthy',
            'active_sessions': active_sessions,
            'pending_nonces': pending_nonces
        }
    except Exception as e:
        health_status['checks']['web3'] = f'unhealthy: {str(e)}'
        health_status['status'] = 'unhealthy'
    
    status_code = 200 if health_status['status'] == 'healthy' else 503
    return JsonResponse(health_status, status=status_code)

def metrics(request):
    """Metrics endpoint for monitoring"""
    
    try:
        # User metrics
        total_users = User.objects.count()
        web3_users = User.objects.filter(is_web3_verified=True).count()
        active_users = User.objects.filter(last_login__gte=timezone.now() - timezone.timedelta(days=30)).count()
        
        # Session metrics
        active_sessions = WalletSession.objects.filter(is_active=True).count()
        total_sessions = WalletSession.objects.count()
        
        # Nonce metrics
        pending_nonces = Web3Nonce.objects.filter(is_used=False, expires_at__gt=timezone.now()).count()
        expired_nonces = Web3Nonce.objects.filter(expires_at__lt=timezone.now()).count()
        
        metrics_data = {
            'users': {
                'total': total_users,
                'web3_verified': web3_users,
                'active_30d': active_users,
                'conversion_rate': round((web3_users / max(total_users, 1)) * 100, 2)
            },
            'sessions': {
                'active': active_sessions,
                'total': total_sessions
            },
            'nonces': {
                'pending': pending_nonces,
                'expired': expired_nonces
            },
            'timestamp': timezone.now().isoformat()
        }
        
        return JsonResponse(metrics_data)
        
    except Exception as e:
        return JsonResponse({
            'error': str(e),
            'timestamp': timezone.now().isoformat()
        }, status=500)