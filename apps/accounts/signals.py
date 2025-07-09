"""
Signals for the accounts app.
"""
import logging
from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import UserProfile
from .tasks import generate_user_profile_embedding_task

logger = logging.getLogger(__name__)

@receiver(post_save, sender=UserProfile)
def queue_user_profile_embedding(sender, instance, created, **kwargs):
    """
    Queue a Celery task to generate user profile embedding on save.
    """
    # We can add more complex logic here to avoid re-generating embeddings on every minor change.
    # For now, we generate it on creation and every update.
    logger.info(f"UserProfile signal triggered for user {instance.user.id}. Queueing embedding generation.")
    generate_user_profile_embedding_task.delay(str(instance.id))
