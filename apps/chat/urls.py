"""
URL patterns for chat app.
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

# Router for ViewSets
router = DefaultRouter()
router.register(r'conversations', views.ConversationViewSet, basename='conversation')
router.register(r'messages', views.MessageViewSet, basename='message')

urlpatterns = [
    # Chat endpoints
    path('send/', views.SendMessageView.as_view(), name='send_message'),
    path('ai-reply/', views.AIReplyView.as_view(), name='ai_reply'),
    
    # Include router URLs
    path('', include(router.urls)),
]
