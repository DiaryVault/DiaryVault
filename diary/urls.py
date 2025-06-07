from django.urls import path
from django.contrib.auth import views as auth_views
from django.views.generic import RedirectView, TemplateView
from django.contrib.staticfiles.storage import staticfiles_storage
from django.conf import settings
from django.conf.urls.static import static
from .views import core
from .views.core import CustomLoginView, CustomSignupView
from .views.marketplace import (
    marketplace_view, publish_journal, marketplace_journal_detail,
    like_journal, tip_author, marketplace_author_profile,
    marketplace_monetization, marketplace_contest, marketplace_faq,
    purchase_journal_api, tip_author_api, earnings_dashboard,
    publish_biography, my_published_journals
)
from .views import journal_compiler, marketplace_views
from .views import api

from . import views

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

    # ============================================================================
    # Main Pages
    # ============================================================================
    path('', views.home, name='home'),

    # Authentication - other auth URLs
    path('logout/', auth_views.LogoutView.as_view(next_page='/login/'), name='logout'),
    path('password-reset/', auth_views.PasswordResetView.as_view(), name='password_reset'),

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
    # Life Chapters Management
    # ============================================================================
    path('manage-chapters/', views.user.manage_chapters, name='manage_chapters'),
    path('create-chapter/', views.user.create_chapter, name='create_chapter'),
    path('update-chapter/', views.user.update_chapter, name='update_chapter'),
    path('close-chapter/<int:chapter_id>/', views.user.close_chapter, name='close_chapter'),
    path('reactivate-chapter/<int:chapter_id>/', views.user.reactivate_chapter, name='reactivate_chapter'),
    path('delete-chapter/<int:chapter_id>/', views.user.delete_chapter, name='delete_chapter'),

    # ============================================================================
    # Biography Feature
    # ============================================================================
    path('biography/', views.biography, name='biography'),
    path('biography/manage-chapters/', views.manage_chapters, name='manage_chapters'),
    path('biography/edit-chapter/<int:chapter_id>/', views.edit_chapter, name='edit_chapter'),
    path('biography/delete-chapter/<int:chapter_id>/', views.delete_chapter, name='delete_chapter'),
    path('biography/regenerate-chapter/<int:chapter_id>/', views.regenerate_chapter, name='regenerate_chapter'),

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
    path('marketplace/publish/', publish_journal, name='publish_journal'),
    path('marketplace/publish-biography/', publish_biography, name='publish_biography'),

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
    path('publish/preview-structure/', journal_compiler.preview_journal_structure, name='preview_journal_structure'),

    # ============================================================================
    # API Endpoints - Core Functionality
    # ============================================================================
    # Journal Generation & Management
    path('api/demo-journal/', views.demo_journal, name='demo_journal'),
    path('save-generated-entry/', views.save_generated_entry, name='save_generated_entry'),

    # Biography API
    path('api/biography/generate/', views.generate_biography_api, name='generate_biography_api'),

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

    # ============================================================================
    # Static File Handling
    # ============================================================================
    # Favicon (fixes your 404 error)
    path('favicon.ico', RedirectView.as_view(
        url=staticfiles_storage.url('favicon.ico'),
        permanent=True
    ), name='favicon'),
]

# Serve media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
