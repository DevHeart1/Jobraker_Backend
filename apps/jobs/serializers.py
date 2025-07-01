"""
Serializers for jobs app API endpoints.
"""

from rest_framework import serializers
from drf_spectacular.utils import extend_schema_serializer, OpenApiExample
from .models import Job, Application, SavedJob, JobAlert, JobSource, RecommendedJob # Added RecommendedJob


@extend_schema_serializer(
    examples=[
        OpenApiExample(
            'Job Detail Example',
            summary='Complete job information',
            description='Full job details including company info, requirements, and metadata',
            value={
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "title": "Senior Python Developer",
                "company": "TechCorp Inc.",
                "location": "San Francisco, CA",
                "job_type": "full_time",
                "experience_level": "senior",
                "salary_min": 120000,
                "salary_max": 160000,
                "salary_range_display": "$120,000 - $160,000",
                "is_remote": True,
                "description": "We are looking for an experienced Python developer...",
                "requirements": "5+ years Python experience, Django, PostgreSQL",
                "skills": ["Python", "Django", "PostgreSQL", "AWS"],
                "posted_date": "2025-06-15T10:00:00Z",
                "expires_at": "2025-07-15T23:59:59Z",
                "external_url": "https://example.com/jobs/123",
                "company_logo_url": "https://example.com/logo.png",
                "view_count": 245,
                "application_count": 12,
                "is_expired": False,
                "created_at": "2025-06-15T10:00:00Z",
                "updated_at": "2025-06-15T10:00:00Z"
            }
        )
    ]
)
class JobSerializer(serializers.ModelSerializer):
    """
    Complete serializer for Job model with full details.
    
    Used for job detail views and job creation/updates.
    Includes computed fields like salary_range_display and is_expired.
    """
    salary_range_display = serializers.ReadOnlyField()
    is_expired = serializers.ReadOnlyField()
    
    class Meta:
        model = Job
        fields = '__all__'
        read_only_fields = ('id', 'created_at', 'updated_at', 'view_count', 'application_count', 'processed_for_matching')


@extend_schema_serializer(
    examples=[
        OpenApiExample(
            'Job List Item Example',
            summary='Lightweight job information for listings',
            description='Essential job details optimized for job listing views',
            value={
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "title": "Senior Python Developer",
                "company": "TechCorp Inc.",
                "location": "San Francisco, CA",
                "job_type": "full_time",
                "experience_level": "senior",
                "salary_min": 120000,
                "salary_max": 160000,
                "salary_range_display": "$120,000 - $160,000",
                "is_remote": True,
                "posted_date": "2025-06-15T10:00:00Z",
                "external_url": "https://example.com/jobs/123",
                "company_logo_url": "https://example.com/logo.png",
                "view_count": 245
            }
        )
    ]
)
class JobListSerializer(serializers.ModelSerializer):
    """
    Lightweight serializer for job listings and embedded job references.
    
    Optimized for performance with only essential fields.
    Used in job search results, recommendations, and as nested serializer.
    """
    salary_range_display = serializers.ReadOnlyField()
    
    class Meta:
        model = Job
        fields = (
            'id', 'title', 'company', 'location', 'job_type', 'experience_level',
            'salary_min', 'salary_max', 'salary_range_display', 'is_remote',
            'posted_date', 'external_url', 'company_logo_url', 'view_count'
        )


@extend_schema_serializer(
    examples=[
        OpenApiExample(
            'Application Create Request',
            summary='Create new job application',
            description='Request body for creating a new job application',
            value={
                "job_id": "550e8400-e29b-41d4-a716-446655440000",
                "cover_letter": "I am very interested in this position because...",
                "resume_url": "https://example.com/resume.pdf",
                "status": "pending"
            },
            request_only=True
        ),
        OpenApiExample(
            'Application Response',
            summary='Job application with details',
            description='Complete application information including job details',
            value={
                "id": "660f9500-f39c-52e5-b827-557766551111",
                "job": {
                    "id": "550e8400-e29b-41d4-a716-446655440000",
                    "title": "Senior Python Developer",
                    "company": "TechCorp Inc.",
                    "location": "San Francisco, CA",
                    "salary_range_display": "$120,000 - $160,000"
                },
                "cover_letter": "I am very interested in this position because...",
                "resume_url": "https://example.com/resume.pdf",
                "status": "pending",
                "applied_at": "2025-06-15T14:30:00Z",
                "match_score": 85.5,
                "created_at": "2025-06-15T14:30:00Z",
                "updated_at": "2025-06-15T14:30:00Z"
            },
            response_only=True
        )
    ]
)
class ApplicationSerializer(serializers.ModelSerializer):
    """
    Serializer for job applications with nested job information.
    
    Handles creating applications with job_id lookup and provides
    complete application details including job information and matching score.
    """
    job = JobListSerializer(read_only=True)
    job_id = serializers.UUIDField(write_only=True, help_text="UUID of the job to apply for")
    
    class Meta:
        model = Application
        fields = '__all__'
        read_only_fields = (
            'id', 'user', 'created_at', 'updated_at',
            'match_score', 'follow_up_reminder_sent_at' # Added follow_up_reminder_sent_at
        )
    
    def create(self, validated_data):
        """Create application with job lookup."""
        job_id = validated_data.pop('job_id')
        job = Job.objects.get(id=job_id)
        validated_data['job'] = job
        return super().create(validated_data)


