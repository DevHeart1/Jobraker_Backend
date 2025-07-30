"""
Celery configuration for jobraker project.
"""

import os

from celery import Celery

# Set the default Django settings module for the 'celery' program.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "jobraker.settings.development")

from celery.schedules import crontab  # Added for daily scheduling

app = Celery("jobraker")

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
app.config_from_object("django.conf:settings", namespace="CELERY")

# Load task modules from all registered Django apps.
app.autodiscover_tasks()

# Task configurations
app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
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
    "automated-daily-job-sync": {
        "task": "apps.integrations.tasks.automated_daily_job_sync",
        "schedule": crontab(hour=6, minute=0),  # Run daily at 6:00 AM UTC
    },
    "process-pending-applications": {
        "task": "apps.integrations.tasks.process_pending_applications",
        "schedule": crontab(minute="*/30"),  # Run every 30 minutes
    },
    "batch-intelligent-job-matching": {
        "task": "apps.integrations.tasks.batch_intelligent_job_matching",
        "schedule": crontab(hour=8, minute=0),  # Run daily at 8:00 AM UTC
    },
    "weekly-system-maintenance": {
        "task": "apps.integrations.tasks.weekly_system_maintenance",
        "schedule": crontab(
            hour=2, minute=0, day_of_week=1
        ),  # Run weekly on Monday at 2:00 AM UTC
    },
    # === EXISTING JOB PROCESSING TASKS ===
    "fetch-adzuna-jobs": {
        "task": "apps.integrations.tasks.fetch_adzuna_jobs",
        "schedule": crontab(hour="*/4"),  # Run every 4 hours
    },
    "check-stale-skyvern-applications": {
        "task": "apps.integrations.tasks.check_stale_skyvern_applications",
        "schedule": crontab(
            hour="*/2"
        ),  # Run every 2 hours to catch stuck applications
    },
    "batch-generate-job-embeddings": {
        "task": "apps.integrations.tasks.batch_generate_job_embeddings",
        "schedule": crontab(hour="*/2"),  # Run every 2 hours
    },
    "batch-generate-user-embeddings": {
        "task": "apps.integrations.tasks.batch_generate_user_embeddings",
        "schedule": crontab(hour=1, minute=0),  # Run daily at 1:00 AM UTC
    },
    # === NOTIFICATION AND USER-FACING TASKS ===
    "send-daily-job-recommendations": {
        "task": "apps.notifications.tasks.send_daily_job_recommendations_task",
        "schedule": crontab(hour=9, minute=0),  # Daily at 9:00 AM UTC
    },
    "send-weekly-activity-summary": {
        "task": "apps.notifications.tasks.send_weekly_activity_summary_task",
        "schedule": crontab(
            hour=10, minute=0, day_of_week="saturday"
        ),  # Weekly on Saturday at 10:00 AM UTC
    },
    # === DATA & SYSTEM HEALTH TASKS ===
    "clean-up-old-job-listings": {
        "task": "apps.jobs.tasks.clean_up_old_job_listings_task",
        "schedule": crontab(
            hour=3, minute=0, day_of_week=0
        ),  # Weekly on Sunday at 3:00 AM UTC
    },
    "rebuild-embedding-index": {
        "task": "apps.integrations.tasks.rebuild_embedding_index_task",
        "schedule": crontab(
            hour=4, minute=0, day_of_week=0
        ),  # Weekly on Sunday at 4:00 AM UTC
    },
    "monitor-system-health": {
        "task": "apps.integrations.tasks.monitor_system_health_task",
        "schedule": crontab(minute="*/15"),  # Every 15 minutes
    },
}


@app.task(bind=True)
def debug_task(self):
    """Debug task for testing Celery setup."""
    print(f"Request: {self.request!r}")
