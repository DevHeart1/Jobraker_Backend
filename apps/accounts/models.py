"""
User authentication and profile models for Jobraker.
"""

from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.core.validators import validate_email
import uuid

# Handle pgvector import gracefully for development
try:
    from pgvector.django import VectorField
    PGVECTOR_AVAILABLE = True
except ImportError:
    # Use JSONField for development without pgvector
    VectorField = models.JSONField
    PGVECTOR_AVAILABLE = False


class UserManager(BaseUserManager):
    """Custom user manager that uses email as the username field."""
    
    def create_user(self, email, password=None, **extra_fields):
        """Create and return a regular user with an email and password."""
        if not email:
            raise ValueError('The Email field must be set')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user
    
    def create_superuser(self, email, password=None, **extra_fields):
        """Create and return a superuser with an email and password."""
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)
        
        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')
        
        return self.create_user(email, password, **extra_fields)


class User(AbstractUser):
    """Extended user model with additional fields."""
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True, validators=[validate_email])
    is_verified = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Remove username field since we're using email
    username = None
    
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['first_name', 'last_name']
    
    objects = UserManager()
    
    class Meta:
        db_table = 'users'
        verbose_name = 'User'
        verbose_name_plural = 'Users'
    
    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.email})"


class UserProfile(models.Model):
    """Extended user profile with job search preferences and AI data."""
    
    EXPERIENCE_LEVELS = [
        ('entry', 'Entry Level (0-2 years)'),
        ('mid', 'Mid Level (3-5 years)'),
        ('senior', 'Senior Level (6-10 years)'),
        ('lead', 'Lead/Principal (10+ years)'),
        ('executive', 'Executive/C-Level'),
    ]
    
    JOB_TYPES = [
        ('full_time', 'Full Time'),
        ('part_time', 'Part Time'),
        ('contract', 'Contract'),
        ('freelance', 'Freelance'),
        ('internship', 'Internship'),
    ]
    
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    
    # Basic Information
    phone = models.CharField(max_length=20, blank=True)
    location = models.CharField(max_length=100, blank=True)
    linkedin_url = models.URLField(blank=True)
    github_url = models.URLField(blank=True)
    portfolio_url = models.URLField(blank=True)
    
    # Professional Information
    current_title = models.CharField(max_length=100, blank=True)
    current_company = models.CharField(max_length=100, blank=True)
    experience_level = models.CharField(max_length=20, choices=EXPERIENCE_LEVELS, default='entry')
    skills = models.JSONField(default=list, help_text="List of skills")
    industries = models.JSONField(default=list, help_text="Preferred industries")
    
    # Job Search Preferences
    preferred_locations = models.JSONField(default=list, help_text="Preferred job locations")
    job_types = models.JSONField(default=list, help_text="Preferred job types")
    salary_min = models.PositiveIntegerField(null=True, blank=True)
    salary_max = models.PositiveIntegerField(null=True, blank=True)
    remote_ok = models.BooleanField(default=True)
    
    # Resume and Documents
    resume = models.FileField(upload_to='resumes/', blank=True)
    cover_letter_template = models.TextField(blank=True)
    
    # AI and Automation Settings
    auto_apply_enabled = models.BooleanField(default=False)
    auto_apply_limit_daily = models.PositiveIntegerField(default=5)
    match_threshold = models.FloatField(default=0.7, help_text="Minimum match score for auto-apply")
    
    # Vector embeddings for semantic matching
    if PGVECTOR_AVAILABLE:
        profile_embedding = VectorField(dimensions=1536, null=True, blank=True)
        skills_embedding = VectorField(dimensions=1536, null=True, blank=True)
    else:
        # Fallback to TextField for development
        profile_embedding = models.TextField(null=True, blank=True, help_text="Vector embedding (JSON)")
        skills_embedding = models.TextField(null=True, blank=True, help_text="Vector embedding (JSON)")
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'user_profiles'
        verbose_name = 'User Profile'
        verbose_name_plural = 'User Profiles'
    
    def __str__(self):
        return f"Profile for {self.user.get_full_name()}"
    
    @property
    def full_name(self):
        return self.user.get_full_name()
    
    @property
    def is_complete(self):
        """Check if profile has minimum required information."""
        required_fields = [
            self.current_title,
            self.experience_level,
            self.skills,
            self.preferred_locations,
        ]
        return all(field for field in required_fields)
