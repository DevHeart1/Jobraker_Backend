from django.shortcuts import render
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from django.contrib.auth import get_user_model, logout
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from rest_framework_simplejwt.tokens import RefreshToken
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiExample, extend_schema_view
from drf_spectacular.openapi import OpenApiTypes
from .models import UserProfile
from .serializers import (
    UserSerializer, UserProfileSerializer, UserRegistrationSerializer, 
    ChangePasswordSerializer
)

User = get_user_model()


@extend_schema_view(
    list=extend_schema(
        summary="List all users",
        description="Retrieve a list of all users (admin only)",
        tags=['Users'],
        responses={
            200: UserSerializer(many=True),
            403: OpenApiExample(
                'Forbidden',
                value={'error': 'Permission denied'},
                response_only=True
            )
        }
    ),
    retrieve=extend_schema(
        summary="Get user details",
        description="Retrieve detailed information about a specific user",
        tags=['Users'],
        responses={
            200: UserSerializer,
            404: OpenApiExample(
                'User Not Found',
                value={'error': 'User not found'},
                response_only=True
            )
        }
    ),
    create=extend_schema(
        summary="Create new user",
        description="Create a new user account (Note: For self-registration, use the /auth/register/ endpoint. This is more for admin creation if permissions allow).",
        tags=['Users'],
        request=UserSerializer, # Explicitly defining request body
        responses={
            201: UserSerializer,
            400: OpenApiExample(
                'Validation Error',
                value={'email': ['This field is required.']},
                response_only=True
            )
        }
    ),
    update=extend_schema(
        summary="Update user",
        description="Update user information",
        tags=['Users'],
        request=UserSerializer,
        responses={
            200: UserSerializer,
            400: OpenApiExample(
                'Validation Error',
                value={'email': ['Enter a valid email address.']},
                response_only=True
            )
        }
    ),
    destroy=extend_schema(
        summary="Delete user",
        description="Delete a user account",
        tags=['Users'],
        responses={
            204: None,
            404: OpenApiExample(
                'User Not Found',
                value={'error': 'User not found'},
                response_only=True
            )
        }
    )
)
class UserViewSet(viewsets.ModelViewSet):
    """
    ViewSet for comprehensive user management.
    
    Provides full CRUD operations for user accounts including:
    - List all users (admin only)
    - Retrieve user details
    - Create new user accounts
    - Update user information
    - Delete user accounts
    
    Authentication is required for all endpoints except user creation.
    """
    queryset = User.objects.all()
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_permissions(self):
        """
        Apply different permissions based on the action.
        
        - create: Allow anyone to register
        - other actions: Require authentication
        """
        if self.action == 'create':
            permission_classes = [permissions.AllowAny]
        else:
            permission_classes = [permissions.IsAuthenticated]
        return [permission() for permission in permission_classes]


