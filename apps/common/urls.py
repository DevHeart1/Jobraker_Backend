"""
URL patterns for common app.
"""

from django.urls import path
from . import views

urlpatterns = [
    path('health/', views.health_check, name='health_check'),
    path('user-recommendations-status/', views.user_recommendations_status, name='user_recommendations_status'),
]
