from django.shortcuts import render
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from django.contrib.auth import get_user_model
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiParameter, OpenApiExample, OpenApiResponse
from drf_spectacular.openapi import OpenApiTypes
from .models import Job, Application, SavedJob, JobAlert, JobSource
from .serializers import (
    JobSerializer, JobListSerializer, ApplicationSerializer, SavedJobSerializer,
    JobAlertSerializer, JobSearchSerializer, BulkApplySerializer,
    JobSearchResultSerializer, JobRecommendationSerializer, ApplicationStatsSerializer,
    SuccessResponseSerializer, ErrorResponseSerializer
)

User = get_user_model()


@extend_schema_view(
    list=extend_schema(
        summary="List jobs",
        description="Retrieve a paginated list of available jobs with optional filtering",
        tags=['Jobs'],
        parameters=[
            OpenApiParameter(
                name='search',
                description='Search jobs by title keywords',
                required=False,
                type=OpenApiTypes.STR
            ),
            OpenApiParameter(
                name='location',
                description='Filter jobs by location',
                required=False,
                type=OpenApiTypes.STR
            ),
            OpenApiParameter(
                name='company',
                description='Filter jobs by company name',
                required=False,
                type=OpenApiTypes.STR
            ),
            OpenApiParameter(
                name='job_type',
                description='Filter by job type (full_time, part_time, contract, etc.)',
                required=False,
                type=OpenApiTypes.STR
            ),
            OpenApiParameter(
                name='experience_level',
                description='Filter by required experience level',
                required=False,
                type=OpenApiTypes.STR
            ),
            OpenApiParameter(
                name='is_remote',
                description='Filter for remote jobs only',
                required=False,
                type=OpenApiTypes.BOOL
            )
        ],
        responses={
            200: JobListSerializer(many=True),
            401: ErrorResponseSerializer
        }
    ),
    retrieve=extend_schema(
        summary="Get job details",
        description="Retrieve detailed information about a specific job",
        tags=['Jobs'],
        responses={
            200: JobSerializer,
            404: ErrorResponseSerializer
        }
    ),
    create=extend_schema(
        summary="Create job",
        description="Create a new job posting (admin/employer only)",
        tags=['Jobs'],
        request=JobSerializer,
        responses={
            201: JobSerializer,
            400: ErrorResponseSerializer,
            403: ErrorResponseSerializer
        }
    ),
    update=extend_schema(
        summary="Update job",
        description="Update job information (admin/employer only)",
        tags=['Jobs'],
        request=JobSerializer,
        responses={
            200: JobSerializer,
            400: ErrorResponseSerializer,
            403: ErrorResponseSerializer,
            404: ErrorResponseSerializer
        }
    ),
    destroy=extend_schema(
        summary="Delete job",
        description="Delete a job posting (admin/employer only)",
        tags=['Jobs'],
        responses={
            204: None,
            403: ErrorResponseSerializer,
            404: ErrorResponseSerializer
        }
    )
)
class JobViewSet(viewsets.ModelViewSet):
    """
    Comprehensive job management ViewSet.
    
    Provides full CRUD operations for job postings with advanced filtering:
    - List jobs with search, location, company, and other filters
    - Retrieve detailed job information
    - Create new job postings (admin/employer only)
    - Update existing job information
    - Delete job postings
    - Save/unsave jobs to user's collection
    
    All job listings are ordered by posting date (newest first).
    """
    queryset = Job.objects.all()
    permission_classes = [permissions.IsAuthenticated]
    
    def get_serializer_class(self):
        """
        Use different serializers for list vs detail views.
        """
        if self.action == 'list':
            return JobListSerializer
        return JobSerializer
    
    def get_queryset(self):
        """
        Filter jobs based on query parameters and user preferences.
        
        Supports filtering by:
        - search: Job title keywords
        - location: Job location
        - company: Company name
        - job_type: Employment type
        - experience_level: Required experience
        - is_remote: Remote work availability
        """
        queryset = Job.objects.all()
        
        # Apply search filters
        search = self.request.query_params.get('search', None)
        if search:
            queryset = queryset.filter(title__icontains=search)
        
        location = self.request.query_params.get('location', None)
        if location:
            queryset = queryset.filter(location__icontains=location)
        
        company = self.request.query_params.get('company', None)
        if company:
            queryset = queryset.filter(company__icontains=company)
            
        job_type = self.request.query_params.get('job_type', None)
        if job_type:
            queryset = queryset.filter(job_type=job_type)
            
        experience_level = self.request.query_params.get('experience_level', None)
        if experience_level:
            queryset = queryset.filter(experience_level=experience_level)
            
        is_remote = self.request.query_params.get('is_remote', None)
        if is_remote is not None:
            queryset = queryset.filter(is_remote=is_remote.lower() == 'true')
        
        return queryset.order_by('-posted_date')
    
    @extend_schema(
        summary="Save job",
        description="Save a job to the user's saved jobs collection",
        tags=['Jobs'],
        request=None,
        responses={
            200: SuccessResponseSerializer,
            404: ErrorResponseSerializer
        }
    )
    @action(detail=True, methods=['post'])
    def save(self, request, pk=None):
        """
        Save a job for later review.
        
        Adds the job to the user's saved jobs collection.
        Returns success message if job is newly saved or already exists.
        """
        job = self.get_object()
        saved_job, created = SavedJob.objects.get_or_create(
            user=request.user,
            job=job
        )
        
        if created:
            return Response({'message': 'Job saved successfully'})
        else:
            return Response({'message': 'Job already saved'})
    
    @extend_schema(
        summary="Unsave job",
        description="Remove a job from the user's saved jobs collection",
        tags=['Jobs'],
        request=None,
        responses={
            200: SuccessResponseSerializer,
            404: ErrorResponseSerializer
        }
    )
    @action(detail=True, methods=['delete'])
    def unsave(self, request, pk=None):
        """
        Remove a job from saved jobs collection.
        
        Removes the job from the user's saved jobs if it exists.
        """
        job = self.get_object()
        try:
            saved_job = SavedJob.objects.get(user=request.user, job=job)
            saved_job.delete()
            return Response({'message': 'Job removed from saved jobs'})
        except SavedJob.DoesNotExist:
            return Response(
                {'error': 'Job not found in saved jobs'}, 
                status=status.HTTP_404_NOT_FOUND
            )


