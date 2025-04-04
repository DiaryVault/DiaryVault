from django.contrib.auth import views as auth_views
from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('signup/', views.signup, name='signup'),
    path('login/', auth_views.LoginView.as_view(template_name='auth/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='login'), name='logout'),
    path('biography/', views.biography, name='biography'),
    path('regenerate-summary/<int:entry_id>/', views.regenerate_summary, name='regenerate_summary'),
    path('restore-summary/<int:version_id>/', views.restore_summary, name='restore_summary'),
    path('ai-entry/', views.generate_ai_entry, name='ai_entry'),
    path('stream-summary/<int:entry_id>/', views.stream_summary, name='stream_summary'),
]
