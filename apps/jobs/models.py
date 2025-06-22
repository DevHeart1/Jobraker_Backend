"""
Job management models for Jobraker.
"""

from django.db import models
from django.contrib.auth import get_user_model
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
from pgvector.django import VectorField
import uuid

User = get_user_model()


class Job(models.Model):
    """Job posting model with AI matching capabilities."""
    
    JOB_TYPES = [
        ('full_time', 'Full Time'),
        ('part_time', 'Part Time'),
        ('contract', 'Contract'),
        ('temporary', 'Temporary'),
        ('internship', 'Internship'),
        ('freelance', 'Freelance'),
    ]
    
    EXPERIENCE_LEVELS = [
        ('entry', 'Entry Level'),
        ('mid', 'Mid Level'),
        ('senior', 'Senior Level'),
        ('lead', 'Lead/Principal'),
        ('executive', 'Executive'),
    ]
    
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('closed', 'Closed'),
        ('filled', 'Filled'),
        ('paused', 'Paused'),
        ('draft', 'Draft'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Basic Job Information
    title = models.CharField(max_length=200, db_index=True)
    company = models.CharField(max_length=100, db_index=True)
    description = models.TextField()
    requirements = models.TextField(blank=True)
    benefits = models.TextField(blank=True)
    
    # Location and Remote Work
    location = models.CharField(max_length=100, db_index=True)
    city = models.CharField(max_length=50, blank=True)
    state = models.CharField(max_length=50, blank=True)
    country = models.CharField(max_length=50, default='US')
    is_remote = models.BooleanField(default=False)
    remote_type = models.CharField(
        max_length=20,
        choices=[
            ('no', 'No Remote'),
            ('hybrid', 'Hybrid'),
            ('full', 'Fully Remote'),
        ],
        default='no'
    )
    
    # Employment Details
    job_type = models.CharField(max_length=20, choices=JOB_TYPES, default='full_time')
    experience_level = models.CharField(max_length=20, choices=EXPERIENCE_LEVELS, default='mid')
    
    # Salary Information
    salary_min = models.PositiveIntegerField(null=True, blank=True)
    salary_max = models.PositiveIntegerField(null=True, blank=True)
    salary_currency = models.CharField(max_length=3, default='USD')
    salary_period = models.CharField(
        max_length=10,
        choices=[
            ('hourly', 'Hourly'),
            ('monthly', 'Monthly'),
            ('yearly', 'Yearly'),
        ],
        default='yearly'
    )
    
    # Skills and Technologies
    skills_required = models.JSONField(default=list, help_text="Required skills")
    skills_preferred = models.JSONField(default=list, help_text="Preferred skills")
    technologies = models.JSONField(default=list, help_text="Technologies used")
    
    # External Data
    external_id = models.CharField(max_length=100, blank=True, db_index=True)
    external_source = models.CharField(max_length=50, blank=True)  # adzuna, linkedin, etc.
    external_url = models.URLField(blank=True)
    company_logo_url = models.URLField(blank=True)
    
    # AI and Matching
    job_embedding = VectorField(dimensions=1536, null=True, blank=True)
    processed_for_matching = models.BooleanField(default=False)
    
    # Status and Metadata
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    posted_date = models.DateTimeField(null=True, blank=True)
    application_deadline = models.DateTimeField(null=True, blank=True)
    
    # Tracking
    view_count = models.PositiveIntegerField(default=0)
    application_count = models.PositiveIntegerField(default=0)
    
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'jobs'
        verbose_name = 'Job'
        verbose_name_plural = 'Jobs'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['title', 'company']),
            models.Index(fields=['location', 'is_remote']),
            models.Index(fields=['job_type', 'experience_level']),
            models.Index(fields=['status', '-created_at']),
            models.Index(fields=['external_source', 'external_id']),
        ]
    
    def __str__(self):
        return f"{self.title} at {self.company}"
    
    @property
    def salary_range_display(self):
        """Display salary range in a readable format."""
        if self.salary_min and self.salary_max:
            return f"${self.salary_min:,} - ${self.salary_max:,} {self.salary_period}"
        elif self.salary_min:
            return f"${self.salary_min:,}+ {self.salary_period}"
        return "Salary not disclosed"
    
    @property
    def is_expired(self):
        """Check if job application deadline has passed."""
        if self.application_deadline:
            return timezone.now() > self.application_deadline
        return False
    
    def increment_view_count(self):
        """Increment job view count."""
        self.view_count += 1
        self.save(update_fields=['view_count'])
    
    def increment_application_count(self):
        """Increment job application count."""
        self.application_count += 1
        self.save(update_fields=['application_count'])