@extend_schema_view(
    list=extend_schema(
        summary="List user applications",
        description="Retrieve all job applications for the current user",
        tags=['Applications'],
        responses={
            200: ApplicationSerializer(many=True),
            401: ErrorResponseSerializer
        }
    ),
    retrieve=extend_schema(
        summary="Get application details",
        description="Retrieve detailed information about a specific application",
        tags=['Applications'],
        responses={
            200: ApplicationSerializer,
            404: ErrorResponseSerializer
        }
    ),
    create=extend_schema(
        summary="Apply to job",
        description="Submit a new job application",
        tags=['Applications'],
        request=ApplicationSerializer,
        responses={
            201: ApplicationSerializer,
            400: ErrorResponseSerializer
        }
    ),
    update=extend_schema(
        summary="Update application",
        description="Update an existing job application",
        tags=['Applications'],
        request=ApplicationSerializer,
        responses={
            200: ApplicationSerializer,
            400: ErrorResponseSerializer,
            404: ErrorResponseSerializer
        }
    ),
    destroy=extend_schema(
        summary="Withdraw application",
        description="Withdraw a job application",
        tags=['Applications'],
        responses={
            204: None,
            404: ErrorResponseSerializer
        }
    )
)
class ApplicationViewSet(viewsets.ModelViewSet):
    """
    Comprehensive job application management ViewSet.
    
    Handles all aspects of job applications:
    - List user's applications with job details
    - Create new job applications
    - Update application status and information
    - Withdraw applications
    - Track application status and progress
    
    All operations are scoped to the current user's applications only.
    """
    queryset = Application.objects.all()
    serializer_class = ApplicationSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        """
        Return applications for the current user only.
        
        Ensures users can only access their own application data.
        """
        return Application.objects.filter(user=self.request.user)
    
    def perform_create(self, serializer):
        """
        Create application for the current user.
        
        Automatically sets the current user as the application owner.
        """
        serializer.save(user=self.request.user)


