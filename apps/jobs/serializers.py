"""
Serializers for jobs app API endpoints.
"""

from rest_framework import serializers
from drf_spectacular.utils import extend_schema_serializer, OpenApiExample
from .models import Job, Application, SavedJob, JobAlert, JobSource


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
        read_only_fields = ('id', 'user', 'created_at', 'updated_at', 'match_score')
    
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


class BulkApplySerializer(serializers.Serializer):
    """Serializer for bulk job application."""
    job_ids = serializers.ListField(
        child=serializers.UUIDField(),
        min_length=1,
        max_length=50
    )
    cover_letter = serializers.CharField(required=False, max_length=5000)
    
    def validate_job_ids(self, value):
        """Validate that all job IDs exist."""
        existing_jobs = Job.objects.filter(id__in=value).values_list('id', flat=True)
        missing_jobs = set(value) - set(existing_jobs)
        
        if missing_jobs:
            raise serializers.ValidationError(f"Jobs not found: {list(missing_jobs)}")
        
        return value
