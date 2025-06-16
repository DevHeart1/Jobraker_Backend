from django.contrib import admin
from .models import Job, Application, SavedJob, JobAlert, JobSource


@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    """Admin configuration for Job model."""
    list_display = ('title', 'company', 'location', 'job_type', 'experience_level', 'status', 'posted_date')
    list_filter = ('job_type', 'experience_level', 'status', 'is_remote', 'external_source', 'created_at')
    search_fields = ('title', 'company', 'location', 'description', 'external_id')
    ordering = ('-created_at',)
    date_hierarchy = 'created_at'
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('title', 'company', 'description', 'requirements', 'benefits')
        }),
        ('Location & Remote', {
            'fields': ('location', 'city', 'state', 'country', 'is_remote', 'remote_type')
        }),
        ('Employment Details', {
            'fields': ('job_type', 'experience_level', 'status')
        }),
        ('Salary Information', {
            'fields': ('salary_min', 'salary_max', 'salary_currency', 'salary_period')
        }),
        ('Skills & Technologies', {
            'fields': ('skills_required', 'skills_preferred', 'technologies')
        }),
        ('External Data', {
            'fields': ('external_id', 'external_source', 'external_url', 'company_logo_url')
        }),
        ('AI & Matching', {
            'fields': ('processed_for_matching',)
        }),
        ('Dates', {
            'fields': ('posted_date', 'application_deadline')
        }),
        ('Statistics', {
            'fields': ('view_count', 'application_count'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    
    readonly_fields = ('created_at', 'updated_at', 'view_count', 'application_count')


@admin.register(Application)
class ApplicationAdmin(admin.ModelAdmin):
    """Admin configuration for Application model."""
    list_display = ('user', 'job', 'status', 'application_type', 'match_score', 'applied_at')
    list_filter = ('status', 'application_type', 'auto_applied', 'ai_generated_cover_letter', 'created_at')
    search_fields = ('user__email', 'job__title', 'job__company', 'external_application_id')
    ordering = ('-created_at',)
    date_hierarchy = 'created_at'
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('user', 'job', 'status', 'application_type')
        }),
        ('Documents', {
            'fields': ('resume_used', 'cover_letter', 'additional_documents')
        }),
        ('External Data', {
            'fields': ('application_url', 'external_application_id', 'skyvern_task_id')
        }),
        ('AI & Automation', {
            'fields': ('match_score', 'auto_applied', 'ai_generated_cover_letter')
        }),
        ('Communication', {
            'fields': ('last_contact_date', 'interview_date', 'follow_up_date')
        }),
        ('Notes & Feedback', {
            'fields': ('notes', 'feedback_received', 'submission_logs')
        }),
        ('Timestamps', {
            'fields': ('applied_at', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    
    readonly_fields = ('created_at', 'updated_at')


@admin.register(SavedJob)
class SavedJobAdmin(admin.ModelAdmin):
    """Admin configuration for SavedJob model."""
    list_display = ('user', 'job', 'category', 'created_at')
    list_filter = ('category', 'created_at')
    search_fields = ('user__email', 'job__title', 'job__company', 'notes')
    ordering = ('-created_at',)


@admin.register(JobAlert)
class JobAlertAdmin(admin.ModelAdmin):
    """Admin configuration for JobAlert model."""
    list_display = ('user', 'name', 'frequency', 'is_active', 'last_run')
    list_filter = ('frequency', 'is_active', 'email_notifications', 'push_notifications', 'remote_only')
    search_fields = ('user__email', 'name', 'keywords', 'location')
    ordering = ('-created_at',)


@admin.register(JobSource)
class JobSourceAdmin(admin.ModelAdmin):
    """Admin configuration for JobSource model."""
    list_display = ('name', 'source_type', 'is_active', 'total_jobs_fetched', 'last_sync_at')
    list_filter = ('source_type', 'is_active', 'created_at')
    search_fields = ('name', 'base_url', 'api_endpoint')
    ordering = ('name',)
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'source_type', 'base_url', 'api_endpoint', 'is_active')
        }),
        ('Configuration', {
            'fields': ('configuration', 'rate_limit_per_hour', 'rate_limit_per_day')
        }),
        ('API Credentials', {
            'fields': ('api_key', 'api_secret'),
            'classes': ('collapse',)
        }),
        ('Statistics', {
            'fields': ('last_sync_at', 'total_jobs_fetched', 'successful_syncs', 'failed_syncs'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    
    readonly_fields = ('created_at', 'updated_at', 'total_jobs_fetched', 'successful_syncs', 'failed_syncs')
