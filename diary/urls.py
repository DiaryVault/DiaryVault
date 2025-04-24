from django.urls import path
from django.contrib.auth import views as auth_views
from . import views
from .views import CustomLoginView

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

    # Chapters
    path('chapters/', views.manage_chapters, name='manage_chapters'),
    path('chapters/<int:chapter_id>/edit/', views.edit_chapter, name='edit_chapter'),
    path('chapters/<int:chapter_id>/delete/', views.delete_chapter, name='delete_chapter'),
    path('entry/<int:entry_id>/assign-chapters/', views.assign_to_chapter, name='assign_to_chapter'),

    # Library
    path('library/', views.library, name='library'),
    path('library/time-period/<str:period>/', views.time_period_view, name='time_period'),


    # Biography and Insights
    path('biography/', views.biography, name='biography'),
    path('insights/', views.insights, name='insights'),
    path('api/generate-biography/', views.generate_biography_api, name='generate_biography_api'),


    # User Settings
    path('account/settings/', views.account_settings, name='account_settings'),

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
