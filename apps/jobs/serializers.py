"""
Serializers for jobs app API endpoints.
"""

from rest_framework import serializers
from .models import Job, Application, SavedJob, JobAlert, JobSource


class JobSerializer(serializers.ModelSerializer):
    """Serializer for Job model."""
    salary_range_display = serializers.ReadOnlyField()
    is_expired = serializers.ReadOnlyField()
    
    class Meta:
        model = Job
        fields = '__all__'
        read_only_fields = ('id', 'created_at', 'updated_at', 'view_count', 'application_count', 'processed_for_matching')


class JobListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for job listings."""
    salary_range_display = serializers.ReadOnlyField()
    
    class Meta:
        model = Job
        fields = (
            'id', 'title', 'company', 'location', 'job_type', 'experience_level',
            'salary_min', 'salary_max', 'salary_range_display', 'is_remote',
            'posted_date', 'external_url', 'company_logo_url', 'view_count'
        )


class ApplicationSerializer(serializers.ModelSerializer):
    """Serializer for Application model."""
    job = JobListSerializer(read_only=True)
    job_id = serializers.UUIDField(write_only=True)
    
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


class SavedJobSerializer(serializers.ModelSerializer):
    """Serializer for SavedJob model."""
    job = JobListSerializer(read_only=True)
    
    class Meta:
        model = SavedJob
        fields = '__all__'
        read_only_fields = ('id', 'user', 'created_at')


class JobAlertSerializer(serializers.ModelSerializer):
    """Serializer for JobAlert model."""
    
    class Meta:
        model = JobAlert
        fields = '__all__'
        read_only_fields = ('id', 'user', 'created_at', 'updated_at', 'last_run')


class JobSourceSerializer(serializers.ModelSerializer):
    """Serializer for JobSource model."""
    
    class Meta:
        model = JobSource
        fields = '__all__'
        read_only_fields = (
            'id', 'created_at', 'updated_at', 'last_sync_at',
            'total_jobs_fetched', 'successful_syncs', 'failed_syncs'
        )


class JobSearchSerializer(serializers.Serializer):
    """Serializer for job search parameters."""
    title = serializers.CharField(required=False, max_length=200)
    company = serializers.CharField(required=False, max_length=100)
    location = serializers.CharField(required=False, max_length=100)
    job_type = serializers.ChoiceField(choices=Job.JOB_TYPES, required=False)
    experience_level = serializers.ChoiceField(choices=Job.EXPERIENCE_LEVELS, required=False)
    min_salary = serializers.IntegerField(required=False, min_value=0)
    max_salary = serializers.IntegerField(required=False, min_value=0)
    is_remote = serializers.BooleanField(required=False)
    skills = serializers.ListField(child=serializers.CharField(), required=False)
    
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
