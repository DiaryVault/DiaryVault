# views/web3_auth.py
import json
import logging
import time
from datetime import datetime, timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.http import JsonResponse
from django.shortcuts import render, redirect
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.contrib.auth.models import AnonymousUser

# REST framework
from rest_framework import status, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.authtoken.models import Token

# Local imports
from ..models import Entry, Tag, Web3Nonce, WalletSession, UserPreference
from ..serializers import (
    NonceRequestSerializer, Web3LoginSerializer, UserProfileSerializer
)
from ..utils.Web3Utils import Web3Utils

# Initialize
User = get_user_model()
logger = logging.getLogger(__name__)

@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def request_nonce(request):
    """Generate and return a nonce for wallet authentication"""
    
    serializer = NonceRequestSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    wallet_address = Web3Utils.format_wallet_address(serializer.validated_data['wallet_address'])
    
    try:
        # Generate nonce
        nonce = Web3Utils.generate_nonce()
        
        # Create expiry time
        expires_at = timezone.now() + timedelta(
            seconds=getattr(settings, 'WEB3_NONCE_EXPIRY', 300)  # 5 minutes default
        )
        
        # Clean up old nonces for this wallet
        Web3Nonce.objects.filter(
            wallet_address=wallet_address,
            expires_at__lt=timezone.now()
        ).delete()
        
        # Store nonce in database
        Web3Nonce.objects.create(
            wallet_address=wallet_address,
            nonce=nonce,
            expires_at=expires_at
        )
        
        # Create message for signing
        message = Web3Utils.create_auth_message(wallet_address, nonce)
        
        return Response({
            'success': True,
            'nonce': nonce,
            'message': message,
            'expires_at': expires_at.isoformat(),
            'wallet_address': wallet_address
        })
        
    except Exception as e:
        logger.error(f"Nonce generation failed: {e}")
        return Response(
            {'success': False, 'error': 'Failed to generate nonce'}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def web3_login(request):
    """Authenticate user with Web3 signature"""
    
    serializer = Web3LoginSerializer(data=request.data)
    if not serializer.is_valid():
        return Response({
            'success': False,
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)
    
    wallet_address = Web3Utils.format_wallet_address(serializer.validated_data['wallet_address'])
    signature = serializer.validated_data['signature']
    nonce = serializer.validated_data['nonce']
    wallet_type = serializer.validated_data.get('wallet_type', 'unknown')
    chain_id = serializer.validated_data.get('chain_id', 8453)
    
    try:
        # Verify nonce exists and is valid
        nonce_obj = Web3Nonce.objects.filter(
            wallet_address=wallet_address,
            nonce=nonce,
            is_used=False
        ).first()
        
        if not nonce_obj:
            return Response({
                'success': False,
                'error': 'Invalid or expired nonce. Please try connecting again.'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        if nonce_obj.is_expired():
            return Response({
                'success': False,
                'error': 'Authentication session expired. Please try connecting again.'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Verify chain ID
        if not Web3Utils.is_valid_chain_id(chain_id):
            return Response({
                'success': False,
                'error': 'Unsupported blockchain network. Please switch to Base network.'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Create and verify signature
        message = Web3Utils.create_auth_message(wallet_address, nonce)
        
        if not Web3Utils.verify_signature(message, signature, wallet_address):
            return Response({
                'success': False,
                'error': 'Invalid signature. Please try connecting again.'
            }, status=status.HTTP_401_UNAUTHORIZED)
        
        # Mark nonce as used
        nonce_obj.is_used = True
        nonce_obj.save()
        
        # Get or create user
        user, created = User.objects.get_or_create(
            wallet_address=wallet_address,
            defaults={
                'username': f'user_{wallet_address[-8:]}',
                'wallet_type': wallet_type,
                'is_web3_verified': True,
                'preferred_chain_id': chain_id,
                'last_wallet_login': timezone.now(),
                'is_active': True
            }
        )
        
        if not created:
            # Update existing user
            user.last_wallet_login = timezone.now()
            user.wallet_type = wallet_type
            user.preferred_chain_id = chain_id
            user.is_web3_verified = True
            user.is_active = True
            user.save()
        
        # Create user preferences if they don't exist
        UserPreference.objects.get_or_create(user=user)
        
        # Create or get auth token
        token, token_created = Token.objects.get_or_create(user=user)
        
        # Create wallet session
        session = WalletSession.objects.create(
            user=user,
            wallet_address=wallet_address,
            chain_id=chain_id,
            ip_address=request.META.get('REMOTE_ADDR', ''),
            user_agent=request.META.get('HTTP_USER_AGENT', '')
        )
        
        # Login user to Django session
        login(request, user)
        
        # Handle pending entry if exists
        pending_entry_saved = handle_pending_entry(request, user)
        
        # Get user stats
        user_stats = {
            'total_entries': Entry.objects.filter(user=user).count(),
            'is_new_user': created
        }
        
        response_data = {
            'success': True,
            'token': token.key,
            'user': UserProfileSerializer(user).data,
            'session_id': str(session.session_id),
            'message': 'Successfully authenticated with Web3',
            'stats': user_stats,
            'chain_id': chain_id,
            'is_correct_network': chain_id == 8453
        }
        
        if pending_entry_saved:
            response_data['pending_entry_saved'] = True
            response_data['message'] = 'Successfully authenticated and saved your entry!'
        
        return Response(response_data)
        
    except Exception as e:
        logger.error(f"Web3 login failed: {e}", exc_info=True)
        return Response({
            'success': False,
            'error': 'Authentication failed. Please try again.'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

def handle_pending_entry(request, user):
    """Handle any pending entry after successful login"""
    pending_entry = request.session.get('pending_entry')
    if not pending_entry:
        return False
    
    try:
        # Create the entry
        entry = Entry.objects.create(
            user=user,
            title=pending_entry.get('title', 'Untitled Entry'),
            content=pending_entry.get('content', ''),
            mood=pending_entry.get('mood')
        )
        
        # Add tags
        tags = pending_entry.get('tags', [])
        if not tags and pending_entry.get('content'):
            from ..utils.analytics import auto_generate_tags
            tags = auto_generate_tags(pending_entry.get('content'), pending_entry.get('mood'))
        
        if tags:
            for tag_name in tags:
                if isinstance(tag_name, str) and tag_name.strip():
                    tag, created = Tag.objects.get_or_create(
                        name=tag_name.lower().strip(),
                        user=user
                    )
                    entry.tags.add(tag)
        
        # Handle photo if it was mentioned
        if pending_entry.get('had_photo'):
            # Photo handling would need to be implemented based on your storage strategy
            pass
        
        # Clear the pending entry from session
        del request.session['pending_entry']
        
        # Set success indicators
        request.session['entry_saved'] = True
        request.session['saved_entry_id'] = entry.id
        
        logger.info(f"Successfully created entry after Web3 login with ID: {entry.id}")
        return True
        
    except Exception as e:
        logger.error(f"Error creating entry after Web3 login: {str(e)}", exc_info=True)
        return False

@api_view(['POST'])
@login_required
def disconnect_wallet(request):
    """Disconnect wallet and invalidate session"""
    
    try:
        # Deactivate wallet sessions
        WalletSession.objects.filter(
            user=request.user, 
            is_active=True
        ).update(is_active=False)
        
        # Don't delete the token as user might want to reconnect
        # Token.objects.filter(user=request.user).delete()
        
        return Response({
            'success': True,
            'message': 'Wallet disconnected successfully'
        })
        
    except Exception as e:
        logger.error(f"Wallet disconnection failed: {e}")
        return Response({
            'success': False,
            'error': 'Failed to disconnect wallet'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET'])
@login_required
def user_profile(request):
    """Get current user's profile"""
    
    try:
        serializer = UserProfileSerializer(request.user)
        
        # Add additional context
        profile_data = serializer.data
        profile_data.update({
            'total_entries': Entry.objects.filter(user=request.user).count(),
            'wallet_sessions': WalletSession.objects.filter(
                user=request.user,
                is_active=True
            ).count(),
            'last_login': request.user.last_login.isoformat() if request.user.last_login else None,
            'date_joined': request.user.date_joined.isoformat()
        })
        
        return Response({
            'success': True,
            'profile': profile_data
        })
        
    except Exception as e:
        logger.error(f"Error fetching user profile: {e}")
        return Response({
            'success': False,
            'error': 'Failed to fetch profile'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['PATCH'])
@login_required
def update_profile(request):
    """Update user profile settings"""
    
    try:
        serializer = UserProfileSerializer(
            request.user, 
            data=request.data, 
            partial=True
        )
        
        if serializer.is_valid():
            serializer.save()
            return Response({
                'success': True,
                'profile': serializer.data,
                'message': 'Profile updated successfully'
            })
        
        return Response({
            'success': False,
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)
        
    except Exception as e:
        logger.error(f"Error updating profile: {e}")
        return Response({
            'success': False,
            'error': 'Failed to update profile'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET'])
@login_required
def wallet_status(request):
    """Get current wallet connection status"""
    
    try:
        active_sessions = WalletSession.objects.filter(
            user=request.user,
            is_active=True
        ).order_by('-created_at')
        
        current_session = active_sessions.first()
        
        status_data = {
            'is_connected': bool(current_session),
            'wallet_address': current_session.wallet_address if current_session else None,
            'chain_id': current_session.chain_id if current_session else None,
            'wallet_type': request.user.wallet_type if hasattr(request.user, 'wallet_type') else 'unknown',
            'is_correct_network': current_session.chain_id == 8453 if current_session else False,
            'session_count': active_sessions.count(),
            'last_connection': current_session.created_at.isoformat() if current_session else None
        }
        
        return Response({
            'success': True,
            'status': status_data
        })
        
    except Exception as e:
        logger.error(f"Error fetching wallet status: {e}")
        return Response({
            'success': False,
            'error': 'Failed to fetch wallet status'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def verify_wallet_ownership(request):
    """Verify wallet ownership without full authentication"""
    
    try:
        wallet_address = Web3Utils.format_wallet_address(request.data.get('wallet_address'))
        signature = request.data.get('signature')
        message = request.data.get('message')
        
        if not all([wallet_address, signature, message]):
            return Response({
                'success': False,
                'error': 'Missing required fields'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        is_valid = Web3Utils.verify_signature(message, signature, wallet_address)
        
        return Response({
            'success': True,
            'is_valid': is_valid,
            'wallet_address': wallet_address
        })
        
    except Exception as e:
        logger.error(f"Wallet verification failed: {e}")
        return Response({
            'success': False,
            'error': 'Verification failed'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

# Enhanced middleware for Web3 authentication
class Web3AuthenticationMiddleware:
    """Middleware to handle Web3 authentication alongside traditional auth"""
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        # Check for Web3 token in headers
        auth_header = request.META.get('HTTP_AUTHORIZATION', '')
        
        if auth_header.startswith('Bearer ') and not request.user.is_authenticated:
            token = auth_header.split(' ')[1]
            try:
                token_obj = Token.objects.select_related('user').get(key=token)
                if token_obj.user.is_active:
                    request.user = token_obj.user
                    request._cached_user = token_obj.user
            except Token.DoesNotExist:
                pass
        
        response = self.get_response(request)
        return response

# Enhanced authentication backend
class Web3AuthenticationBackend:
    """Custom authentication backend for Web3 users"""
    
    def authenticate(self, request, wallet_address=None, signature=None, message=None):
        if not all([wallet_address, signature, message]):
            return None
        
        wallet_address = Web3Utils.format_wallet_address(wallet_address)
        
        # Verify signature
        if not Web3Utils.verify_signature(message, signature, wallet_address):
            return None
        
        try:
            user = User.objects.get(wallet_address=wallet_address, is_active=True)
            return user
        except User.DoesNotExist:
            return None
    
    def get_user(self, user_id):
        try:
            return User.objects.get(pk=user_id, is_active=True)
        except User.DoesNotExist:
            return None

# View decorators for Web3 authentication
from functools import wraps

def web3_login_required(view_func):
    """Decorator that requires Web3 authentication"""
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            if request.headers.get('Accept') == 'application/json':
                return JsonResponse({
                    'success': False,
                    'error': 'Authentication required',
                    'login_required': True
                }, status=401)
            else:
                return redirect('web3_login_required')
        
        # Check if user has Web3 verification
        if hasattr(request.user, 'is_web3_verified') and not request.user.is_web3_verified:
            if request.headers.get('Accept') == 'application/json':
                return JsonResponse({
                    'success': False,
                    'error': 'Web3 verification required',
                    'web3_verification_required': True
                }, status=401)
            else:
                return redirect('web3_verification_required')
        
        return view_func(request, *args, **kwargs)
    
    return _wrapped_view

def require_correct_network(view_func):
    """Decorator that requires user to be on the correct network"""
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if request.user.is_authenticated:
            # Check if user's preferred chain is correct
            if hasattr(request.user, 'preferred_chain_id') and request.user.preferred_chain_id != 8453:
                if request.headers.get('Accept') == 'application/json':
                    return JsonResponse({
                        'success': False,
                        'error': 'Please switch to Base network',
                        'network_switch_required': True,
                        'required_chain_id': 8453,
                        'current_chain_id': request.user.preferred_chain_id
                    }, status=400)
        
        return view_func(request, *args, **kwargs)
    
    return _wrapped_view