@extend_schema_serializer(
    examples=[
        OpenApiExample(
            'Saved Job Example',
            summary='Saved job with job details',
            description='A job saved by the user for later reference',
            value={
                "id": "770fa600-f49d-63f6-c938-668877662222",
                "job": {
                    "id": "550e8400-e29b-41d4-a716-446655440000",
                    "title": "Senior Python Developer",
                    "company": "TechCorp Inc.",
                    "location": "San Francisco, CA",
                    "salary_range_display": "$120,000 - $160,000",
                    "is_remote": True,
                    "posted_date": "2025-06-15T10:00:00Z"
                },
                "notes": "Interesting role, good company culture",
                "created_at": "2025-06-15T16:45:00Z"
            }
        )
    ]
)
class SavedJobSerializer(serializers.ModelSerializer):
    """
    Serializer for saved jobs with nested job information.
    
    Allows users to bookmark jobs for later review.
    Includes full job details for easy reference.
    """
    job = JobListSerializer(read_only=True)
    
    class Meta:
        model = SavedJob
        fields = '__all__'
        read_only_fields = ('id', 'user', 'created_at')


@extend_schema_serializer(
    examples=[
        OpenApiExample(
            'Job Alert Create Request',
            summary='Create job alert',
            description='Request to create a new job alert with search criteria',
            value={
                "name": "Python Developer Alerts",
                "title": "Python Developer",
                "location": "San Francisco",
                "job_type": "full_time",
                "experience_level": "senior",
                "min_salary": 100000,
                "is_remote": True,
                "skills": ["Python", "Django", "PostgreSQL"],
                "is_active": True,
                "frequency": "daily"
            },
            request_only=True
        ),
        OpenApiExample(
            'Job Alert Response',
            summary='Job alert with metadata',
            description='Complete job alert information including execution status',
            value={
                "id": "880fb700-f59e-74g7-d049-779988773333",
                "name": "Python Developer Alerts",
                "title": "Python Developer",
                "location": "San Francisco",
                "job_type": "full_time",
                "experience_level": "senior",
                "min_salary": 100000,
                "is_remote": True,
                "skills": ["Python", "Django", "PostgreSQL"],
                "is_active": True,
                "frequency": "daily",
                "last_run": "2025-06-15T09:00:00Z",
                "created_at": "2025-06-10T12:00:00Z",
                "updated_at": "2025-06-15T12:30:00Z"
            },
            response_only=True
        )
    ]
)
class JobAlertSerializer(serializers.ModelSerializer):
    """
    Serializer for job alerts with automated job matching.
    
    Users can create alerts based on search criteria to receive
    notifications when matching jobs are posted.
    """
    
    class Meta:
        model = JobAlert
        fields = '__all__'
        read_only_fields = ('id', 'user', 'created_at', 'updated_at', 'last_run')


@extend_schema_serializer(
    examples=[
        OpenApiExample(
            'Job Source Example',
            summary='Job aggregation source',
            description='Configuration and statistics for job data sources',
            value={
                "id": "990fc800-f69f-85h8-e159-889999884444",
                "name": "Indeed API",
                "source_type": "api",
                "base_url": "https://api.indeed.com",
                "api_key_required": True,
                "is_active": True,
                "sync_frequency": "hourly",
                "last_sync_at": "2025-06-15T14:00:00Z",
                "total_jobs_fetched": 15432,
                "successful_syncs": 156,
                "failed_syncs": 2,
                "created_at": "2025-01-01T00:00:00Z",
                "updated_at": "2025-06-15T14:00:00Z"
            }
        )
    ]
)
class JobSourceSerializer(serializers.ModelSerializer):
    """
    Serializer for job data sources and aggregation services.
    
    Manages external job sources like Indeed, LinkedIn, etc.
    Includes sync statistics and configuration.
    """
    
    class Meta:
        model = JobSource
        fields = '__all__'
        read_only_fields = (
            'id', 'created_at', 'updated_at', 'last_sync_at',
            'total_jobs_fetched', 'successful_syncs', 'failed_syncs'
        )


