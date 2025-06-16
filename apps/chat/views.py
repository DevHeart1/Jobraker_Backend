from django.shortcuts import render
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response


class ChatViewSet(viewsets.ViewSet):
    """
    ViewSet for chat functionality.
    """
    permission_classes = [permissions.IsAuthenticated]
    
    @action(detail=False, methods=['post'])
    def send_message(self, request):
        """
        Send a message to the AI chat system.
        """
        # TODO: Implement chat functionality
        return Response({'message': 'Chat functionality coming soon'})
    
    @action(detail=False, methods=['get'])
    def history(self, request):
        """
        Get chat history for the current user.
        """
        # TODO: Implement chat history
        return Response({'history': []})