class Application(models.Model):
    """Job application tracking model."""
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),                           # Initial state before any action
        ('submitting_via_skyvern', 'Submitting via Skyvern'), # Skyvern task initiated
        ('submitted', 'Submitted'),                       # Successfully submitted (by Skyvern or manually)
        ('under_review', 'Under Review'),                 # Application is being reviewed by employer
        ('interview_scheduled', 'Interview Scheduled'),
        ('interview_completed', 'Interview Completed'),
        ('offer_received', 'Offer Received'),
        ('accepted', 'Accepted'),
        ('rejected', 'Rejected'),
        ('withdrawn', 'Withdrawn'),                       # User withdrew application
        ('failed_to_submit', 'Failed to Submit'),         # Generic submission failure (manual or other)
        ('skyvern_submission_failed', 'Skyvern Submission Failed'), # Skyvern explicitly failed
        ('skyvern_canceled', 'Skyvern Task Canceled'),        # Skyvern task was canceled
        ('skyvern_requires_attention', 'Skyvern Task Requires Attention'), # Skyvern needs input/action
    ]
    
    APPLICATION_TYPES = [
        ('manual', 'Manual Application'),
        ('auto', 'Auto Application'),
        ('bulk', 'Bulk Application'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Core Relationships
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='applications')
    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name='applications')
    
    # Application Details
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='pending')
    application_type = models.CharField(max_length=20, choices=APPLICATION_TYPES, default='manual')
    
    # Documents and Content
    resume_used = models.FileField(upload_to='applications/resumes/', blank=True)
    cover_letter = models.TextField(blank=True)
    additional_documents = models.JSONField(default=list, help_text="Additional document URLs")
    
    # Application Process Data
    application_url = models.URLField(blank=True)
    external_application_id = models.CharField(max_length=100, blank=True)
    
    # AI and Automation
    match_score = models.FloatField(
        null=True, 
        blank=True,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
        help_text="AI-calculated job match score (0-1)"
    )
    auto_applied = models.BooleanField(default=False)
    ai_generated_cover_letter = models.BooleanField(default=False)
    
    # Communication Tracking
    last_contact_date = models.DateTimeField(null=True, blank=True)
    interview_date = models.DateTimeField(null=True, blank=True)
    follow_up_date = models.DateTimeField(null=True, blank=True)
    
    # External Integration Data
    skyvern_task_id = models.CharField(max_length=100, blank=True, db_index=True, help_text="Task ID from Skyvern for auto-applications.")
    skyvern_response_data = models.JSONField(null=True, blank=True, help_text="Raw response data from Skyvern task results (e.g., confirmation, errors).")
    submission_logs = models.JSONField(default=list, help_text="Application submission logs (can include Skyvern logs or manual entries).")
    
    # Notes and Feedback
    notes = models.TextField(blank=True)
    feedback_received = models.TextField(blank=True)
    
    # Timestamps
    applied_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'applications'
        verbose_name = 'Application'
        verbose_name_plural = 'Applications'
        ordering = ['-created_at']
        unique_together = ['user', 'job']  # Prevent duplicate applications
        indexes = [
            models.Index(fields=['user', 'status']),
            models.Index(fields=['job', 'status']),
            models.Index(fields=['application_type', '-created_at']),
            models.Index(fields=['auto_applied', 'match_score']),
        ]
    
    def __str__(self):
        return f"{self.user.get_full_name()} -> {self.job.title} at {self.job.company}"


class SavedJob(models.Model):
    """Model for jobs saved by users for later reference."""
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='saved_jobs')
    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name='saved_by')
    
    # Optional categorization
    category = models.CharField(max_length=50, blank=True, help_text="User-defined category")
    notes = models.TextField(blank=True, help_text="User notes about this job")
    
    # Tracking
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'saved_jobs'
        verbose_name = 'Saved Job'
        verbose_name_plural = 'Saved Jobs'
        unique_together = ['user', 'job']  # Prevent duplicate saves
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', '-created_at']),
        ]
    
    def __str__(self):
        return f"{self.user.get_full_name()} saved {self.job.title}"


