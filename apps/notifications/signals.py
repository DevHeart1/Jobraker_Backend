"""
Django signals for automatic email notifications.
"""

import logging
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model
from apps.jobs.models import Application
from apps.notifications.tasks import (
    send_welcome_email_task,
    send_application_status_update_task
)

logger = logging.getLogger(__name__)
User = get_user_model()


@receiver(post_save, sender=User)
def send_welcome_email_on_user_creation(sender, instance, created, **kwargs):
    """
    Send welcome email when a new user is created.
    """
    if created:
        try:
            # Send welcome email asynchronously
            send_welcome_email_task.delay(instance.id)
            logger.info(f"Welcome email queued for user {instance.id}")
        except Exception as e:
            logger.error(f"Failed to queue welcome email for user {instance.id}: {e}")


@receiver(pre_save, sender=Application)
def track_application_status_changes(sender, instance, **kwargs):
    """
    Track application status changes to send appropriate notifications.
    """
    if instance.pk:  # Only for updates, not creation
        try:
            # Get the old status
            old_application = Application.objects.get(pk=instance.pk)
            old_status = old_application.status
            
            # Store old status for the post_save signal
            instance._old_status = old_status
        except Application.DoesNotExist:
            instance._old_status = None


@receiver(post_save, sender=Application)
def send_application_status_update_email(sender, instance, created, **kwargs):
    """
    Send application status update email when status changes.
    """
    if not created and hasattr(instance, '_old_status'):
        old_status = instance._old_status
        
        # Only send email if status actually changed
        if old_status and old_status != instance.status:
            try:
                # Send status update email asynchronously
                send_application_status_update_task.delay(instance.id, old_status)
                logger.info(f"Application status update email queued for application {instance.id}")
            except Exception as e:
                logger.error(f"Failed to queue application status update email for application {instance.id}: {e}")
