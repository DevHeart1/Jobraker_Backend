"""
URL patterns for notifications app.
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

# Router for ViewSets
router = DefaultRouter()
router.register(r'notifications', views.NotificationViewSet, basename='notification')

urlpatterns = [
    # Notification management
    path('settings/', views.NotificationSettingsView.as_view(), name='settings'),
    
    # Include router URLs
    path('', include(router.urls)),
]