class JobAlert(models.Model):
    """Model for job alerts/notifications based on user preferences."""
    
    FREQUENCY_CHOICES = [
        ('immediate', 'Immediate'),
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
        ('monthly', 'Monthly'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='job_alerts')
    
    # Alert Configuration
    name = models.CharField(max_length=100, help_text="User-defined name for this job alert.")
    keywords = models.JSONField(default=list, help_text="List of keywords or phrases to match in job titles or descriptions.")
    location = models.CharField(max_length=100, blank=True, help_text="Desired job location (e.g., city, state, 'remote').")
    job_type = models.CharField(max_length=20, choices=Job.JOB_TYPES, blank=True, help_text="Preferred employment type.")
    experience_level = models.CharField(max_length=20, choices=Job.EXPERIENCE_LEVELS, blank=True, help_text="Preferred experience level.")
    remote_only = models.BooleanField(default=False, help_text="If true, only include remote jobs.")
    
    # Salary preferences
    min_salary = models.PositiveIntegerField(null=True, blank=True, help_text="Minimum desired salary (annualized).")
    max_salary = models.PositiveIntegerField(null=True, blank=True, help_text="Maximum desired salary (annualized).")
    
    # Notification settings
    frequency = models.CharField(max_length=20, choices=FREQUENCY_CHOICES, default='daily', help_text="How often to send alert notifications.")
    email_notifications = models.BooleanField(default=True, help_text="Enable email notifications for this alert.")
    push_notifications = models.BooleanField(default=False, help_text="Enable push notifications for this alert (if supported).")
    
    # Status
    is_active = models.BooleanField(default=True, help_text="Is this alert currently active and running?")
    last_run = models.DateTimeField(null=True, blank=True, help_text="Timestamp of the last time this alert was processed.")
    
    # Tracking
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'job_alerts'
        verbose_name = 'Job Alert'
        verbose_name_plural = 'Job Alerts'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'is_active']),
            models.Index(fields=['frequency', 'last_run']),
        ]
    
    def __str__(self):
        return f"{self.user.get_full_name()}: {self.name}"


class JobSource(models.Model):
    """Model to track different job sources and their configurations."""
    
    SOURCE_TYPES = [
        ('api', 'API Integration'),
        ('scraper', 'Web Scraper'),
        ('manual', 'Manual Entry'),
        ('import', 'Data Import'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Source Information
    name = models.CharField(max_length=100, unique=True)
    source_type = models.CharField(max_length=20, choices=SOURCE_TYPES)
    base_url = models.URLField(blank=True)
    api_endpoint = models.URLField(blank=True)
    
    # Configuration
    is_active = models.BooleanField(default=True)
    configuration = models.JSONField(default=dict, help_text="Source-specific configuration")
    
    # API credentials (encrypted)
    api_key = models.CharField(max_length=200, blank=True)
    api_secret = models.CharField(max_length=200, blank=True)
    
    # Rate limiting
    rate_limit_per_hour = models.PositiveIntegerField(default=1000)
    rate_limit_per_day = models.PositiveIntegerField(default=10000)
    
    # Tracking
    last_sync_at = models.DateTimeField(null=True, blank=True)
    total_jobs_fetched = models.PositiveIntegerField(default=0)
    successful_syncs = models.PositiveIntegerField(default=0)
    failed_syncs = models.PositiveIntegerField(default=0)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'job_sources'
        verbose_name = 'Job Source'
        verbose_name_plural = 'Job Sources'
        ordering = ['name']
    
    def __str__(self):
        return f"{self.name} ({self.source_type})"
    
    def update_sync_stats(self, success=True, jobs_count=0):
        """Update synchronization statistics."""
        if success:
            self.successful_syncs += 1
            self.total_jobs_fetched += jobs_count
        else:
            self.failed_syncs += 1
        
        self.last_sync_at = timezone.now()
        self.save(update_fields=['successful_syncs', 'failed_syncs', 'total_jobs_fetched', 'last_sync_at'])


class RecommendedJob(models.Model):
    """
    Stores job recommendations generated for users.
    """
    STATUS_CHOICES = [
        ('pending_review', 'Pending Review'), # New recommendation, user hasn't seen it
        ('viewed', 'Viewed'),                 # User has seen the recommendation
        ('applied', 'Applied'),               # User initiated an application from this recommendation
        ('dismissed', 'Dismissed'),           # User indicated they are not interested
        ('irrelevant', 'Marked as Irrelevant'), # User explicitly marked it as a bad match
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='recommended_jobs')
    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name='recommendations_for_users')

    score = models.FloatField(
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)], # Assuming score is 0-1
        help_text="Similarity or match score (0.0 to 1.0)."
    )
    algorithm_version = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        help_text="Version of the recommendation algorithm used."
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending_review',
        db_index=True,
        help_text="User's interaction status with this recommendation."
    )

    recommended_at = models.DateTimeField(auto_now_add=True, db_index=True)
    # updated_at to track when status changes, etc.
    updated_at = models.DateTimeField(auto_now=True)


    class Meta:
        db_table = 'recommended_jobs'
        verbose_name = 'Recommended Job'
        verbose_name_plural = 'Recommended Jobs'
        unique_together = ('user', 'job') # A user should only have a specific job recommended once directly
        ordering = ['user', '-score', '-recommended_at']
        indexes = [
            models.Index(fields=['user', 'status', '-score']),
        ]

    def __str__(self):
        return f"Recommendation for {self.user.get_full_name()}: {self.job.title} (Score: {self.score:.3f})"
