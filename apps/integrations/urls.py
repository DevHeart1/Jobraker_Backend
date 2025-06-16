"""
URL patterns for integrations app.
"""

from django.urls import path
from . import views

urlpatterns = [
    # External API integrations
    path('adzuna/sync/', views.AdzunaJobSyncView.as_view(), name='adzuna_sync'),
    path('skyvern/status/', views.SkyvernStatusView.as_view(), name='skyvern_status'),
    path('openai/usage/', views.OpenAIUsageView.as_view(), name='openai_usage'),
    
    # Webhooks
    path('webhooks/skyvern/', views.SkyvernWebhookView.as_view(), name='skyvern_webhook'),
    path('webhooks/adzuna/', views.AdzunaWebhookView.as_view(), name='adzuna_webhook'),
]