@extend_schema(
    summary="Advanced job search",
    description="Search jobs with advanced filters and AI-powered matching",
    tags=['Jobs'],
    parameters=[
        OpenApiParameter(
            name='title',
            description='Job title keywords',
            required=False,
            type=OpenApiTypes.STR
        ),
        OpenApiParameter(
            name='company',
            description='Company name',
            required=False,
            type=OpenApiTypes.STR
        ),
        OpenApiParameter(
            name='location',
            description='Job location',
            required=False,
            type=OpenApiTypes.STR
        ),
        OpenApiParameter(
            name='remote',
            description='Remote work availability',
            required=False,
            type=OpenApiTypes.BOOL
        ),
        OpenApiParameter(
            name='min_salary',
            description='Minimum salary requirement',
            required=False,
            type=OpenApiTypes.INT
        ),
        OpenApiParameter(
            name='max_salary',
            description='Maximum salary range',
            required=False,
            type=OpenApiTypes.INT
        ),
        OpenApiParameter(
            name='job_type',
            description='Employment type',
            required=False,
            type=OpenApiTypes.STR
        ),
        OpenApiParameter(
            name='experience_level',
            description='Required experience level',
            required=False,
            type=OpenApiTypes.STR
        )
    ],
    responses={
        200: JobSearchResultSerializer,
        400: ErrorResponseSerializer,
        401: ErrorResponseSerializer
    }
)
class JobSearchView(APIView):
    """
    Advanced job search with comprehensive filtering and AI-powered matching.
    
    Provides flexible job search capabilities with:
    - Keyword-based title search
    - Company and location filtering
    - Salary range filtering
    - Employment type and experience level filters
    - Remote work availability
    - AI-powered job matching and ranking (planned)
    
    Results are limited to 50 jobs and ordered by posting date.
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        """
        Execute advanced job search with multiple filter options.
        
        Applies various filters and returns structured search results
        with job matching information.
        """
        # TODO: Implement advanced search with AI matching
        queryset = Job.objects.all()
        
        # Basic filters
        filters = {}
        if request.query_params.get('title'):
            filters['title__icontains'] = request.query_params.get('title')
        if request.query_params.get('company'):
            filters['company__icontains'] = request.query_params.get('company')
        if request.query_params.get('location'):
            filters['location__icontains'] = request.query_params.get('location')
        if request.query_params.get('remote'):
            filters['is_remote'] = request.query_params.get('remote').lower() == 'true'
        
        if filters:
            queryset = queryset.filter(**filters)
        
        # Salary range filter
        min_salary = request.query_params.get('min_salary')
        max_salary = request.query_params.get('max_salary')
        if min_salary:
            queryset = queryset.filter(salary_min__gte=min_salary)
        if max_salary:
            queryset = queryset.filter(salary_max__lte=max_salary)
        
        jobs = queryset.order_by('-posted_date')[:50]  # Limit results
        
        # TODO: Add AI-powered job matching and ranking
        
        return Response({
            'count': jobs.count() if hasattr(jobs, 'count') else len(jobs),
            'results': [
                {
                    'id': job.id,
                    'title': job.title,
                    'company': job.company,
                    'location': job.location,
                    'salary_min': job.salary_min,
                    'salary_max': job.salary_max,
                    'is_remote': job.is_remote,
                    'posted_date': job.posted_date,
                    'url': job.url,
                } for job in jobs
            ]
        })


@extend_schema(
    summary="Get job recommendations",
    description="Get AI-powered personalized job recommendations based on user profile",
    tags=['Jobs'],
    responses={
        200: JobRecommendationSerializer,
        401: ErrorResponseSerializer
    }
)
class JobRecommendationsView(APIView):
    """
    AI-powered job recommendations based on user profile and preferences.
    
    Provides personalized job suggestions using:
    - User skills and experience
    - Job preferences and salary expectations
    - Application history and patterns
    - Vector similarity matching (planned)
    - Machine learning recommendations (planned)
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        """
        Get personalized job recommendations for the current user.
        
        Returns a curated list of jobs with match scores and explanations.
        """
        # TODO: Implement AI-powered job recommendations
        # This would use the user's profile, skills, experience, and preferences
        # to recommend relevant jobs using vector similarity search
        
        user = request.user
        
        # For now, return a simple set of recent jobs
        # This should be replaced with actual AI recommendations
        jobs = Job.objects.all().order_by('-posted_date')[:10]
        
        return Response({
            'message': 'AI-powered recommendations coming soon',
            'recommendations': [
                {
                    'id': job.id,
                    'title': job.title,
                    'company': job.company,
                    'location': job.location,
                    'match_score': 0.85,  # Placeholder score
                    'reasons': ['Skills match', 'Location preference']  # Placeholder
                } for job in jobs
            ]
        })


