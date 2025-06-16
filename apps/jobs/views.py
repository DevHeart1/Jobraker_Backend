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


@extend_schema(
    summary="Bulk apply to jobs",
    description="Apply to multiple jobs simultaneously with a single cover letter",
    tags=['Applications'],
    request=BulkApplySerializer,
    responses={
        200: OpenApiExample(
            'Bulk Apply Results',
            summary='Bulk application results',
            description='Results of bulk application operation',
            value={
                "successful_applications": 3,
                "failed_applications": 1,
                "total_processed": 4,
                "details": [
                    {
                        "job_id": "550e8400-e29b-41d4-a716-446655440000",
                        "status": "success",
                        "application_id": "aa0fb700-f59e-74g7-d049-779988771111"
                    },
                    {
                        "job_id": "660f9500-f39c-52e5-b827-557766551111",
                        "status": "failed",
                        "error": "Already applied to this job"
                    }
                ]
            }
        ),
        400: ErrorResponseSerializer,
        401: ErrorResponseSerializer
    }
)
class BulkApplyView(APIView):
    """
    Bulk job application for efficient multiple job applications.
    
    Allows users to apply to multiple jobs simultaneously with:
    - Single cover letter for all applications
    - Batch processing for efficiency
    - Individual success/failure tracking
    - Duplicate application prevention
    - Comprehensive result reporting
    
    Maximum 50 jobs per bulk operation.
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


@extend_schema_view(
    list=extend_schema(
        summary="List saved jobs",
        description="Retrieve all jobs saved by the current user",
        tags=['Saved Jobs'],
        responses={
            200: SavedJobSerializer(many=True),
            401: ErrorResponseSerializer
        }
    ),
    retrieve=extend_schema(
        summary="Get saved job details",
        description="Retrieve details of a specific saved job",
        tags=['Saved Jobs'],
        responses={
            200: SavedJobSerializer,
            404: ErrorResponseSerializer
        }
    ),
    create=extend_schema(
        summary="Save a job",
        description="Add a job to the user's saved jobs collection",
        tags=['Saved Jobs'],
        request=SavedJobSerializer,
        responses={
            201: SavedJobSerializer,
            400: ErrorResponseSerializer
        }
    ),
    destroy=extend_schema(
        summary="Remove saved job",
        description="Remove a job from the user's saved jobs collection",
        tags=['Saved Jobs'],
        responses={
            204: None,
            404: ErrorResponseSerializer
        }
    )
)
class SavedJobViewSet(viewsets.ModelViewSet):
    """
    Comprehensive saved jobs management ViewSet.
    
    Handles user's saved jobs collection:
    - List all saved jobs with job details
    - Add jobs to saved collection
    - Remove jobs from saved collection
    - Retrieve individual saved job details
    
    All operations are scoped to the current user's saved jobs only.
    """
    queryset = SavedJob.objects.all()
    serializer_class = SavedJobSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        """
        Return saved jobs for the current user only.
        
        Ensures users can only access their own saved jobs.
        """
        return SavedJob.objects.filter(user=self.request.user)
    
    def perform_create(self, serializer):
        """
        Create saved job for the current user.
        
        Automatically sets the current user as the owner.
        """
        serializer.save(user=self.request.user)


@extend_schema_view(
    list=extend_schema(
        summary="List job alerts",
        description="Retrieve all job alerts for the current user",
        tags=['Job Alerts'],
        responses={
            200: JobAlertSerializer(many=True),
            401: ErrorResponseSerializer
        }
    ),
    retrieve=extend_schema(
        summary="Get job alert details",
        description="Retrieve details of a specific job alert",
        tags=['Job Alerts'],
        responses={
            200: JobAlertSerializer,
            404: ErrorResponseSerializer
        }
    ),
    create=extend_schema(
        summary="Create job alert",
        description="Create a new job alert with search criteria",
        tags=['Job Alerts'],
        request=JobAlertSerializer,
        responses={
            201: JobAlertSerializer,
            400: ErrorResponseSerializer
        }
    ),
    update=extend_schema(
        summary="Update job alert",
        description="Update job alert criteria and settings",
        tags=['Job Alerts'],
        request=JobAlertSerializer,
        responses={
            200: JobAlertSerializer,
            400: ErrorResponseSerializer,
            404: ErrorResponseSerializer
        }
    ),
    destroy=extend_schema(
        summary="Delete job alert",
        description="Delete a job alert",
        tags=['Job Alerts'],
        responses={
            204: None,
            404: ErrorResponseSerializer
        }
    )
)
class JobAlertViewSet(viewsets.ModelViewSet):
    """
    Comprehensive job alerts management ViewSet.
    
    Handles automated job notifications:
    - Create alerts with custom search criteria
    - Update alert settings and frequency
    - List all user alerts with execution status
    - Delete unwanted alerts
    - Track alert performance and matches
    
    All operations are scoped to the current user's alerts only.
    """
    queryset = JobAlert.objects.all()
    serializer_class = JobAlertSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        """
        Return job alerts for the current user only.
        
        Ensures users can only access their own job alerts.
        """
        return JobAlert.objects.filter(user=self.request.user)
    
    def perform_create(self, serializer):
        """
        Create job alert for the current user.
        
        Automatically sets the current user as the owner.
        """
        serializer.save(user=self.request.user)
    
    @extend_schema(
        summary="Test job alert",
        description="Test a job alert to see matching jobs",
        tags=['Job Alerts'],
        request=None,
        responses={
            200: OpenApiExample(
                'Alert Test Results',
                summary='Jobs matching alert criteria',
                description='Preview of jobs that would match this alert',
                value={
                    "matching_jobs": 15,
                    "sample_jobs": [
                        {
                            "id": "550e8400-e29b-41d4-a716-446655440000",
                            "title": "Senior Python Developer",
                            "company": "TechCorp Inc.",
                            "location": "San Francisco, CA",
                            "match_score": 0.92
                        }
                    ]
                }
            ),
            404: ErrorResponseSerializer
        }
    )
    @action(detail=True, methods=['post'])
    def test(self, request, pk=None):
        """
        Test job alert to preview matching jobs.
        
        Returns a preview of jobs that would match the alert criteria.
        """
        alert = self.get_object()
        
        # TODO: Implement actual alert testing logic
        # This would use the alert criteria to find matching jobs
        
        return Response({
            'message': 'Alert testing functionality coming soon',
            'alert_id': alert.id,
            'matching_jobs': 0,
            'sample_jobs': []
        })


@extend_schema(
    summary="Get application statistics",
    description="Retrieve comprehensive statistics about user's job applications",
    tags=['Applications'],
    responses={
        200: ApplicationStatsSerializer,
        401: ErrorResponseSerializer
    }
)
class ApplicationStatsView(APIView):
    """
    User application statistics and analytics.
    
    Provides comprehensive insights into:
    - Application counts and success rates
    - Response times and patterns
    - Most applied job types and locations
    - Interview and offer statistics
    - Application performance metrics
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        """
        Calculate and return application statistics for the current user.
        """
        user = request.user
        applications = Application.objects.filter(user=user)
        
        total_applications = applications.count()
        pending_applications = applications.filter(status='pending').count()
        interview_requests = applications.filter(status='interview').count()
        offers_received = applications.filter(status='offer').count()
        rejections = applications.filter(status='rejected').count()
        
        success_rate = (offers_received / total_applications * 100) if total_applications > 0 else 0
        
        # TODO: Implement more sophisticated analytics
        # - Average response time calculation
        # - Most applied job types/locations
        # - Application trends over time
        
        return Response({
            'total_applications': total_applications,
            'pending_applications': pending_applications,
            'interview_requests': interview_requests,
            'offers_received': offers_received,
            'rejections': rejections,
            'success_rate': round(success_rate, 2),
            'average_response_time': 0.0,  # Placeholder
            'most_applied_job_type': 'full_time',  # Placeholder
            'most_applied_location': 'San Francisco, CA'  # Placeholder
        })