@extend_schema_serializer(
    examples=[
        OpenApiExample(
            'Job Search Request',
            summary='Advanced job search parameters',
            description='Flexible search parameters for finding relevant jobs',
            value={
                "title": "Python Developer",
                "company": "TechCorp",
                "location": "San Francisco",
                "job_type": "full_time",
                "experience_level": "senior",
                "min_salary": 100000,
                "max_salary": 150000,
                "is_remote": True,
                "skills": ["Python", "Django", "PostgreSQL", "AWS"]
            }
        )
    ]
)
class JobSearchSerializer(serializers.Serializer):
    """
    Serializer for advanced job search parameters with validation.
    
    Supports flexible filtering by title, company, location, salary,
    job type, experience level, remote work, and required skills.
    """
    title = serializers.CharField(
        required=False, 
        max_length=200,
        help_text="Job title or keywords to search for"
    )
    company = serializers.CharField(
        required=False, 
        max_length=100,
        help_text="Company name or partial match"
    )
    location = serializers.CharField(
        required=False, 
        max_length=100,
        help_text="Job location (city, state, or country)"
    )
    job_type = serializers.ChoiceField(
        choices=Job.JOB_TYPES, 
        required=False,
        help_text="Employment type (full_time, part_time, contract, etc.)"
    )
    experience_level = serializers.ChoiceField(
        choices=Job.EXPERIENCE_LEVELS, 
        required=False,
        help_text="Required experience level"
    )
    min_salary = serializers.IntegerField(
        required=False, 
        min_value=0,
        help_text="Minimum salary requirement"
    )
    max_salary = serializers.IntegerField(
        required=False, 
        min_value=0,
        help_text="Maximum salary range"
    )
    is_remote = serializers.BooleanField(
        required=False,
        help_text="Filter for remote work opportunities"
    )
    skills = serializers.ListField(
        child=serializers.CharField(), 
        required=False,
        help_text="List of required or preferred skills"
    )
    
    def validate(self, attrs):
        """Validate search parameters."""
        min_salary = attrs.get('min_salary')
        max_salary = attrs.get('max_salary')
        
        if min_salary and max_salary and min_salary > max_salary:
            raise serializers.ValidationError("Min salary cannot be greater than max salary")
        
        return attrs


@extend_schema_serializer(
    examples=[
        OpenApiExample(
            'Bulk Apply Request',
            summary='Apply to multiple jobs at once',
            description='Efficient bulk application to multiple job positions',
            value={
                "job_ids": [
                    "550e8400-e29b-41d4-a716-446655440000",
                    "660f9500-f39c-52e5-b827-557766551111",
                    "770fa600-f49d-63f6-c938-668877662222"
                ],
                "cover_letter": "I am interested in applying to these positions because of my relevant experience in Python development and my passion for building innovative solutions..."
            },
            request_only=True
        ),
        OpenApiExample(
            'Bulk Apply Response',
            summary='Bulk application results',
            description='Results of bulk application operation with success/failure details',
            value={
                "successful_applications": 2,
                "failed_applications": 1,
                "details": [
                    {
                        "job_id": "550e8400-e29b-41d4-a716-446655440000",
                        "status": "success",
                        "application_id": "aa0fb700-f59e-74g7-d049-779988771111"
                    },
                    {
                        "job_id": "660f9500-f39c-52e5-b827-557766551111",
                        "status": "success",
                        "application_id": "bb0fb700-f59e-74g7-d049-779988772222"
                    },
                    {
                        "job_id": "770fa600-f49d-63f6-c938-668877662222",
                        "status": "failed",
                        "error": "Already applied to this job"
                    }
                ]
            },
            response_only=True
        )
    ]
)
class BulkApplySerializer(serializers.Serializer):
    """
    Serializer for bulk job application operations.
    
    Allows users to apply to multiple jobs simultaneously with
    a single cover letter. Validates job existence and handles
    bulk processing efficiently.
    """
    job_ids = serializers.ListField(
        child=serializers.UUIDField(),
        min_length=1,
        max_length=50,
        help_text="List of job UUIDs to apply to (max 50 jobs)"
    )
    cover_letter = serializers.CharField(
        required=False, 
        max_length=5000,
        help_text="Cover letter to use for all applications"
    )
    
    def validate_job_ids(self, value):
        """Validate that all job IDs exist."""
        existing_jobs = Job.objects.filter(id__in=value).values_list('id', flat=True)
        missing_jobs = set(value) - set(existing_jobs)
        
        if missing_jobs:
            raise serializers.ValidationError(f"Jobs not found: {list(missing_jobs)}")
        
        return value


