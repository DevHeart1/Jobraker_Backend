"""
Enhanced Celery tasks for email automation and notifications.
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List

from celery import shared_task
from django.contrib.auth import get_user_model
from django.db.models import Q
from django.utils import timezone

from apps.jobs.models import Application, Job, JobAlert
from apps.jobs.services import JobMatchService
from apps.notifications.email_service import EmailService

logger = logging.getLogger(__name__)
User = get_user_model()


@shared_task(bind=True, max_retries=3)
def send_job_alert_email_task(self, alert_id: int):
    """
    Celery task to send job alert emails to users.
    """
    try:
        alert = JobAlert.objects.get(id=alert_id, is_active=True)

        # Get matching jobs that haven't been sent in this alert
        matching_service = JobMatchService()

        # Build query based on alert criteria
        query = Q(is_active=True)

        if alert.title:
            query &= Q(title__icontains=alert.title)

        if alert.location:
            query &= Q(location__icontains=alert.location)

        if alert.job_type:
            query &= Q(job_type=alert.job_type)

        if alert.salary_min:
            query &= Q(salary_min__gte=alert.salary_min)

        if alert.salary_max:
            query &= Q(salary_max__lte=alert.salary_max)

        # Get jobs created since last alert
        since_date = alert.last_sent_at or (timezone.now() - timedelta(days=1))
        query &= Q(created_at__gte=since_date)

        matching_jobs = Job.objects.filter(query).order_by("-created_at")[:50]

        if not matching_jobs.exists():
            logger.info(f"No new jobs found for alert {alert_id}")
            return

        # Send email
        email_service = EmailService()
        success = email_service.send_job_alert_email(
            user=alert.user, jobs=list(matching_jobs), alert=alert
        )

        if success:
            alert.last_sent_at = timezone.now()
            alert.save()
            logger.info(f"Job alert email sent successfully for alert {alert_id}")
        else:
            logger.error(f"Failed to send job alert email for alert {alert_id}")

    except JobAlert.DoesNotExist:
        logger.error(f"JobAlert {alert_id} not found")
    except Exception as e:
        logger.error(f"Error sending job alert email for alert {alert_id}: {e}")
        self.retry(countdown=60 * (self.request.retries + 1))


@shared_task(bind=True, max_retries=3)
def send_application_status_update_task(self, application_id: int, old_status: str):
    """
    Celery task to send application status update emails.
    """
    try:
        application = Application.objects.select_related("user", "job").get(
            id=application_id
        )

        email_service = EmailService()
        success = email_service.send_application_status_update(
            application=application, old_status=old_status
        )

        if success:
            logger.info(
                f"Application status update email sent for application {application_id}"
            )
        else:
            logger.error(
                f"Failed to send application status update email for application {application_id}"
            )

    except Application.DoesNotExist:
        logger.error(f"Application {application_id} not found")
    except Exception as e:
        logger.error(
            f"Error sending application status update email for application {application_id}: {e}"
        )
        self.retry(countdown=60 * (self.request.retries + 1))


@shared_task(bind=True, max_retries=3)
def send_welcome_email_task(self, user_id: int):
    """
    Celery task to send welcome email to new users.
    """
    try:
        user = User.objects.get(id=user_id)

        email_service = EmailService()
        success = email_service.send_welcome_email(user=user)

        if success:
            logger.info(f"Welcome email sent successfully to user {user_id}")
        else:
            logger.error(f"Failed to send welcome email to user {user_id}")

    except User.DoesNotExist:
        logger.error(f"User {user_id} not found")
    except Exception as e:
        logger.error(f"Error sending welcome email to user {user_id}: {e}")
        self.retry(countdown=60 * (self.request.retries + 1))


@shared_task(bind=True, max_retries=3)
def send_job_recommendations_task(self, user_id: int):
    """
    Celery task to send job recommendation emails to users.
    """
    try:
        user = User.objects.get(id=user_id)

        # Get user profile for recommendations
        try:
            user_profile = user.userprofile
        except:
            logger.info(f"No user profile found for user {user_id}")
            return

        # Get job recommendations for user
        matching_service = JobMatchService()
        recommendations = matching_service.generate_recommendations_for_user(
            user_profile.id, num_recommendations=10
        )

        if not recommendations:
            logger.info(f"No job recommendations found for user {user_id}")
            return

        email_service = EmailService()
        success = email_service.send_job_recommendation_email(
            user=user, recommended_jobs=recommendations
        )

        if success:
            logger.info(
                f"Job recommendations email sent successfully to user {user_id}"
            )
        else:
            logger.error(f"Failed to send job recommendations email to user {user_id}")

    except User.DoesNotExist:
        logger.error(f"User {user_id} not found")
    except Exception as e:
        logger.error(f"Error sending job recommendations email to user {user_id}: {e}")
        self.retry(countdown=60 * (self.request.retries + 1))


@shared_task(bind=True, max_retries=3)
def send_follow_up_reminder_task(self, application_id: int):
    """
    Celery task to send follow-up reminder emails for applications.
    """
    try:
        application = Application.objects.select_related("user", "job").get(
            id=application_id
        )

        # Only send follow-up if application is still in pending/review status
        if application.status not in ["submitted", "under_review"]:
            logger.info(
                f"Application {application_id} status is {application.status}, skipping follow-up"
            )
            return

        email_service = EmailService()
        success = email_service.send_application_follow_up_reminder(
            application=application
        )

        if success:
            logger.info(
                f"Follow-up reminder email sent for application {application_id}"
            )
        else:
            logger.error(
                f"Failed to send follow-up reminder email for application {application_id}"
            )

    except Application.DoesNotExist:
        logger.error(f"Application {application_id} not found")
    except Exception as e:
        logger.error(
            f"Error sending follow-up reminder email for application {application_id}: {e}"
        )
        self.retry(countdown=60 * (self.request.retries + 1))


# =======================
# MISSING CRITICAL NOTIFICATION TASKS
# =======================


@shared_task(bind=True, max_retries=3)
def process_daily_job_alerts(self):
    """
    Process all daily job alerts for active users.
    """
    try:
        # Get all active daily job alerts
        daily_alerts = JobAlert.objects.filter(
            is_active=True, frequency="daily"
        ).select_related("user")

        processed_count = 0
        for alert in daily_alerts:
            # Check if alert was already sent today
            today = timezone.now().date()
            if alert.last_sent_at and alert.last_sent_at.date() == today:
                continue

            # Queue individual alert processing
            send_job_alert_email_task.delay(alert.id)
            processed_count += 1

        logger.info(f"Queued {processed_count} daily job alerts for processing")
        return {"status": "success", "processed_count": processed_count}

    except Exception as exc:
        logger.error(f"Error processing daily job alerts: {exc}")
        raise self.retry(exc=exc, countdown=300)


@shared_task(bind=True, max_retries=3)
def process_weekly_job_alerts(self):
    """
    Process all weekly job alerts for active users.
    """
    try:
        # Get all active weekly job alerts
        weekly_alerts = JobAlert.objects.filter(
            is_active=True, frequency="weekly"
        ).select_related("user")

        processed_count = 0
        for alert in weekly_alerts:
            # Check if alert was already sent this week
            week_ago = timezone.now() - timedelta(days=7)
            if alert.last_sent_at and alert.last_sent_at >= week_ago:
                continue

            # Queue individual alert processing
            send_job_alert_email_task.delay(alert.id)
            processed_count += 1

        logger.info(f"Queued {processed_count} weekly job alerts for processing")
        return {"status": "success", "processed_count": processed_count}

    except Exception as exc:
        logger.error(f"Error processing weekly job alerts: {exc}")
        raise self.retry(exc=exc, countdown=300)


@shared_task(bind=True, max_retries=3)
def send_weekly_job_recommendations(self):
    """
    Send weekly job recommendations to all active users.
    """
    try:
        # Get users who haven't received recommendations recently
        week_ago = timezone.now() - timedelta(days=7)

        users_for_recommendations = User.objects.filter(
            is_active=True, profile__isnull=False
        ).exclude(
            # Exclude users who got recommendations recently
            id__in=User.objects.filter(
                email_log__template_name="job_recommendations",
                email_log__sent_at__gte=week_ago,
            ).values("id")
        )[
            :100
        ]  # Limit to avoid overwhelming the system

        processed_count = 0
        for user in users_for_recommendations:
            send_job_recommendations_task.delay(user.id)
            processed_count += 1

        logger.info(f"Queued {processed_count} weekly job recommendation emails")
        return {"status": "success", "processed_count": processed_count}

    except Exception as exc:
        logger.error(f"Error sending weekly job recommendations: {exc}")
        raise self.retry(exc=exc, countdown=300)


@shared_task(bind=True, max_retries=3)
def send_application_follow_up_reminders(self):
    """
    Send follow-up reminders for applications that need attention.
    """
    try:
        # Find applications that need follow-up (7 days after submission)
        week_ago = timezone.now() - timedelta(days=7)

        applications_needing_followup = Application.objects.filter(
            status__in=["submitted", "under_review"],
            created_at__lte=week_ago,
            follow_up_sent_at__isnull=True,
        ).select_related("user", "job")[
            :50
        ]  # Limit to avoid spam

        processed_count = 0
        for application in applications_needing_followup:
            send_follow_up_reminder_task.delay(application.id)
            # Mark that follow-up was queued
            application.follow_up_sent_at = timezone.now()
            application.save(update_fields=["follow_up_sent_at"])
            processed_count += 1

        logger.info(f"Queued {processed_count} application follow-up reminders")
        return {"status": "success", "processed_count": processed_count}

    except Exception as exc:
        logger.error(f"Error sending application follow-up reminders: {exc}")
        raise self.retry(exc=exc, countdown=300)


@shared_task(bind=True, max_retries=3)
def cleanup_old_notifications(self):
    """
    Clean up old notifications to keep the database manageable.
    """
    try:
        from apps.notifications.models import Notification

        # Delete notifications older than 30 days
        cutoff_date = timezone.now() - timedelta(days=30)

        deleted_count, _ = Notification.objects.filter(
            created_at__lt=cutoff_date
        ).delete()

        logger.info(f"Cleaned up {deleted_count} old notifications")
        return {"status": "success", "deleted_count": deleted_count}

    except Exception as exc:
        logger.error(f"Error cleaning up old notifications: {exc}")
        raise self.retry(exc=exc, countdown=300)


@shared_task(bind=True, max_retries=3)
def send_system_digest_email(self, admin_email=None):
    """
    Send daily system digest to administrators.
    """
    try:
        from django.conf import settings
        from django.core.mail import mail_admins

        # Gather system statistics
        stats = {
            "active_users": User.objects.filter(is_active=True).count(),
            "total_jobs": Job.objects.filter(is_active=True).count(),
            "applications_today": Application.objects.filter(
                created_at__gte=timezone.now().date()
            ).count(),
            "job_alerts_active": JobAlert.objects.filter(is_active=True).count(),
            "notifications_sent_today": 0,  # Would need email tracking model
        }

        # Create digest message
        message = f"""
Daily Jobraker System Digest - {timezone.now().date()}

System Statistics:
- Active Users: {stats['active_users']}
- Active Jobs: {stats['total_jobs']}
- Applications Today: {stats['applications_today']}
- Active Job Alerts: {stats['job_alerts_active']}
- Notifications Sent: {stats['notifications_sent_today']}

System Status: Operational
        """

        # Send to admin email or site admins
        if admin_email:
            from django.core.mail import send_mail

            send_mail(
                "Jobraker Daily Digest",
                message,
                settings.DEFAULT_FROM_EMAIL,
                [admin_email],
            )
        else:
            mail_admins("Jobraker Daily Digest", message)

        logger.info("System digest email sent successfully")
        return {"status": "success", "stats": stats}

    except Exception as exc:
        logger.error(f"Error sending system digest email: {exc}")
        raise self.retry(exc=exc, countdown=300)
