from django.shortcuts import render
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from django.contrib.auth import get_user_model
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiParameter, OpenApiExample, OpenApiResponse
from drf_spectacular.openapi import OpenApiTypes
from .models import Job, Application, SavedJob, JobAlert, JobSource, RecommendedJob # Added RecommendedJob
from .serializers import (
    JobSerializer, JobListSerializer, ApplicationSerializer, SavedJobSerializer,
    JobAlertSerializer, JobSearchSerializer, BulkApplySerializer,
    JobSearchResultSerializer, JobRecommendationSerializer, ApplicationStatsSerializer,
    SuccessResponseSerializer, ErrorResponseSerializer, RecommendedJobSerializer # Added RecommendedJobSerializer
)
from .services import JobMatchService
from rest_framework import generics # For ListAPIView
import logging # For logging in the view

User = get_user_model()
logger = logging.getLogger(__name__) # Standard logger for views


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
        summary="Find Similar Jobs",
        description="Find jobs similar to the specified job using vector embeddings.",
        tags=['Jobs', 'Recommendations'],
        parameters=[
            OpenApiParameter(
                name='top_n',
                description='Number of similar jobs to return.',
                required=False,
                type=OpenApiTypes.INT,
                default=10
            )
        ],
        responses={
            200: JobListSerializer(many=True),
            404: ErrorResponseSerializer
        }
    )
    @action(detail=True, methods=['get'], url_path='similar')
    def similar(self, request, pk=None):
        """
        Find and return jobs similar to the current job.
        """
        try:
            job = self.get_object()
        except Job.DoesNotExist:
            return Response({"error": "Job not found."}, status=status.HTTP_404_NOT_FOUND)

        top_n = int(request.query_params.get('top_n', 10))
        
        service = JobMatchService()
        similar_jobs_data = service.find_similar_jobs(job_id=job.id, top_n=top_n)

        similar_jobs = [item['job'] for item in similar_jobs_data]

        serializer = JobListSerializer(similar_jobs, many=True, context={'request': request})
        return Response(serializer.data)

    @extend_schema(
        summary="Generate Interview Questions",
        description="Queues a task to generate interview questions for this specific job.",
        tags=['Jobs', 'AI'],
        request=None, # No request body needed for this version
        responses={
            202: OpenApiResponse(
                response={'type': 'object', 'properties': {'task_id': {'type': 'string'}, 'status': {'type': 'string'}, 'message': {'type': 'string'}}},
                description="Task successfully queued.",
                examples=[OpenApiExample('Example Response', value={'task_id': 'some-celery-task-id', 'status': 'queued', 'message': 'Interview question generation has been queued.'})]
            ),
            404: ErrorResponseSerializer, # If job not found
            401: ErrorResponseSerializer  # If not authenticated
        }
    )
    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAuthenticated])
    def generate_interview_questions(self, request, pk=None):
        """
        Triggers an asynchronous task to generate interview questions for the specified job.
        """
        from apps.integrations.tasks import generate_interview_questions_task # Local import for clarity

        try:
            job = self.get_object() # Gets the Job instance based on pk
        except Job.DoesNotExist: # Should be handled by get_object, but defensive
            return Response({"error": "Job not found."}, status=status.HTTP_404_NOT_FOUND)

        # Dispatch Celery task
        # Pass user_id for potential personalization, task handles if user_id is None
        task = generate_interview_questions_task.delay(job_id=str(job.id), user_id=str(request.user.id))

        return Response(
            {
                "task_id": task.id,
                "status": "queued",
                "message": "Interview question generation has been queued. You can check the status using the task_id."
            },
            status=status.HTTP_202_ACCEPTED
        )
    
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
    # Consider adding DRF's pagination for this view
    # from rest_framework.pagination import PageNumberPagination
    # pagination_class = PageNumberPagination
    # PageNumberPagination.page_size = 20 # Example page size

    def get(self, request):
        """
        Execute advanced job search using Django ORM with fallback to Elasticsearch.
        
        Applies various filters and returns structured search results.
        """
        from django.db.models import Q as Django_Q
        
        # Validate query parameters using JobSearchSerializer
        query_params_serializer = JobSearchSerializer(data=request.query_params)
        if not query_params_serializer.is_valid():
            return Response(query_params_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        valid_params = query_params_serializer.validated_data

        # Start with base queryset
        queryset = Job.objects.filter(status='active')
        
        # Apply filters using Django ORM
        if valid_params.get('title'):
            queryset = queryset.filter(title__icontains=valid_params['title'])
        
        if valid_params.get('company'):
            queryset = queryset.filter(company__icontains=valid_params['company'])

        if valid_params.get('location'):
            queryset = queryset.filter(location__icontains=valid_params['location'])

        if valid_params.get('is_remote') is not None:
            queryset = queryset.filter(is_remote=valid_params['is_remote'])

        if valid_params.get('job_type'):
            queryset = queryset.filter(job_type=valid_params['job_type'])

        if valid_params.get('experience_level'):
            queryset = queryset.filter(experience_level=valid_params['experience_level'])
        
        # Salary range filters
        if valid_params.get('min_salary') is not None:
            # Jobs where salary_min is >= requested min OR salary_max is >= requested min
            queryset = queryset.filter(
                Django_Q(salary_min__gte=valid_params['min_salary']) |
                Django_Q(salary_max__gte=valid_params['min_salary'])
            )
        
        if valid_params.get('max_salary') is not None:
            # Jobs where salary_max is <= requested max OR salary_min is <= requested max
            queryset = queryset.filter(
                Django_Q(salary_max__lte=valid_params['max_salary']) |
                Django_Q(salary_min__lte=valid_params['max_salary'])
            )

        # Skills search (if provided)
        if valid_params.get('skills'):
            skills_q = Django_Q()
            for skill in valid_params['skills']:
                skills_q |= (
                    Django_Q(skills_required__icontains=skill) |
                    Django_Q(skills_preferred__icontains=skill) |
                    Django_Q(description__icontains=skill)
                )
            queryset = queryset.filter(skills_q)

        # Order by posted_date (newest first)
        queryset = queryset.order_by('-posted_date', '-created_at')

        # Apply pagination
        page_size = min(int(request.query_params.get('limit', 20)), 50)  # Max 50 results
        page = int(request.query_params.get('page', 1))
        start = (page - 1) * page_size
        end = start + page_size
        
        # Get total count
        total_count = queryset.count()
        
        # Get paginated results
        jobs_list = list(queryset[start:end])

        # Use existing JobListSerializer
        serializer = JobListSerializer(jobs_list, many=True, context={'request': request})

        # Prepare pagination URLs
        next_url = None
        previous_url = None
        
        if end < total_count:
            next_url = f"{request.build_absolute_uri(request.path)}?page={page + 1}&limit={page_size}"
            if valid_params.get('title'):
                next_url += f"&title={valid_params['title']}"
            if valid_params.get('company'):
                next_url += f"&company={valid_params['company']}"
            if valid_params.get('location'):
                next_url += f"&location={valid_params['location']}"
        
        if page > 1:
            previous_url = f"{request.build_absolute_uri(request.path)}?page={page - 1}&limit={page_size}"
            if valid_params.get('title'):
                previous_url += f"&title={valid_params['title']}"
            if valid_params.get('company'):
                previous_url += f"&company={valid_params['company']}"
            if valid_params.get('location'):
                previous_url += f"&location={valid_params['location']}"

        # Prepare response data
        search_result_data = {
            'count': total_count,
            'next': next_url,
            'previous': previous_url,
            'results': serializer.data
        }
        
        return Response(search_result_data)


@extend_schema(
    summary="Get job recommendations",
    description="Get AI-powered personalized job recommendations based on user profile. Supports filtering by recommendation status.",
    tags=['Jobs', 'Recommendations'], # Added Recommendations tag
    parameters=[
        OpenApiParameter(
            name='status',
            description="Filter recommendations by status (e.g., 'pending_review', 'viewed'). Multiple statuses can be comma-separated.",
            required=False,
            type=OpenApiTypes.STR
        )
    ],
    responses={
        200: RecommendedJobSerializer(many=True), # Use the new serializer
        401: ErrorResponseSerializer
    }
)
class JobRecommendationsView(generics.ListAPIView): # Changed to ListAPIView
    """
    API endpoint to retrieve personalized job recommendations for the authenticated user.
    
    Recommendations are generated by an AI-powered matching algorithm and can be
    filtered by their interaction status (e.g., 'pending_review', 'viewed', 'dismissed').
    Results are ordered by match score (highest first) and then by recommendation date.
    """
    serializer_class = RecommendedJobSerializer
    permission_classes = [permissions.IsAuthenticated]
    # pagination_class = StandardResultsSetPagination # Add pagination if needed

    def get_queryset(self):
        """
        Return job recommendations for the current user, optionally filtered by status.
        """
        user = self.request.user
        queryset = RecommendedJob.objects.filter(user=user)

        status_param = self.request.query_params.get('status')
        if status_param:
            statuses = [s.strip() for s in status_param.split(',') if s.strip()]
            # Validate statuses against model choices if necessary
            valid_statuses = [choice[0] for choice in RecommendedJob.STATUS_CHOICES]
            statuses_to_filter = [s for s in statuses if s in valid_statuses]
            if statuses_to_filter:
                queryset = queryset.filter(status__in=statuses_to_filter)
            else: # If invalid statuses are provided, maybe return empty or ignore filter
                logger.warning(f"Invalid status values provided for recommendation filter: {statuses}")
                # Depending on desired behavior, could return queryset.none() or just proceed without status filter
        else:
            # Default to showing 'pending_review' and 'viewed' if no status filter is applied
            queryset = queryset.filter(status__in=['pending_review', 'viewed'])
        
        return queryset.select_related('job').order_by('-score', '-recommended_at')

    # If PATCH for status update is desired on this view (if it were a RetrieveUpdateAPIView or ViewSet action):
    # @extend_schema(
    #     summary="Update recommendation status",
    #     request=serializers.SerializerMethodField(method_name='get_status_update_serializer'), # Placeholder
    #     responses={200: RecommendedJobSerializer}
    # )
    # @action(detail=True, methods=['patch'])
    # def update_status(self, request, pk=None):
    #     recommendation = self.get_object() # Would need get_object if detail view
    #     new_status = request.data.get('status')
    #     if new_status and any(new_status == choice[0] for choice in RecommendedJob.STATUS_CHOICES):
    #         recommendation.status = new_status
    #         recommendation.save(update_fields=['status', 'updated_at'])
    #         serializer = self.get_serializer(recommendation)
    #         return Response(serializer.data)
    #     return Response({'error': 'Invalid status provided.'}, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(
    summary="Generate Job Recommendations",
    description="Triggers the generation of new job recommendations for the authenticated user.",
    tags=['Jobs', 'Recommendations'],
    request=None,
    responses={
        200: SuccessResponseSerializer,
        404: ErrorResponseSerializer,
        500: ErrorResponseSerializer
    }
)
class GenerateRecommendationsView(APIView):
    """
    API endpoint to trigger the generation of job recommendations for the authenticated user.
    
    This endpoint calls the JobMatchService to find relevant jobs based on the user's profile,
    filters out jobs they've already interacted with, and stores the new recommendations.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        user = request.user
        try:
            # The user model should have a one-to-one relation to a profile model.
            # Common practice is to name it 'userprofile' or 'profile'.
            # Let's assume it's 'profile' as used in the service.
            if not hasattr(user, 'profile'):
                logger.warning(f"User {user.id} does not have a profile to generate recommendations.")
                return Response(
                    {"error": "User profile not found. Recommendations cannot be generated without a profile."},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            user_profile_id = user.profile.id
            
            service = JobMatchService()
            # The number of recommendations can be a parameter if needed
            recommendations_result = service.generate_recommendations_for_user(user_profile_id=user_profile_id)
            
            return Response({
                "success": True,
                "message": f"Successfully generated {len(recommendations_result)} new or updated recommendations.",
                "data": recommendations_result
            }, status=status.HTTP_200_OK)
        except Exception as e:
            logger.error(f"An unexpected error occurred while generating recommendations for user {user.id}: {e}", exc_info=True)
            return Response(
                {"error": "An internal error occurred while generating recommendations."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


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
        from apps.integrations.tasks import run_skyvern_application_task
        from apps.accounts.models import UserProfile

        serializer = BulkApplySerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        job_ids = serializer.validated_data['job_ids']
        user = request.user

        try:
            profile = user.profile
        except UserProfile.DoesNotExist:
            return Response(
                {"error": "User profile not found. A complete profile with a resume is required for auto-apply."},
                status=status.HTTP_400_BAD_REQUEST
            )

        if not profile.resume:
            return Response(
                {"error": "Resume not found in profile. Please upload a resume before using auto-apply."},
                status=status.HTTP_400_BAD_REQUEST
            )

        queued_jobs = []
        for job_id in job_ids:
            try:
                job = Job.objects.get(id=job_id, status='active')
                
                # Optional: Check if already applied through Jobraker
                if Application.objects.filter(user=user, job=job).exists():
                    logger.warning(f"User {user.id} attempting to auto-apply to already applied job {job.id}. Skipping.")
                    continue

                # Queue the Skyvern task
                task = run_skyvern_application_task.delay(
                    user_id=str(user.id),
                    job_id=str(job.id)
                )
                queued_jobs.append({"job_id": str(job.id), "task_id": task.id})
                logger.info(f"Queued Skyvern application task {task.id} for user {user.id} and job {job.id}")

            except Job.DoesNotExist:
                logger.warning(f"Auto-apply requested for non-existent or inactive job_id: {job_id}")
                continue
        
        return Response({
            'message': f'Auto-apply process started for {len(queued_jobs)} jobs.',
            'queued_jobs': queued_jobs
        }, status=status.HTTP_202_ACCEPTED)


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
                            "id": "550e8400-e29b-41a716-446655440000",
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
