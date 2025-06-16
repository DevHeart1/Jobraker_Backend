"""
URL patterns for chat app.
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

# Router for ViewSets
router = DefaultRouter()
router.register(r'sessions', views.ChatSessionViewSet, basename='chatsession')

urlpatterns = [
    # Chat endpoints
    path('send/', views.ChatView.as_view(), name='chat'),
    path('advice/', views.JobAdviceView.as_view(), name='job_advice'),
    
    # Include router URLs
    path('', include(router.urls)),
]
