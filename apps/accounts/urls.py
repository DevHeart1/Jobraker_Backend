"""
URL patterns for accounts app.
"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import (TokenObtainPairView,
                                            TokenRefreshView, TokenVerifyView)

from . import views

# Router for ViewSets
router = DefaultRouter()
router.register(r"profiles", views.UserProfileViewSet, basename="userprofile")

urlpatterns = [
    # Authentication
    path("login/", TokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("verify/", TokenVerifyView.as_view(), name="token_verify"),
    path("register/", views.RegisterView.as_view(), name="register"),
    path("logout/", views.LogoutView.as_view(), name="logout"),
    # User management
    path("me/", views.CurrentUserView.as_view(), name="current_user"),
    path(
        "change-password/", views.ChangePasswordView.as_view(), name="change_password"
    ),
    # Profile management
    path("upload-resume/", views.ResumeUploadView.as_view(), name="upload_resume"),
    # Include router URLs
    path("", include(router.urls)),
]
