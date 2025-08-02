from django.urls import path, include
from django.contrib.auth import views as auth_views
from django.views.generic import RedirectView, TemplateView
from django.contrib.staticfiles.storage import staticfiles_storage
from django.conf import settings
from django.conf.urls.static import static
from .views import core
from .views.core import CustomLoginView, CustomSignupView
from .views.api import save_entry_api, user_stats, recent_entries
from .views import api
from .views import web3_auth
from . import views

# ============================================================================
# Web3 Authentication Pattern Groups
# ============================================================================
web3_auth_patterns = [
    # Core Web3 authentication
    path('nonce/', web3_auth.request_nonce, name='web3_nonce'),
    path('login/', web3_auth.web3_login, name='web3_login'),
    path('logout/', web3_auth.disconnect_wallet, name='web3_logout'),
    path('verify/', web3_auth.verify_wallet_ownership, name='web3_verify'),
    
    # Wallet management
    path('connect/', api.wallet_connect_api, name='wallet_connect'),
    path('disconnect/', web3_auth.disconnect_wallet, name='web3_disconnect'),
    path('status/', web3_auth.wallet_status, name='web3_status'),
    
    # User profile management
    path('profile/', web3_auth.user_profile, name='web3_profile'),
    path('profile/update/', web3_auth.update_profile, name='web3_profile_update'),
    path('profile/complete/', api.web3_complete_profile, name='web3_complete_profile'),
]

# Token rewards API patterns
token_rewards_patterns = [
    path('balance/', api.get_token_balance, name='token_balance'),
    path('history/', api.get_reward_history, name='reward_history'),
    path('claim/', api.claim_rewards, name='claim_rewards'),
]

# Anonymous user API patterns
anonymous_api_patterns = [
    path('session/connect-wallet/', api.connect_wallet_session, name='connect_wallet_session'),
    path('entry/preview/<uuid:entry_uuid>/', api.anonymous_entry_preview, name='anonymous_entry_preview'),
]

urlpatterns = [
    # ============================================================================
    # Main Pages - MUST come first
    # ============================================================================
    path('', views.home, name='home'),
    
    # ============================================================================
    # Authentication - Override allauth defaults
    # ============================================================================
    # Signup URLs
    path('signup/', CustomSignupView.as_view(), name='signup'),
    path('accounts/signup/', CustomSignupView.as_view(), name='account_signup'),

    # Login URLs
    path('login/', CustomLoginView.as_view(), name='login'),
    path('accounts/login/', CustomLoginView.as_view(), name='account_login'),
    
    # Logout
    path('logout/', auth_views.LogoutView.as_view(next_page='/login/'), name='logout'),
    path('accounts/logout/', auth_views.LogoutView.as_view(next_page='/login/'), name='account_logout'),
    
    # Password reset
    path('password-reset/', auth_views.PasswordResetView.as_view(), name='password_reset'),

    # ============================================================================
    # Web3 Authentication URLs - Organized
    # ============================================================================
    path('api/web3/', include(web3_auth_patterns)),
    path('api/rewards/', include(token_rewards_patterns)),
    path('api/anonymous/', include(anonymous_api_patterns)),
    
    # Legacy API endpoints (for backward compatibility)
    path('api/request-nonce/', web3_auth.request_nonce, name='request_nonce'),
    path('api/web3-login/', web3_auth.web3_login, name='web3_login_api'),
    path('api/disconnect-wallet/', web3_auth.disconnect_wallet, name='disconnect_wallet'),
    path('api/wallet-status/', web3_auth.wallet_status, name='wallet_status'),
    path('api/user-profile/', web3_auth.user_profile, name='user_profile'),
    path('api/update-profile/', web3_auth.update_profile, name='update_profile'),

    # ============================================================================
    # Dashboard & Main App
    # ============================================================================
    path('dashboard/', views.dashboard, name='dashboard'),

    # ============================================================================
    # Journal Entries
    # ============================================================================
    path('journal/', views.journal, name='journal'),
    path('entry/new/', views.journal, name='new_entry'),
    path('new_entry/', views.journal, name='new_entry_alt'),  # Legacy URL
    
    # Entry detail, edit, delete - supports both int and UUID
    path('entry/<str:entry_id>/', views.entry_detail, name='entry_detail'),
    path('entry/<str:entry_id>/edit/', views.edit_entry, name='edit_entry'),
    path('entry/<str:entry_id>/delete/', views.delete_entry, name='delete_entry'),

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
    # API Endpoints - Journal & Entry Management
    # ============================================================================
    # Core entry API
    path('api/save-entry/', save_entry_api, name='save_entry_api'),
    path('api/save-generated-entry/', api.save_generated_entry, name='save_generated_entry'),
    path('api/user-stats/', user_stats, name='user_stats'),
    path('api/recent-entries/', recent_entries, name='recent_entries'),
    
    # AI Chat
    path('api/chat/', views.chat_with_ai, name='chat_with_ai'),
    
    # Demo & Generation
    path('api/demo-journal/', views.demo_journal, name='demo_journal'),
    path('save-generated-entry/', views.save_generated_entry, name='save_generated_entry_legacy'),
    
    # Entry management
    path('api/entry/<int:entry_id>/regenerate-summary/', views.regenerate_summary_ajax, name='regenerate_summary_ajax'),

    # ============================================================================
    # Smart Journal Compiler API
    # ============================================================================
    path('diary/api/analyze-entries/', api.analyze_entries_ajax, name='analyze_entries_ajax'),
    path('diary/api/save-draft/', api.save_journal_draft, name='save_journal_draft'),
    path('diary/api/load-draft/', api.load_journal_draft, name='load_journal_draft'),

    # ============================================================================
    # Account Management
    # ============================================================================
    path('accounts/settings/', views.account_settings, name='account_settings'),
    path('preferences/', views.preferences, name='preferences'),

    # ============================================================================
    # Legal and Policy Pages
    # ============================================================================
    path('privacy/', TemplateView.as_view(template_name='legal/privacy_policy.html'), name='privacy_policy'),
    path('terms/', TemplateView.as_view(template_name='legal/terms_of_service.html'), name='terms_of_service'),

    # ============================================================================
    # Static File Handling
    # ============================================================================
    path('favicon.ico', RedirectView.as_view(
        url=staticfiles_storage.url('favicon.ico'),
        permanent=True
    ), name='favicon'),

    # ============================================================================
    # Allauth URLs (must come after custom overrides)
    # ============================================================================
    path('accounts/', include('allauth.urls')),
]

# Serve media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)