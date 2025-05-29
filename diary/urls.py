from django.urls import path
from django.contrib.auth import views as auth_views
from django.views.generic import RedirectView
from django.contrib.staticfiles.storage import staticfiles_storage
from django.conf import settings
from django.conf.urls.static import static
from .views import core
from .views.core import CustomLoginView
from .views import marketplace

from . import views
from .views import CustomLoginView

urlpatterns = [
    # ============================================================================
    # Main Pages
    # ============================================================================
    path('', views.home, name='home'),
    path('signup/', views.signup, name='signup'),

    # Authentication
    path('login/', CustomLoginView.as_view(template_name='diary/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('password-reset/', auth_views.PasswordResetView.as_view(), name='password_reset'),

    # User Settings & Preferences
    path('preferences/', views.preferences, name='preferences'),
    path('account/settings/', views.account_settings, name='account_settings'),

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
    path('marketplace/', views.marketplace_view, name='marketplace'),

    # Publishing functionality
    path('marketplace/publish/', views.publish_journal, name='publish_journal'),

    # Journal detail and interactions
    path('marketplace/journal/<int:journal_id>/', views.marketplace_journal_detail, name='marketplace_journal_detail'),
    path('marketplace/like/<int:journal_id>/', views.like_journal, name='like_journal'),
    path('marketplace/tip/<int:journal_id>/', views.tip_author, name='tip_author'),

    # Author profiles
    path('marketplace/author/<str:username>/', views.marketplace_author_profile, name='marketplace_author_profile'),

    # Additional marketplace pages
    path('marketplace/monetization/', views.marketplace_monetization, name='marketplace_monetization'),
    path('marketplace/contest/', views.marketplace_contest, name='marketplace_contest'),
    path('marketplace/faq/', views.marketplace_faq, name='marketplace_faq'),

    # ============================================================================
    # API Endpoints
    # ============================================================================
    # Journal Generation & Management
    path('api/demo-journal/', views.demo_journal, name='demo_journal'),
    path('save-generated-entry/', views.save_generated_entry, name='save_generated_entry'),

    # Biography API
    path('api/biography/generate/', views.generate_biography_api, name='generate_biography_api'),

    # Entry Management API
    path('api/entry/<int:entry_id>/regenerate-summary/', views.regenerate_summary_ajax, name='regenerate_summary_ajax'),

    # Marketplace API (New - from your core.py)
    path('api/track-view/<int:journal_id>/', core.track_journal_view, name='track_journal_view'),
    path('api/wishlist/add/', core.add_to_wishlist, name='add_to_wishlist'),
    path('api/wishlist/remove/', core.remove_from_wishlist, name='remove_from_wishlist'),
    path('api/journal-preview/<int:journal_id>/', core.journal_preview, name='journal_preview'),
    path('api/marketplace-stats/', core.marketplace_stats, name='marketplace_stats'),

    # Enhanced marketplace URLs
    path('marketplace/publish-biography/', views.publish_biography, name='publish_biography'),
    path('api/purchase/<int:journal_id>/', views.purchase_journal_api, name='purchase_journal_api'),
    path('api/tip/<int:journal_id>/', views.tip_author_api, name='tip_author_api'),
    path('dashboard/earnings/', views.earnings_dashboard, name='earnings_dashboard'),
    path('dashboard/my-journals/', views.my_published_journals, name='my_published_journals'),


    # ============================================================================
    # Static File Handling
    # ============================================================================
    # Favicon (fixes your 404 error)
    path('favicon.ico', RedirectView.as_view(
        url=staticfiles_storage.url('favicon.ico'),
        permanent=True
    ), name='favicon'),
]

marketplace_patterns = [
    # Biography Publishing
    path('marketplace/publish-biography/', marketplace.publish_biography, name='publish_biography'),

    # Enhanced Purchase & Tip APIs
    path('api/purchase/<int:journal_id>/', marketplace.purchase_journal_api, name='purchase_journal_api'),
    path('api/tip/<int:journal_id>/', marketplace.tip_author_api, name='tip_author_api'),

    # Author Dashboard
    path('dashboard/earnings/', marketplace.earnings_dashboard, name='earnings_dashboard'),
    path('dashboard/my-journals/', marketplace.my_published_journals, name='my_published_journals'),
]


# Serve media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
