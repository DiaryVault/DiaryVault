from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from django.contrib.auth import get_user_model
from .models import WalletSession

User = get_user_model()

class Web3Authentication(BaseAuthentication):
    """Custom authentication for Web3 sessions"""
    
    def authenticate(self, request):
        session_id = request.META.get('HTTP_X_SESSION_ID')
        
        if not session_id:
            return None
        
        try:
            session = WalletSession.objects.select_related('user').get(
                session_id=session_id,
                is_active=True
            )
            
            # Update last activity
            session.save(update_fields=['last_activity'])
            
            return (session.user, session)
            
        except WalletSession.DoesNotExist:
            raise AuthenticationFailed('Invalid session')
