from django.shortcuts import render
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from django.contrib.auth import get_user_model, logout
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from rest_framework_simplejwt.tokens import RefreshToken
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiExample
from drf_spectacular.openapi import OpenApiTypes
from .models import UserProfile
from .serializers import (
    UserSerializer, UserProfileSerializer, RegisterSerializer, 
    ChangePasswordSerializer
)

User = get_user_model()


@extend_schema(tags=['Users'])
class UserViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing users.
    
    Provides CRUD operations for user management including:
    - List all users (admin only)
    - Retrieve user details
    - Update user information
    - Delete user account
    """
    queryset = User.objects.all()
    serializer_class = UserSerializer
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


@extend_schema(tags=['User Profiles'])
class UserProfileViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing user profiles.
    
    Handles user profile data including:
    - Personal information
    - Job preferences
    - Skills and experience
    - Availability status
    """
    queryset = UserProfile.objects.all()
    serializer_class = UserProfileSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        """
        This view should return the profile for the currently authenticated user.
        """
        return UserProfile.objects.filter(user=self.request.user)

    @extend_schema(
        description="Retrieve the current user's profile",
        responses={
            200: UserProfileSerializer,
            404: OpenApiExample(
                'Profile Not Found',
                value={'error': 'Profile not found for current user'},
                response_only=True
            )
        }
    )
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @extend_schema(
        description="Update the current user's profile",
        request=UserProfileSerializer,
        responses={
            200: UserProfileSerializer,
            400: OpenApiExample(
                'Validation Error',
                value={'field': ['This field is required.']},
                response_only=True
            )
        }
    )
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)


@extend_schema(tags=['Authentication'])
class RegisterView(APIView):
    """
    User registration endpoint.
    
    Creates a new user account with email and password.
    Returns JWT tokens for immediate authentication.
    """
    permission_classes = [permissions.AllowAny]
    
    def post(self, request):
        """
        Register a new user.
        """
        # TODO: Implement proper serializer-based registration
        email = request.data.get('email')
        password = request.data.get('password')
        first_name = request.data.get('first_name', '')
        last_name = request.data.get('last_name', '')
        
        if not email or not password:
            return Response(
                {'error': 'Email and password are required'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            validate_password(password)
        except ValidationError as e:
            return Response({'error': e.messages}, status=status.HTTP_400_BAD_REQUEST)
        
        if User.objects.filter(email=email).exists():
            return Response(
                {'error': 'User with this email already exists'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        user = User.objects.create_user(
            username=email,
            email=email,
            password=password,
            first_name=first_name,
            last_name=last_name
        )
        
        # Create refresh token
        refresh = RefreshToken.for_user(user)
        
        return Response({
            'message': 'User registered successfully',
            'user_id': user.id,
            'access': str(refresh.access_token),
            'refresh': str(refresh)
        }, status=status.HTTP_201_CREATED)


class LogoutView(APIView):
    """
    View for user logout.
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        """
        Logout user by blacklisting refresh token.
        """
        try:
            refresh_token = request.data.get('refresh')
            if refresh_token:
                token = RefreshToken(refresh_token)
                token.blacklist()
            
            logout(request)
            return Response({'message': 'Successfully logged out'})
        except Exception as e:
            return Response(
                {'error': 'Invalid token'}, 
                status=status.HTTP_400_BAD_REQUEST
            )


class CurrentUserView(APIView):
    """
    View to get current user information.
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        """
        Get current user data.
        """
        user = request.user
        return Response({
            'id': user.id,
            'username': user.username,
            'email': user.email,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'date_joined': user.date_joined,
        })


class ChangePasswordView(APIView):
    """
    View for changing user password.
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        """
        Change user password.
        """
        old_password = request.data.get('old_password')
        new_password = request.data.get('new_password')
        
        if not old_password or not new_password:
            return Response(
                {'error': 'Both old and new passwords are required'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        user = request.user
        if not user.check_password(old_password):
            return Response(
                {'error': 'Old password is incorrect'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            validate_password(new_password, user)
        except ValidationError as e:
            return Response({'error': e.messages}, status=status.HTTP_400_BAD_REQUEST)
        
        user.set_password(new_password)
        user.save()
        
        return Response({'message': 'Password changed successfully'})


class ProfileView(APIView):
    """
    View for user profile management.
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        """
        Get user profile.
        """
        try:
            profile = request.user.profile
            return Response({
                'bio': profile.bio,
                'phone_number': str(profile.phone_number) if profile.phone_number else None,
                'location': profile.location,
                'website': profile.website,
                'linkedin_url': profile.linkedin_url,
                'github_url': profile.github_url,
                'resume_url': profile.resume_url,
                'skills': profile.skills,
                'experience_level': profile.experience_level,
                'desired_salary_min': profile.desired_salary_min,
                'desired_salary_max': profile.desired_salary_max,
                'job_preferences': profile.job_preferences,
                'availability': profile.availability,
                'is_available': profile.is_available,
                'preferred_work_type': profile.preferred_work_type,
            })
        except UserProfile.DoesNotExist:
            return Response(
                {'error': 'Profile not found'}, 
                status=status.HTTP_404_NOT_FOUND
            )
    
    def put(self, request):
        """
        Update user profile.
        """
        try:
            profile, created = UserProfile.objects.get_or_create(user=request.user)
            
            # Update profile fields
            for field in ['bio', 'phone_number', 'location', 'website', 'linkedin_url', 
                         'github_url', 'resume_url', 'skills', 'experience_level',
                         'desired_salary_min', 'desired_salary_max', 'job_preferences',
                         'availability', 'is_available', 'preferred_work_type']:
                if field in request.data:
                    setattr(profile, field, request.data[field])
            
            profile.save()
            
            return Response({'message': 'Profile updated successfully'})
        except Exception as e:
            return Response(
                {'error': str(e)}, 
                status=status.HTTP_400_BAD_REQUEST
            )
