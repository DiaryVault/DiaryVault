from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

# Import your custom view
from diary.views import CustomLoginView

urlpatterns = [
    path('admin/', admin.site.urls),

    # IMPORTANT: Override allauth login BEFORE including allauth.urls
    path('accounts/login/', CustomLoginView.as_view(), name='account_login'),

    # Include your app URLs
    path('', include('diary.urls')),

    # Include allauth URLs (login will be overridden by the above)
    path('accounts/', include('allauth.urls')),
]

# Serve media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
