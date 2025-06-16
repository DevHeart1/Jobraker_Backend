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
        ('pending', 'Pending'),
        ('submitted', 'Submitted'),
        ('under_review', 'Under Review'),
        ('interview_scheduled', 'Interview Scheduled'),
        ('interview_completed', 'Interview Completed'),
        ('offer_received', 'Offer Received'),
        ('accepted', 'Accepted'),
        ('rejected', 'Rejected'),
        ('withdrawn', 'Withdrawn'),
        ('failed', 'Failed to Submit'),
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
    skyvern_task_id = models.CharField(max_length=100, blank=True)
    submission_logs = models.JSONField(default=list, help_text="Application submission logs")
    
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