@extend_schema_view(
    list=extend_schema(
        summary="List user profiles",
        description="Get all user profiles (current user only)",
        tags=['User Profiles'],
        responses={
            200: UserProfileSerializer(many=True),
            401: OpenApiExample(
                'Unauthorized',
                value={'error': 'Authentication required'},
                response_only=True
            )
        }
    ),
    retrieve=extend_schema(
        summary="Get user profile",
        description="Retrieve the current user's detailed profile information",
        tags=['User Profiles'],
        responses={
            200: UserProfileSerializer,
            404: OpenApiExample(
                'Profile Not Found',
                value={'error': 'Profile not found for current user'},
                response_only=True
            )
        }
    ),
    create=extend_schema(
        summary="Create user profile",
        description="Create a new user profile",
        tags=['User Profiles'],
        request=UserProfileSerializer,
        responses={
            201: UserProfileSerializer,
            400: OpenApiExample(
                'Validation Error',
                value={'bio': ['This field may not be blank.']},
                response_only=True
            )
        }
    ),
    update=extend_schema(
        summary="Update user profile",
        description="Update the current user's profile information",
        tags=['User Profiles'],
        request=UserProfileSerializer,
        responses={
            200: UserProfileSerializer,
            400: OpenApiExample(
                'Validation Error',
                value={'experience_level': ['Invalid choice.']},
                response_only=True
            )
        }
    ),
    partial_update=extend_schema(
        summary="Partially update user profile",
        description="Update specific fields of the current user's profile",
        tags=['User Profiles'],
        request=UserProfileSerializer,
        responses={
            200: UserProfileSerializer,
            400: OpenApiExample(
                'Validation Error',
                value={'desired_salary_min': ['Must be a positive number.']},
                response_only=True
            )
        }
    )
)
class UserProfileViewSet(viewsets.ModelViewSet):
    """
    ViewSet for comprehensive user profile management.
    
    Handles all aspects of user profile data including:
    - Personal information (bio, contact details)
    - Professional information (skills, experience level)
    - Job preferences (salary range, work type)
    - Availability status and preferences
    - Social media and portfolio links
    
    All operations are scoped to the authenticated user's profile only.
    """
    queryset = UserProfile.objects.all()
    serializer_class = UserProfileSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        """
        Filter profiles to only return the current user's profile.
        
        This ensures users can only access and modify their own profile data.
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


@extend_schema(
    summary="Register new user",
    description="Create a new user account with email and password. Returns JWT tokens for immediate authentication.",
    tags=['Authentication'],
    request=OpenApiExample(
        'Registration Request',
        summary='User registration data',
        description='Required information for creating a new user account',
        value={
            "email": "user@example.com",
            "password": "securePassword123!",
            "first_name": "John",
            "last_name": "Doe"
        }
    ),
    responses={
        201: OpenApiExample(
            'Registration Success',
            summary='Successful registration response',
            description='User created successfully with JWT tokens',
            value={
                "message": "User registered successfully",
                "user_id": 1,
                "access": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
                "refresh": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9..."
            }
        ),
        400: OpenApiExample(
            'Registration Error',
            summary='Registration failed',
            description='Validation errors or user already exists',
            value={
                "error": "User with this email already exists"
            }
        )
    }
)
class RegisterView(APIView):
    """
    User registration endpoint for creating new accounts.
    
    Creates a new user account with email and password validation.
    Automatically generates JWT tokens for immediate authentication.
    
    Features:
    - Email uniqueness validation
    - Password strength validation
    - Automatic JWT token generation
    - Optional first and last name
    """
    permission_classes = [permissions.AllowAny]
    
    def post(self, request):
        """
        Register a new user with email and password.
        
        Validates input data, creates user account, and returns JWT tokens.
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


@extend_schema(
    summary="User logout",
    description="Logout user by blacklisting refresh token and clearing session",
    tags=['Authentication'],
    request=OpenApiExample(
        'Logout Request',
        summary='Logout request with refresh token',
        description='Refresh token to be blacklisted',
        value={
            "refresh": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9..."
        }
    ),
    responses={
        200: OpenApiExample(
            'Logout Success',
            summary='Successful logout',
            description='User logged out successfully',
            value={
                "message": "Successfully logged out"
            }
        ),
        400: OpenApiExample(
            'Logout Error',
            summary='Invalid token',
            description='Refresh token is invalid or already blacklisted',
            value={
                "error": "Invalid token"
            }
        )
    }
)
class LogoutView(APIView):
    """
    User logout endpoint with token blacklisting.
    
    Securely logs out users by:
    - Blacklisting the provided refresh token
    - Clearing the user session
    - Preventing token reuse
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        """
        Logout user by blacklisting refresh token.
        
        Accepts refresh token and adds it to blacklist to prevent reuse.
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


@extend_schema(
    summary="Get current user",
    description="Retrieve information about the currently authenticated user",
    tags=['Authentication'],
    responses={
        200: OpenApiExample(
            'Current User',
            summary='Current user information',
            description='Basic information about the authenticated user',
            value={
                "id": 1,
                "username": "user@example.com",
                "email": "user@example.com",
                "first_name": "John",
                "last_name": "Doe",
                # "is_staff": False, # Example: if you add more fields from User model
                # "is_active": True,
                "date_joined": "2025-06-15T10:00:00Z"
                # Ensure all fields returned by the view's get method are in this example
            }
        ),
        401: OpenApiExample(
            'Unauthorized',
            summary='Authentication required',
            description='User must be authenticated to access this endpoint',
            value={
                "error": "Authentication credentials were not provided"
            }
        )
    }
)
class CurrentUserView(APIView):
    """
    Get current authenticated user information.
    
    Returns basic user information for the currently authenticated user.
    Useful for frontend applications to display user data and verify authentication status.
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        """
        Get current user data including basic profile information.
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


