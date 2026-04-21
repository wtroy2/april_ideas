"""URL configuration for the Critter backend."""

from django.contrib import admin
from django.urls import path, include
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

urlpatterns = [
    path('admin/', admin.site.urls),

    # Convenience tokens at root (frontend can also use /api/users/token/)
    path('token/', TokenObtainPairView.as_view(), name='get_token'),
    path('token/refresh/', TokenRefreshView.as_view(), name='refresh_token'),

    # App URLs
    path('api/users/', include('users.urls')),
    path('api/orgs/', include('orgs.urls')),
    path('api/analytics/', include('analytics.urls')),
    path('api/subjects/', include('subjects.urls')),
    path('api/themes/', include('themes.urls')),
    path('api/assets/', include('assets.urls')),
    path('api/generations/', include('generations.urls')),
    path('api/stories/', include('stories.urls')),
    path('api/billing/', include('billing.urls')),

    # RQ admin dashboard (lock down with admin permission via django-rq config in prod)
    path('django-rq/', include('django_rq.urls')),
]
