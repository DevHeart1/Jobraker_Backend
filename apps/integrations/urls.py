"""
URL patterns for integrations app.
"""

from django.urls import path

from . import views

urlpatterns = [
    # API status and management
    path("status/", views.ApiStatusView.as_view(), name="api_status"),
    path("sync/", views.JobSyncView.as_view(), name="job_sync"),
    # Webhooks
    path("webhooks/<str:service>/", views.WebhookView.as_view(), name="webhook"),
]
