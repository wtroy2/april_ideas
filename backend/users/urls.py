"""URL routes for the users app — mirrors RateRail's structure."""

from django.urls import path
from rest_framework_simplejwt.views import TokenObtainPairView

from . import views

urlpatterns = [
    # Registration + profile
    path('register/', views.register, name='register'),
    path('get_username/', views.get_username, name='get_username'),
    path('user_info/', views.user_info, name='user_info'),
    path('user_info/update/', views.update_user_info, name='update_user_info'),

    # 2FA login flow
    path('auth/initiate-login/', views.initiate_login, name='initiate_login'),
    path('auth/verify-login/', views.verify_login, name='verify_login'),
    path('auth/resend-code/', views.resend_verification_code, name='resend_verification_code'),

    # Password reset + username recovery
    path('auth/forgot-username/', views.forgot_username, name='forgot_username'),
    path('auth/forgot-password/', views.initiate_password_reset, name='initiate_password_reset'),
    path('auth/verify-password-reset/', views.verify_password_reset, name='verify_password_reset'),
    path('auth/resend-password-reset/', views.resend_password_reset_code, name='resend_password_reset_code'),

    # Logout + validate
    path('auth/logout/', views.enhanced_logout, name='enhanced_logout'),
    path('auth/validate-session/', views.validate_session_enhanced, name='validate_session_enhanced'),

    # Sessions
    path('sessions/', views.get_user_sessions, name='get_user_sessions'),
    path('sessions/<int:session_id>/terminate/', views.terminate_session, name='terminate_session'),

    # JWT (frontend hits /api/users/token/refresh/)
    path('token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('token/refresh/', views.EnhancedTokenRefreshView.as_view(), name='token_refresh'),
]
