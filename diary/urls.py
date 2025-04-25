from django.urls import path
from django.contrib.auth import views as auth_views
from . import views
from .views import CustomLoginView
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    # Main Page
    path('', views.home, name='home'),
    path('signup/', views.signup, name='signup'),
    path('login/', views.custom_login, name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('api/demo-journal/', views.demo_journal, name='demo_journal'),
    path('preferences/', views.preferences, name='preferences'),
    path('save-generated-entry/', views.save_generated_entry, name='save_generated_entry'),
    path('login/', CustomLoginView.as_view(template_name='diary/login.html'), name='login'),


    # Dashboard
    path('dashboard/', views.dashboard, name='dashboard'),

    # Entries
    path('journal/', views.journal, name='new_entry'),
    path('entry/new/', views.journal, name='new_entry'),
    path('entry/<int:entry_id>/', views.entry_detail, name='entry_detail'),
    path('entry/<int:entry_id>/edit/', views.edit_entry, name='edit_entry'),
    path('entry/<int:entry_id>/delete/', views.delete_entry, name='delete_entry'),

    # Chapter management
    path('manage-chapters/', views.user.manage_chapters, name='manage_chapters'),
    path('create-chapter/', views.user.create_chapter, name='create_chapter'),
    path('update-chapter/', views.user.update_chapter, name='update_chapter'),
    path('close-chapter/<int:chapter_id>/', views.user.close_chapter, name='close_chapter'),
    path('reactivate-chapter/<int:chapter_id>/', views.user.reactivate_chapter, name='reactivate_chapter'),
    path('delete-chapter/<int:chapter_id>/', views.user.delete_chapter, name='delete_chapter'),

    # Library
    path('library/', views.library, name='library'),
    path('library/time-period/<str:period>/', views.time_period_view, name='time_period'),


    # Biography URLs
    path('biography/', views.biography, name='biography'),
    path('biography/manage-chapters/', views.manage_chapters, name='manage_chapters'),
    path('biography/edit-chapter/<int:chapter_id>/', views.edit_chapter, name='edit_chapter'),
    path('biography/delete-chapter/<int:chapter_id>/', views.delete_chapter, name='delete_chapter'),
    path('biography/regenerate-chapter/<int:chapter_id>/', views.regenerate_chapter, name='regenerate_chapter'),
    path('api/biography/generate/', views.generate_biography_api, name='generate_biography_api'),


    # User Settings
    path('account/settings/', views.account_settings, name='account_settings'),

    # Insights
    path('insights/', views.insights, name='insights'),

    # AJAX endpoints
    path('api/entry/<int:entry_id>/regenerate-summary/', views.regenerate_summary_ajax, name='regenerate_summary_ajax'),

    # Marketplace Feature
    path('marketplace/', views.marketplace_view, name='marketplace'),
    path('marketplace/publish/', views.marketplace_publish, name='publish'),
    path('marketplace/monetization/', views.marketplace_monetization, name='monetization'),
    path('marketplace/contest/', views.marketplace_contest, name='contest'),
    path('marketplace/faq/', views.marketplace_faq, name='faq'),
    path('marketplace/journal/<int:journal_id>/', views.marketplace_journal_detail, name='journal_detail'),
    path('marketplace/author/<str:username>/', views.marketplace_author_profile, name='author_profile'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
