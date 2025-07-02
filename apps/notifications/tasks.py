"""
Celery tasks for notifications app.
"""

from celery import shared_task
import logging
from django.utils import timezone
from datetime import timedelta

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=1)
def cleanup_old_notifications(self, days_old=30):
    """
    Clean up old notifications that are older than the specified number of days.
    
    Args:
        days_old: Number of days after which notifications should be deleted
    """
    try:
        from apps.notifications.models import Notification
        
        cutoff_date = timezone.now() - timedelta(days=days_old)
        
        # Find old notifications
        old_notifications = Notification.objects.filter(
            created_at__lt=cutoff_date
        )
        
        count = old_notifications.count()
        
        if count > 0:
            # Delete old notifications
            deleted_count, _ = old_notifications.delete()
            logger.info(f"Cleaned up {deleted_count} old notifications (older than {days_old} days)")
            return {'status': 'success', 'deleted_count': deleted_count}
        else:
            logger.info(f"No old notifications found to clean up (older than {days_old} days)")
            return {'status': 'no_cleanup_needed', 'deleted_count': 0}
            
    except Exception as exc:
        logger.error(f"Error cleaning up old notifications: {exc}")
        # Don't retry notification cleanup failures aggressively
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc, countdown=300)  # Retry after 5 minutes
        return {'status': 'error', 'error': str(exc)}


@shared_task(bind=True, max_retries=3)
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
