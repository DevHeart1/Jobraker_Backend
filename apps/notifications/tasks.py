"""
Enhanced Celery tasks for email automation and notifications.
"""

import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any
from celery import shared_task
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.db.models import Q
from apps.jobs.models import Job, Application, JobAlert
from apps.notifications.email_service import EmailService
from apps.jobs.services import JobMatchService

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
        
        matching_jobs = Job.objects.filter(query).order_by('-created_at')[:50]
        
        if not matching_jobs.exists():
            logger.info(f"No new jobs found for alert {alert_id}")
            return
        
        # Send email
        email_service = EmailService()
        success = email_service.send_job_alert_email(
            user=alert.user,
            jobs=list(matching_jobs),
            alert=alert
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
        application = Application.objects.select_related('user', 'job').get(id=application_id)
        
        email_service = EmailService()
        success = email_service.send_application_status_update(
            application=application,
            old_status=old_status
        )
        
        if success:
            logger.info(f"Application status update email sent for application {application_id}")
        else:
            logger.error(f"Failed to send application status update email for application {application_id}")
            
    except Application.DoesNotExist:
        logger.error(f"Application {application_id} not found")
    except Exception as e:
        logger.error(f"Error sending application status update email for application {application_id}: {e}")
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
        
        # Get job recommendations for user
        matching_service = JobMatchService()
        recommendations = matching_service.get_job_recommendations(user_id, limit=10)
        
        if not recommendations:
            logger.info(f"No job recommendations found for user {user_id}")
            return
        
        email_service = EmailService()
        success = email_service.send_job_recommendation_email(
            user=user,
            recommended_jobs=recommendations
        )
        
        if success:
            logger.info(f"Job recommendations email sent successfully to user {user_id}")
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
        application = Application.objects.select_related('user', 'job').get(id=application_id)
        
        # Only send follow-up if application is still in pending/review status
        if application.status not in ['submitted', 'under_review']:
            logger.info(f"Application {application_id} status is {application.status}, skipping follow-up")
            return
        
        email_service = EmailService()
        success = email_service.send_application_follow_up_reminder(application=application)
        
        if success:
            logger.info(f"Follow-up reminder email sent for application {application_id}")
        else:
            logger.error(f"Failed to send follow-up reminder email for application {application_id}")
            
    except Application.DoesNotExist:
        logger.error(f"Application {application_id} not found")
    except Exception as e:
        logger.error(f"Error sending follow-up reminder email for application {application_id}: {e}")
        self.retry(countdown=60 * (self.request.retries + 1))


@shared_task
def process_daily_job_alerts():
    """
    Celery task to process all daily job alerts.
    """
    daily_alerts = JobAlert.objects.filter(
        is_active=True,
        frequency='daily'
    )
    
    count = 0
    for alert in daily_alerts:
        send_job_alert_email_task.delay(alert.id)
        count += 1
    
    logger.info(f"Queued {count} daily job alerts for processing")


@shared_task
def process_weekly_job_alerts():
    """
    Celery task to process all weekly job alerts.
    """
    weekly_alerts = JobAlert.objects.filter(
        is_active=True,
        frequency='weekly'
    )
    
    count = 0
    for alert in weekly_alerts:
        send_job_alert_email_task.delay(alert.id)
        count += 1
    
    logger.info(f"Queued {count} weekly job alerts for processing")


@shared_task
def send_weekly_job_recommendations():
    """
    Celery task to send weekly job recommendations to all active users.
    """
    # Get users who have been active in the last 30 days
    active_users = User.objects.filter(
        is_active=True,
        last_login__gte=timezone.now() - timedelta(days=30)
    )
    
    count = 0
    for user in active_users:
        send_job_recommendations_task.delay(user.id)
        count += 1
    
    logger.info(f"Queued job recommendations for {count} active users")


@shared_task
def send_application_follow_up_reminders():
    """
    Celery task to send follow-up reminders for applications after 7 days.
    """
    # Get applications that are 7 days old and still pending
    seven_days_ago = timezone.now() - timedelta(days=7)
    
    applications = Application.objects.filter(
        applied_at__date=seven_days_ago.date(),
        status__in=['submitted', 'under_review']
    )
    
    count = 0
    for application in applications:
        send_follow_up_reminder_task.delay(application.id)
        count += 1
    
    logger.info(f"Queued {count} follow-up reminder emails")


@shared_task(bind=True, max_retries=3)
def send_bulk_notification_task(
    self,
    user_ids: List[int],
    subject: str,
    template_name: str,
    context: Dict[str, Any]
):
    """
    Celery task to send bulk notifications to multiple users.
    """
    try:
        users = User.objects.filter(id__in=user_ids, is_active=True)
        
        email_service = EmailService()
        results = email_service.send_bulk_notification(
            users=list(users),
            subject=subject,
            template_name=template_name,
            context=context
        )
        
        logger.info(f"Bulk notification sent: {results}")
        return results
        
    except Exception as e:
        logger.error(f"Error sending bulk notification: {e}")
        self.retry(countdown=60 * (self.request.retries + 1))


@shared_task
def cleanup_old_notifications():
    """
    Celery task to cleanup old notification records.
    """
    # This would cleanup old notification records if we had a notification model
    # For now, it's a placeholder for future implementation
    logger.info("Notification cleanup task executed")
def send_notification_email(self, notification_id):
    """
    Send an email notification to a user.
    
    Args:
        notification_id: ID of the notification to send via email
    """
    try:
        from apps.notifications.models import Notification
        from django.core.mail import send_mail
        from django.conf import settings
        
        notification = Notification.objects.get(id=notification_id)
        
        if not notification.user.email:
            logger.warning(f"User {notification.user.id} has no email address for notification {notification_id}")
            return {'status': 'no_email', 'notification_id': notification_id}
        
        # Send email
        subject = f"Jobraker: {notification.title}"
        message = notification.message
        
        send_mail(
            subject,
            message,
            settings.DEFAULT_FROM_EMAIL,
            [notification.user.email],
            fail_silently=False,
        )
        
        # Mark as email sent
        notification.email_sent = True
        notification.email_sent_at = timezone.now()
        notification.save(update_fields=['email_sent', 'email_sent_at'])
        
        logger.info(f"Email sent for notification {notification_id} to {notification.user.email}")
        return {'status': 'success', 'notification_id': notification_id}
        
    except Notification.DoesNotExist:
        logger.error(f"Notification {notification_id} not found")
        return {'status': 'not_found', 'notification_id': notification_id}
        
    except Exception as exc:
        logger.error(f"Error sending email for notification {notification_id}: {exc}")
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))


@shared_task(bind=True, max_retries=3)
def batch_process_pending_notifications(self, limit=100):
    """
    Process pending notifications that need to be sent via email.
    
    Args:
        limit: Maximum number of notifications to process in this batch
    """
    try:
        from apps.notifications.models import Notification
        
        # Find pending notifications that haven't been emailed yet
        pending_notifications = Notification.objects.filter(
            email_sent=False,
            user__email__isnull=False,
            user__is_active=True
        ).select_related('user')[:limit]
        
        queued_count = 0
        for notification in pending_notifications:
            # Queue individual email task
            send_notification_email.delay(notification.id)
            queued_count += 1
        
        logger.info(f"Queued {queued_count} notification emails for sending")
        return {'status': 'success', 'queued_count': queued_count}
        
    except Exception as exc:
        logger.error(f"Error in batch notification processing: {exc}")
        return {'status': 'error', 'error': str(exc)}
