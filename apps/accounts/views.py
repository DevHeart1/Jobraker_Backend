from django.shortcuts import render
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from django.contrib.auth import get_user_model
from .models import UserProfile

User = get_user_model()


class UserViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing users.
    """
    queryset = User.objects.all()
    permission_classes = [permissions.IsAuthenticated]
    
    def get_permissions(self):
        """
        Instantiates and returns the list of permissions that this view requires.
        """
        if self.action == 'create':
            permission_classes = [permissions.AllowAny]
        else:
            permission_classes = [permissions.IsAuthenticated]
        return [permission() for permission in permission_classes]


class UserProfileViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing user profiles.
    """
    queryset = UserProfile.objects.all()
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        """
        This view should return the profile for the currently authenticated user.
        """
        return UserProfile.objects.filter(user=self.request.user)


class RegisterView(APIView):
    """
    View for user registration.
    """
    permission_classes = [permissions.AllowAny]
    
    def post(self, request):
        """
        Register a new user.
        """
        # TODO: Implement user registration logic
        return Response({'message': 'User registration coming soon'})


class ProfileView(APIView):
    """
    View for user profile management.
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        """
        Get user profile.
        """
        # TODO: Implement profile retrieval
        return Response({'message': 'Profile retrieval coming soon'})
    
    def put(self, request):
        """
        Update user profile.
        """
        # TODO: Implement profile update
        return Response({'message': 'Profile update coming soon'})