@extend_schema_serializer(
    examples=[
        OpenApiExample(
            'Job Search Results',
            summary='Paginated job search results',
            description='Search results with pagination and filtering metadata',
            value={
                "count": 156,
                "next": "http://api.example.com/jobs/search/?page=2",
                "previous": None,
                "results": [
                    {
                        "id": "550e8400-e29b-41d4-a716-446655440000",
                        "title": "Senior Python Developer",
                        "company": "TechCorp Inc.",
                        "location": "San Francisco, CA",
                        "salary_range_display": "$120,000 - $160,000",
                        "is_remote": True,
                        "posted_date": "2025-06-15T10:00:00Z",
                        "match_score": 92.5
                    }
                ]
            }
        )
    ]
)
class JobSearchResultSerializer(serializers.Serializer):
    """
    Serializer for job search results with pagination and matching scores.
    
    Provides structured response for job search API endpoints
    with pagination metadata and AI-powered matching scores.
    """
    count = serializers.IntegerField(help_text="Total number of matching jobs")
    next = serializers.URLField(required=False, allow_null=True, help_text="URL for next page")
    previous = serializers.URLField(required=False, allow_null=True, help_text="URL for previous page")
    results = JobListSerializer(many=True, help_text="List of matching jobs")


@extend_schema_serializer(
    examples=[
        OpenApiExample(
            'Job Recommendations',
            summary='AI-powered job recommendations',
            description='Personalized job recommendations based on user profile and preferences',
            value={
                "recommendations": [
                    {
                        "id": "550e8400-e29b-41d4-a716-446655440000",
                        "title": "Senior Python Developer",
                        "company": "TechCorp Inc.",
                        "location": "San Francisco, CA",
                        "salary_range_display": "$120,000 - $160,000",
                        "is_remote": True,
                        "posted_date": "2025-06-15T10:00:00Z",
                        "match_score": 94.2,
                        "match_reasons": [
                            "Skills match: Python, Django, PostgreSQL",
                            "Experience level: Senior (5+ years)",
                            "Location preference: Remote work"
                        ]
                    }
                ],
                "total_recommendations": 25,
                "generated_at": "2025-06-16T08:00:00Z"
            }
        )
    ]
)
class JobRecommendationSerializer(serializers.Serializer):
    """
    Serializer for AI-powered job recommendations.
    
    Provides personalized job recommendations with matching scores
    and explanations for why jobs were recommended.
    """
    recommendations = JobListSerializer(many=True, help_text="List of recommended jobs")
    total_recommendations = serializers.IntegerField(help_text="Total number of available recommendations")
    generated_at = serializers.DateTimeField(help_text="When recommendations were generated")


@extend_schema_serializer(
    examples=[
        OpenApiExample(
            'Application Statistics',
            summary='User application statistics',
            description='Overview of user job application activity and success rates',
            value={
                "total_applications": 45,
                "pending_applications": 12,
                "interview_requests": 8,
                "offers_received": 3,
                "rejections": 22,
                "success_rate": 24.4,
                "average_response_time": 5.2,
                "most_applied_job_type": "full_time",
                "most_applied_location": "San Francisco, CA"
            }
        )
    ]
)
class ApplicationStatsSerializer(serializers.Serializer):
    """
    Serializer for application statistics and analytics.
    
    Provides insights into user application patterns and success rates.
    """
    total_applications = serializers.IntegerField(help_text="Total number of applications submitted")
    pending_applications = serializers.IntegerField(help_text="Applications waiting for response")
    interview_requests = serializers.IntegerField(help_text="Number of interview requests received")
    offers_received = serializers.IntegerField(help_text="Number of job offers received")
    rejections = serializers.IntegerField(help_text="Number of rejections received")
    success_rate = serializers.FloatField(help_text="Success rate percentage")
    average_response_time = serializers.FloatField(help_text="Average response time in days")
    most_applied_job_type = serializers.CharField(help_text="Most frequently applied job type")
    most_applied_location = serializers.CharField(help_text="Most frequently applied location")