@extend_schema(
    summary="Change password",
    description="Change the current user's password with old password verification",
    tags=['Authentication'],
    request=ChangePasswordSerializer, # Explicitly set serializer for request body
    # request=OpenApiExample( # This can be used if ChangePasswordSerializer is not sufficient for example
    # 'Change Password Request',
    # summary='Password change data',
        description='Old and new passwords for authentication',
        value={
            "old_password": "currentPassword123!",
            "new_password": "newSecurePassword456!"
        }
    ),
    responses={
        200: OpenApiExample(
            'Password Changed',
            summary='Password successfully changed',
            description='User password updated successfully',
            value={
                "message": "Password changed successfully"
            }
        ),
        400: OpenApiExample(
            'Change Password Error',
            summary='Password change failed',
            description='Old password incorrect or new password invalid',
            value={
                "error": "Old password is incorrect"
            }
        )
    }
)
class ChangePasswordView(APIView):
    """
    Change user password with verification.
    
    Securely changes user password by:
    - Verifying the old password
    - Validating the new password strength
    - Updating the user's password hash
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        """
        Change user password after verifying old password.
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


@extend_schema_view(
    get=extend_schema(
        summary="Get user profile",
        description="Retrieve the current user's complete profile information",
        tags=['User Profiles'],
        responses={
            200: OpenApiExample(
                'User Profile',
                summary='Complete user profile data',
                description='All profile information for the current user',
                value={
                    "bio": "Experienced Python developer with 5+ years in web development",
                    "phone_number": "+1-555-123-4567",
                    "location": "San Francisco, CA",
                    "website": "https://johndoe.dev",
                    "linkedin_url": "https://linkedin.com/in/johndoe",
                    "github_url": "https://github.com/johndoe", 
                    "resume_url": "https://example.com/resume.pdf",
                    "skills": ["Python", "Django", "JavaScript", "React"],
                    "experience_level": "senior",
                    "desired_salary_min": 120000,
                    "desired_salary_max": 160000,
                    "job_preferences": {"remote": True, "full_time": True},
                    "availability": "immediately",
                    "is_available": True,
                    "preferred_work_type": "remote"
                }
            ),
            404: OpenApiExample(
                'Profile Not Found',
                summary='Profile does not exist',
                description='User profile has not been created yet',
                value={
                    "error": "Profile not found"
                }
            )
        }
    ),
    put=extend_schema(
        summary="Update user profile",
        description="Update the current user's profile information",
        tags=['User Profiles'],
        request=OpenApiExample(
            'Profile Update Request',
            summary='Profile update data',
            description='Profile fields to update',
            value={
                "bio": "Updated bio information",
                "location": "New York, NY",
                "skills": ["Python", "Django", "PostgreSQL", "AWS"],
                "experience_level": "senior",
                "desired_salary_min": 130000,
                "desired_salary_max": 170000,
                "is_available": True
            }
        ),
        responses={
            200: OpenApiExample(
                'Profile Updated',
                summary='Profile successfully updated',
                description='User profile information updated',
                value={
                    "message": "Profile updated successfully"
                }
            ),
            400: OpenApiExample(
                'Profile Update Error',
                summary='Profile update failed',
                description='Validation error or invalid data',
                value={
                    "error": "Invalid experience level"
                }
            )
        }
    )
)
class ProfileView(APIView):
    """
    Legacy user profile management endpoint.
    
    Provides direct access to user profile data with custom serialization.
    
    Note: Consider using UserProfileViewSet for full CRUD operations.
    This view provides simplified profile access for backward compatibility.
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        """
        Get complete user profile information.
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
        Update user profile with flexible field updates.
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
