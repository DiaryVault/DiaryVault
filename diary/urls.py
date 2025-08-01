from django.urls import path, include
from django.contrib.auth import views as auth_views
from django.views.generic import RedirectView, TemplateView
from django.contrib.staticfiles.storage import staticfiles_storage
from django.conf import settings
from django.conf.urls.static import static
from .views import core
from .views.core import CustomLoginView, CustomSignupView
from .views.api import save_entry_api 
# from .views import journal_compiler  # REMOVED - no longer needed
from .views import api
from .views import web3_auth  # ADD THIS IMPORT

from . import views

# Web3 auth URLs - Now properly configured
web3_patterns = [
    path('nonce/', web3_auth.request_nonce, name='web3_nonce'),
    path('login/', web3_auth.web3_login, name='web3_login'),
    path('disconnect/', web3_auth.disconnect_wallet, name='web3_disconnect'),
    path('profile/', web3_auth.user_profile, name='web3_profile'),
    path('profile/update/', web3_auth.update_profile, name='web3_update_profile'),
    path('status/', web3_auth.wallet_status, name='web3_wallet_status'),
    path('verify/', web3_auth.verify_wallet_ownership, name='web3_verify'),
]

urlpatterns = [
    # ============================================================================
    # Authentication - These MUST come FIRST to override allauth
    # ============================================================================

    # Signup URLs - both paths point to CustomSignupView
    path('signup/', CustomSignupView.as_view(), name='signup'),
    path('accounts/signup/', CustomSignupView.as_view(), name='account_signup'),

    # Login URLs - both paths point to CustomLoginView
    path('login/', CustomLoginView.as_view(), name='account_login'),
    path('login/', CustomLoginView.as_view(), name='login'),  # For mobile menu compatibility
    path('accounts/login/', CustomLoginView.as_view(), name='account_login'),

    # Web3 Authentication URLs - PROPERLY CONFIGURED
    path('api/web3/', include(web3_patterns)),
    # Web3 Auth endpoints
    path('api/request-nonce/', web3_auth.request_nonce, name='request_nonce'),
    path('api/web3-login/', web3_auth.web3_login, name='web3_login'),
    path('api/disconnect-wallet/', web3_auth.disconnect_wallet, name='disconnect_wallet'),
    path('api/wallet-status/', web3_auth.wallet_status, name='wallet_status'),
    path('api/user-profile/', web3_auth.user_profile, name='user_profile'),
    path('api/update-profile/', web3_auth.update_profile, name='update_profile'),
    path('api/save-generated-entry/', api.save_generated_entry, name='save_generated_entry'),
    path('api/save-entry/', views.save_entry_api, name='save_entry_api'),
    path('api/save-entry/', save_entry_api, name='save_entry_api'),
    path('api/user-stats/', user_stats, name='user_stats'),


    # ============================================================================
    # Main Pages
    # ============================================================================
    path('', views.home, name='home'),

    # Authentication - other auth URLs
    path('logout/', auth_views.LogoutView.as_view(next_page='/login/'), name='logout'),
    path('password-reset/', auth_views.PasswordResetView.as_view(), name='password_reset'),

    # ============================================================================
    # Legal and Policy Pages
    # ============================================================================
    path('privacy/', TemplateView.as_view(template_name='legal/privacy_policy.html'), name='privacy_policy'),

    # ============================================================================
    # Dashboard & Main App
    # ============================================================================
    path('dashboard/', views.dashboard, name='dashboard'),

    # ============================================================================
    # Journal Entries
    # ============================================================================
    path('journal/', views.journal, name='new_entry'),
    path('entry/new/', views.journal, name='new_entry'),  # Alternative URL
    path('new_entry/', views.journal, name='new_entry_alt'),
    
    # UPDATED: Now accepts both integer IDs and UUIDs
    path('entry/<str:entry_id>/', views.entry_detail, name='entry_detail'),
    path('entry/<str:entry_id>/edit/', views.edit_entry, name='edit_entry'),
    path('entry/<str:entry_id>/delete/', views.delete_entry, name='delete_entry'),
    
    path('api/chat/', views.chat_with_ai, name='chat_with_ai'),

    # ============================================================================
    # Library & Time Periods
    # ============================================================================
    path('library/', views.library, name='library'),
    path('library/time-period/<str:period>/', views.time_period_view, name='time_period'),

    # ============================================================================
    # Insights & Analytics
    # ============================================================================
    path('insights/', views.insights, name='insights'),

    # ============================================================================
    # API Endpoints - Core Functionality
    # ============================================================================
    # Journal Generation & Management
    path('api/demo-journal/', views.demo_journal, name='demo_journal'),
    path('save-generated-entry/', views.save_generated_entry, name='save_generated_entry'),

    # Entry Management API
    path('api/entry/<int:entry_id>/regenerate-summary/', views.regenerate_summary_ajax, name='regenerate_summary_ajax'),

    # ============================================================================
    # SMART JOURNAL COMPILER - API Endpoints (KEPT for now - these use api views)
    # ============================================================================
    # Main compilation endpoints - these match what your JavaScript calls
    path('diary/api/analyze-entries/', api.analyze_entries_ajax, name='analyze_entries_ajax'),

    # Draft management
    path('diary/api/save-draft/', api.save_journal_draft, name='save_journal_draft'),
    path('diary/api/load-draft/', api.load_journal_draft, name='load_journal_draft'),

    # ============================================================================
    # Anonymous User Support URLs (Need to add these functions to api.py)
    # ============================================================================
    path('connect-wallet-session/', api.connect_wallet_session, name='connect_wallet_session'),
    path('web3/complete-profile/', api.web3_complete_profile, name='web3_complete_profile'),
    path('entry/preview/<uuid:entry_uuid>/', api.anonymous_entry_preview, name='anonymous_entry_preview'),
    
    # REMOVED: This line was causing the error
    # path('entry/<uuid:entry_uuid>/', views.entry_detail_uuid, name='entry_detail_uuid'),

    # ============================================================================
    # Account Management
    # ============================================================================
    path('accounts/settings/', views.account_settings, name='account_settings'),
    path('preferences/', views.preferences, name='preferences'),

    # ============================================================================
    # Static File Handling
    # ============================================================================
    # Favicon (fixes your 404 error)
    path('favicon.ico', RedirectView.as_view(
        url=staticfiles_storage.url('favicon.ico'),
        permanent=True
    ), name='favicon'),

    # ============================================================================
    # Sitemap and SEO
    # ============================================================================
]

# Serve media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)