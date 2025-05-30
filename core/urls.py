# core/urls.py
from django.contrib import admin
from django.urls import path, include
from django.views.generic import RedirectView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/', include('allauth.urls')),  

    # Add redirects for common URLs
    path('login/', RedirectView.as_view(url='/accounts/login/', permanent=True), name='login_redirect'),
    path('signup/', RedirectView.as_view(url='/accounts/signup/', permanent=True), name='signup_redirect'),
    path('logout/', RedirectView.as_view(url='/accounts/logout/', permanent=True), name='logout_redirect'),

    # Your existing patterns
    path('', include('diary.urls')),
]
