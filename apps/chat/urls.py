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
    path('send/', views.SendMessageView.as_view(), name='send_message'),
    path('chat/', views.SendMessageView.as_view(), name='chat'),  # Alias for tests
    path('advice/', views.JobAdviceView.as_view(), name='job_advice'),
    path('websocket-token/', views.get_websocket_token, name='websocket_token'),
    
    # Include router URLs
    path('', include(router.urls)),
]
