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
    'fetch-adzuna-jobs': {
        'task': 'apps.integrations.tasks.fetch_adzuna_jobs',
        'schedule': 3600.0,  # Run every hour
    },
    'auto-apply-jobs': {
        'task': 'apps.jobs.tasks.auto_apply_matching_jobs',
        'schedule': 1800.0,  # Run every 30 minutes
    },
    'cleanup-old-notifications': {
        'task': 'apps.notifications.tasks.cleanup_old_notifications',
        'schedule': 86400.0,  # Run daily
    },
    'batch-generate-recommendations': {
        'task': 'apps.jobs.tasks.batch_generate_recommendations_for_active_users_task',
        'schedule': 86400.0,  # Run daily (24 * 60 * 60 seconds)
        # 'args': (), # Add any default arguments if needed
    },
    'process-job-alerts': {
        'task': 'apps.jobs.tasks.process_job_alerts_task',
        'schedule': 1800.0,  # Run every 30 minutes (30 * 60 seconds)
    },
    'send-application-follow-up-reminders': {
        'task': 'apps.jobs.tasks.send_application_follow_up_reminders',
        'schedule': crontab(hour=8, minute=0),  # Run daily at 8:00 AM UTC
    },
    'sync-unprocessed-jobs': {
        'task': 'apps.integrations.tasks_enhanced.sync_unprocessed_jobs',
        'schedule': 3600.0,  # Run every hour
    },
    'cleanup-old-embeddings': {
        'task': 'apps.integrations.tasks_enhanced.cleanup_old_embeddings',
        'schedule': crontab(hour=2, minute=0),  # Run daily at 2:00 AM UTC
    },
    'reindex-vector-database': {
        'task': 'apps.integrations.tasks_enhanced.reindex_vector_database',
        'schedule': crontab(hour=3, minute=0, day_of_week=1),  # Run weekly on Monday at 3:00 AM UTC
    },
}

@app.task(bind=True)
def debug_task(self):
    """Debug task for testing Celery setup."""
    print(f'Request: {self.request!r}')
