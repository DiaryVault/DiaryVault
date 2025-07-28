from django.urls import path, include
from django.contrib.auth import views as auth_views
from django.views.generic import RedirectView, TemplateView
from django.contrib.staticfiles.storage import staticfiles_storage
from django.conf import settings
from django.conf.urls.static import static
from .views import core
from .views.core import CustomLoginView, CustomSignupView
from .views import journal_compiler
from .views import api

from . import views

# Web3 auth URLs - Updated to use existing api views
# web3_patterns = [
#     path('nonce/', api.request_nonce, name='web3_nonce'),
#     path('login/', api.web3_login, name='web3_login'),
#     path('disconnect/', api.disconnect_wallet, name='web3_disconnect'),
#     path('profile/', api.user_profile, name='web3_profile'),
#     path('profile/update/', api.update_profile, name='web3_update_profile'),
#     path('health/', api.health_check, name='web3_health'),
# ]

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

    # Web3 Authentication URLs - Updated to use connect wallet view from core
    # path('connect-wallet/', core.connect_wallet_view, name='connect_wallet'),
    # path('api/web3/', include(web3_patterns)),

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
    path('entry/<int:entry_id>/', views.entry_detail, name='entry_detail'),
    path('entry/<int:entry_id>/edit/', views.edit_entry, name='edit_entry'),
    path('entry/<int:entry_id>/delete/', views.delete_entry, name='delete_entry'),

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
    # Marketplace Feature
    # ============================================================================
    # Main marketplace
    path('marketplace/', marketplace_view, name='marketplace'),

    # Publishing functionality
    path('marketplace/publish/', journal_compiler.smart_journal_compiler, name='publish_journal'),

    # Journal detail and interactions
    path('marketplace/journal/<int:journal_id>/', marketplace_journal_detail, name='marketplace_journal_detail'),
    path('marketplace/like/<int:journal_id>/', like_journal, name='like_journal'),
    path('marketplace/tip/<int:journal_id>/', tip_author, name='tip_author'),

    # Author profiles and dashboards
    path('marketplace/author/<str:username>/', marketplace_author_profile, name='marketplace_author_profile'),
    path('dashboard/earnings/', earnings_dashboard, name='earnings_dashboard'),
    path('dashboard/my-journals/', my_published_journals, name='my_published_journals'),

    # Additional marketplace pages
    path('marketplace/monetization/', marketplace_monetization, name='marketplace_monetization'),
    path('marketplace/contest/', marketplace_contest, name='marketplace_contest'),
    path('marketplace/faq/', marketplace_faq, name='marketplace_faq'),

    # ============================================================================
    # SMART JOURNAL COMPILER - Main Pages
    # ============================================================================
    path('publish_journal/', journal_compiler.smart_journal_compiler, name='smart_journal_compiler'),
    path('publish/smart-compiler/', journal_compiler.smart_journal_compiler, name='smart_journal_compiler_alt'),
    path('smart-compiler/', journal_compiler.smart_journal_compiler, name='smart_journal_compiler'),  # Add this line
    path('publish/preview-structure/', journal_compiler.preview_journal_structure, name='preview_journal_structure'),

    # ============================================================================
    # API Endpoints - Core Functionality
    # ============================================================================
    # Journal Generation & Management
    path('api/demo-journal/', views.demo_journal, name='demo_journal'),
    path('save-generated-entry/', views.save_generated_entry, name='save_generated_entry'),

    # Entry Management API
    path('api/entry/<int:entry_id>/regenerate-summary/', views.regenerate_summary_ajax, name='regenerate_summary_ajax'),

    # Marketplace API
    path('api/track-view/<int:journal_id>/', core.track_journal_view, name='track_journal_view'),
    path('api/wishlist/add/', core.add_to_wishlist, name='add_to_wishlist'),
    path('api/wishlist/remove/', core.remove_from_wishlist, name='remove_from_wishlist'),
    path('api/journal-preview/<int:journal_id>/', core.journal_preview, name='journal_preview'),
    path('api/marketplace-stats/', core.marketplace_stats, name='marketplace_stats'),

    # Enhanced marketplace APIs
    path('api/purchase/<int:journal_id>/', purchase_journal_api, name='purchase_journal_api'),
    path('api/tip/<int:journal_id>/', tip_author_api, name='tip_author_api'),

    # ============================================================================
    # SMART JOURNAL COMPILER - API Endpoints (FIXED)
    # ============================================================================
    # Main compilation endpoints - these match what your JavaScript calls
    path('diary/api/analyze-entries/', api.analyze_entries_ajax, name='analyze_entries_ajax'),
    path('diary/api/generate-structure/', api.generate_journal_structure, name='generate_journal_structure'),
    path('diary/api/publish-journal/', api.publish_compiled_journal, name='publish_compiled_journal'),

    # Draft management
    path('diary/api/save-draft/', api.save_journal_draft, name='save_journal_draft'),
    path('diary/api/load-draft/', api.load_journal_draft, name='load_journal_draft'),

    # Marketing and analytics
    path('diary/api/marketing-copy/', api.generate_marketing_copy, name='generate_marketing_copy'),
    path('diary/api/quick-analyze/', api.quick_analyze_for_publishing, name='quick_analyze_for_publishing'),
    path('diary/api/price-suggestion/', api.get_price_suggestion, name='get_price_suggestion'),
    path('diary/api/validate-journal/', api.validate_journal_data, name='validate_journal_data'),
    path('diary/api/templates/', api.get_journal_templates_api, name='get_journal_templates_api'),

    # Alternative endpoints that point to journal_compiler views (for backend use)
    path('diary/compiler/analyze-entries/', journal_compiler.analyze_entries_ajax, name='compiler_analyze_entries_ajax'),
    path('diary/compiler/generate-structure/', journal_compiler.generate_journal_structure, name='compiler_generate_journal_structure'),
    path('diary/compiler/publish/', journal_compiler.publish_compiled_journal, name='compiler_publish_compiled_journal'),

    # ============================================================================
    # Account Management
    # ============================================================================
    path('accounts/settings/', views.account_settings, name='account_settings'),
    path('preferences/', views.preferences, name='preferences'),

    path('journal/<int:journal_id>/edit/', views.edit_journal, name='edit_journal'),

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