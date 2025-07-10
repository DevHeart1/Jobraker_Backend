"""
URL patterns for notifications app.
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views
from .health_checks import health_check, metrics, test_endpoint

# Router for ViewSets
router = DefaultRouter()
router.register(r'notifications', views.NotificationViewSet, basename='notification')

urlpatterns = [
    # Notification management
    path('settings/', views.NotificationSettingsView.as_view(), name='settings'),
    
    # Health check and monitoring endpoints
    path('health/', health_check, name='health-check'),
    path('test/', test_endpoint, name='test-endpoint'),
    path('metrics/', metrics, name='metrics'),
    
    # Include router URLs
    path('', include(router.urls)),
]