@extend_schema_serializer(
    examples=[
        OpenApiExample(
            'Success Response',
            summary='Generic success response',
            description='Standard success response for operations',
            value={
                "success": True,
                "message": "Job saved successfully",
                "data": {
                    "job_id": "550e8400-e29b-41d4-a716-446655440000",
                    "saved_at": "2025-06-16T10:30:00Z"
                }
            }
        )
    ]
)
class SuccessResponseSerializer(serializers.Serializer):
    """
    Standard success response serializer.
    
    Used for operations that don't return complex data
    but need to confirm success with optional metadata.
    """
    success = serializers.BooleanField(default=True, help_text="Operation success status")
    message = serializers.CharField(help_text="Success message")
    data = serializers.DictField(required=False, help_text="Optional additional data")


@extend_schema_serializer(
    examples=[
        OpenApiExample(
            'Error Response',
            summary='Generic error response',
            description='Standard error response format',
            value={
                "success": False,
                "error": "Validation failed",
                "details": {
                    "job_id": ["This field is required."],
                    "cover_letter": ["Ensure this field has at most 5000 characters."]
                },
                "error_code": "VALIDATION_ERROR"
            }
        )
    ]
)
class ErrorResponseSerializer(serializers.Serializer):
    """
    Standard error response serializer.
    
    Provides consistent error response format across all endpoints.
    """
    success = serializers.BooleanField(default=False, help_text="Operation success status")
    error = serializers.CharField(help_text="Error message")
    details = serializers.DictField(required=False, help_text="Detailed error information")
    error_code = serializers.CharField(required=False, help_text="Machine-readable error code")


@extend_schema_serializer(
    examples=[
        OpenApiExample(
            'Recommended Job Example',
            summary='A single job recommendation for a user',
            description='Details of a job recommended to a user, including the match score and job info.',
            value={
                "id": "d8f8f8f8-f8f8-f8f8-f8f8-f8f8f8f8f8f8",
                "job": { # Using JobListSerializer structure
                    "id": "550e8400-e29b-41d4-a716-446655440000",
                    "title": "Senior Python Developer",
                    "company": "TechCorp Inc.",
                    "location": "San Francisco, CA",
                    "job_type": "full_time",
                    "experience_level": "senior",
                    "salary_min": 120000,
                    "salary_max": 160000,
                    "salary_range_display": "$120,000 - $160,000",
                    "is_remote": True,
                    "posted_date": "2025-06-15T10:00:00Z",
                    "external_url": "https://example.com/jobs/123",
                    "company_logo_url": "https://example.com/logo.png",
                    "view_count": 245
                },
                "score": 0.8875,
                "status": "pending_review",
                "algorithm_version": "v1.0_profile_match",
                "recommended_at": "2025-06-18T10:00:00Z",
                "updated_at": "2025-06-18T10:00:00Z"
            }
        )
    ]
)
class RecommendedJobSerializer(serializers.ModelSerializer):
    """
    Serializer for RecommendedJob model.
    Includes nested job details using JobListSerializer for brevity.
    Allows users to see their job recommendations and update their status.
    """
    job = JobListSerializer(read_only=True)
    # Allow status updates by the user, but other fields are mostly read-only from user's perspective
    # The user would typically interact by changing the status (e.g., 'viewed', 'dismissed', 'applied')

    class Meta:
        model = RecommendedJob
        fields = [
            'id',
            'job',
            'score',
            'status',
            'algorithm_version',
            'recommended_at',
            'updated_at'
        ]
        read_only_fields = ('id', 'job', 'score', 'algorithm_version', 'recommended_at', 'updated_at')
        # 'status' can be updated by the user through a PATCH request on a detail endpoint.
        # For a ListAPIView, this serializer would be read-only.
        # If allowing status updates, a separate serializer for PATCH might be cleaner or handle it in the view.

    # If status updates are allowed via this serializer on a detail view (e.g. PATCH /recommendations/{id}/)
    # you might want to limit the choices for status updates here.
    # For a simple list view, read_only_fields above is fine.
    # If PATCH is used for status:
    # def update(self, instance, validated_data):
    #     instance.status = validated_data.get('status', instance.status)
    #     # Potentially add logic here if changing status should trigger other actions
    #     instance.save()
    #     return instance
