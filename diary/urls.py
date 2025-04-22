from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    # Main Page
    path('', views.home, name='home'),
    path('signup/', views.signup, name='signup'),
    path('login/', auth_views.LoginView.as_view(template_name='diary/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('api/demo-journal/', views.demo_journal, name='demo_journal'),
    path('preferences/', views.preferences, name='preferences'),

    # Dashboard
    path('dashboard/', views.dashboard, name='dashboard'),

    # Entries
    path('journal/', views.journal, name='new_entry'),  # Updated path but kept the same name
    # Keep this URL pattern to maintain backward compatibility
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

    # User Settings
    path('account/settings/', views.account_settings, name='account_settings'),

    # AJAX endpoints
    path('api/entry/<int:entry_id>/regenerate-summary/', views.regenerate_summary_ajax, name='regenerate_summary_ajax'),
]
