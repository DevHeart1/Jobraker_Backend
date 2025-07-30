"""
URL patterns for notifications app.
"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views
from .health_checks import health_check, metrics, test_endpoint
from .production_health import (production_action, production_health_check,
                                production_metrics)

# Router for ViewSets
router = DefaultRouter()
router.register(r"notifications", views.NotificationViewSet, basename="notification")

urlpatterns = [
    # Notification management
    path("settings/", views.NotificationSettingsView.as_view(), name="settings"),
    # Health check and monitoring endpoints
    path("health/", health_check, name="health-check"),
    path("health/production/", production_health_check, name="production-health"),
    path("metrics/", metrics, name="metrics"),
    path("metrics/production/", production_metrics, name="production-metrics"),
    path("test/", test_endpoint, name="test-endpoint"),
    path("admin/action/", production_action, name="production-action"),
    # Include router URLs
    path("", include(router.urls)),
]