@extend_schema(
    summary="Auto-apply to jobs",
    description="Start automated job application process using AI and Skyvern integration",
    tags=['Applications'],
    request=BulkApplySerializer,
    responses={
        202: OpenApiExample(
            'Auto-apply Started',
            summary='Automated application process initiated',
            description='Jobs queued for automated application',
            value={
                "message": "Auto-apply process started",
                "queued_jobs": 5,
                "estimated_completion": "2025-06-16T12:00:00Z"
            }
        ),
        400: ErrorResponseSerializer,
        401: ErrorResponseSerializer
    }
)
class AutoApplyView(APIView):
    """
    Automated job application using AI and Skyvern integration.
    
    Automates the job application process by:
    - Validating user profile completeness
    - Queuing jobs for automated application
    - Using Skyvern to fill out application forms
    - Tracking application status and progress
    - Handling application errors and retries
    
    Requires complete user profile with resume and contact information.
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        """
        Start automated application process for selected jobs.
        
        Validates user readiness and queues jobs for automated application.
        """
        job_ids = request.data.get('job_ids', [])
        
        if not job_ids:
            return Response(
                {'error': 'No job IDs provided'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # TODO: Implement auto-apply using Skyvern
        # This would:
        # 1. Validate user has complete profile and resume
        # 2. Queue jobs for automated application
        # 3. Use Skyvern to fill out application forms
        # 4. Track application status
        
        return Response({
            'message': 'Auto-apply feature coming soon',
            'queued_jobs': len(job_ids)
        })


class BulkApplyView(APIView):
    """
    Apply to multiple jobs at once.
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        """
        Apply to multiple jobs with bulk operation.
        """
        job_ids = request.data.get('job_ids', [])
        cover_letter = request.data.get('cover_letter', '')
        
        if not job_ids:
            return Response(
                {'error': 'No job IDs provided'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        applied_jobs = []
        failed_jobs = []
        
        for job_id in job_ids:
            try:
                job = Job.objects.get(id=job_id)
                
                # Check if already applied
                if Application.objects.filter(user=request.user, job=job).exists():
                    failed_jobs.append({
                        'job_id': job_id,
                        'error': 'Already applied to this job'
                    })
                    continue
                
                # Create application
                application = Application.objects.create(
                    user=request.user,
                    job=job,
                    cover_letter=cover_letter,
                    status='submitted'
                )
                
                applied_jobs.append({
                    'job_id': job_id,
                    'application_id': application.id,
                    'job_title': job.title,
                    'company': job.company
                })
                
            except Job.DoesNotExist:
                failed_jobs.append({
                    'job_id': job_id,
                    'error': 'Job not found'
                })
            except Exception as e:
                failed_jobs.append({
                    'job_id': job_id,
                    'error': str(e)
                })
        
        return Response({
            'message': f'Applied to {len(applied_jobs)} jobs',
            'applied_jobs': applied_jobs,
            'failed_jobs': failed_jobs
        })
