"""
Celery configuration for jobraker project.
"""

import os
from celery import Celery

# Set the default Django settings module for the 'celery' program.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'jobraker.settings.development')

from celery.schedules import crontab # Added for daily scheduling

app = Celery('jobraker')

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Load task modules from all registered Django apps.
app.autodiscover_tasks()

# Task configurations
app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    task_track_started=True,
    task_time_limit=30 * 60,  # 30 minutes
    task_soft_time_limit=60,  # 1 minute
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=1000,
)

# Celery beat schedule for periodic tasks
app.conf.beat_schedule = {
    # === CRITICAL AUTOMATED TASKS ===
    'automated-daily-job-sync': {
        'task': 'apps.integrations.tasks.automated_daily_job_sync',
        'schedule': crontab(hour=6, minute=0),  # Run daily at 6:00 AM UTC
    },
    'process-pending-applications': {
        'task': 'apps.integrations.tasks.process_pending_applications',
        'schedule': crontab(minute='*/30'),  # Run every 30 minutes
    },
    'batch-intelligent-job-matching': {
        'task': 'apps.integrations.tasks.batch_intelligent_job_matching',
        'schedule': crontab(hour=8, minute=0),  # Run daily at 8:00 AM UTC
    },
    'weekly-system-maintenance': {
        'task': 'apps.integrations.tasks.weekly_system_maintenance',
        'schedule': crontab(hour=2, minute=0, day_of_week=1),  # Run weekly on Monday at 2:00 AM UTC
    },
    
    # === EXISTING JOB PROCESSING TASKS ===
    'fetch-adzuna-jobs': {
        'task': 'apps.integrations.tasks.fetch_adzuna_jobs',
        'schedule': crontab(hour='*/4'),  # Run every 4 hours
    },
    'batch-generate-job-embeddings': {
        'task': 'apps.integrations.tasks.batch_generate_job_embeddings',
        'schedule': crontab(hour='*/2'),  # Run every 2 hours
    },
    'batch-generate-user-embeddings': {
        'task': 'apps.integrations.tasks.batch_generate_user_embeddings',
        'schedule': crontab(hour=1, minute=0),  # Run daily at 1:00 AM UTC
    },
    
    # === NOTIFICATION AND COMMUNICATION TASKS ===
    'process-daily-job-alerts': {
        'task': 'apps.notifications.tasks.process_daily_job_alerts',
        'schedule': crontab(hour=9, minute=0),  # Run daily at 9:00 AM UTC
    },
    'process-weekly-job-alerts': {
        'task': 'apps.notifications.tasks.process_weekly_job_alerts',
        'schedule': crontab(hour=9, minute=0, day_of_week=1),  # Run weekly on Monday at 9:00 AM UTC
    },
    'send-weekly-job-recommendations': {
        'task': 'apps.notifications.tasks.send_weekly_job_recommendations',
        'schedule': crontab(hour=10, minute=0, day_of_week=1),  # Run weekly on Monday at 10:00 AM UTC
    },
    'send-application-follow-up-reminders': {
        'task': 'apps.notifications.tasks.send_application_follow_up_reminders',
        'schedule': crontab(hour=11, minute=0),  # Run daily at 11:00 AM UTC
    },
    
    # === LEGACY/OPTIONAL TASKS ===
    'auto-apply-jobs': {
        'task': 'apps.jobs.tasks.auto_apply_matching_jobs',
        'schedule': 1800.0,  # Run every 30 minutes (if implemented)
    },
    'cleanup-old-notifications': {
        'task': 'apps.notifications.tasks.cleanup_old_notifications',
        'schedule': crontab(hour=0, minute=0),  # Run daily at midnight
    },
    'batch-generate-recommendations': {
        'task': 'apps.jobs.tasks.batch_generate_recommendations_for_active_users_task',
        'schedule': crontab(hour=12, minute=0),  # Run daily at noon (if implemented)
    },
    'process-job-alerts': {
        'task': 'apps.jobs.tasks.process_job_alerts_task',
        'schedule': 1800.0,  # Run every 30 minutes (if implemented)
    },
    'sync-unprocessed-jobs': {
        'task': 'apps.integrations.tasks_enhanced.sync_unprocessed_jobs',
        'schedule': 3600.0,  # Run every hour (if implemented)
    },
    'cleanup-old-embeddings': {
        'task': 'apps.integrations.tasks_enhanced.cleanup_old_embeddings',
        'schedule': crontab(hour=3, minute=0),  # Run daily at 3:00 AM UTC (if implemented)
    },
    'reindex-vector-database': {
        'task': 'apps.integrations.tasks_enhanced.reindex_vector_database',
        'schedule': crontab(hour=4, minute=0, day_of_week=1),  # Run weekly on Monday at 4:00 AM UTC (if implemented)
    },
}

@app.task(bind=True)
def debug_task(self):
    """Debug task for testing Celery setup."""
    print(f'Request: {self.request!r}')
