import logging

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

# Ensure this task path is correct based on where you defined it.
# If tasks.py is in apps.integrations, this import is fine.
from apps.integrations.tasks import process_knowledge_article_for_rag_task

from .models import KnowledgeArticle

logger = logging.getLogger(__name__)


@receiver(post_save, sender=KnowledgeArticle)
def knowledge_article_post_save(
    sender, instance: KnowledgeArticle, created: bool, **kwargs
):
    """
    Signal handler for when a KnowledgeArticle instance is saved.
    If the article is active, it triggers a Celery task to process it for RAG.
    If it's made inactive, it also triggers the task to potentially remove it from RAG.
    """
    logger.info(
        f"KnowledgeArticle post_save signal triggered for article ID: {instance.id}, active: {instance.is_active}"
    )
    # The task itself handles the logic for active (embed & add) vs inactive (delete from RAG)
    process_knowledge_article_for_rag_task.delay(instance.id)
    logger.info(f"Queued RAG processing task for KnowledgeArticle ID: {instance.id}")


@receiver(post_delete, sender=KnowledgeArticle)
def knowledge_article_post_delete(sender, instance: KnowledgeArticle, **kwargs):
    """
    Signal handler for when a KnowledgeArticle instance is deleted.
    Triggers a Celery task to remove it from the RAG vector store.
    (Note: The task process_knowledge_article_for_rag_task currently handles deletion if is_active=False.
     A dedicated delete task might be cleaner, or ensure the current task can handle
     being called for an already deleted PK if is_active was True before deletion.)

    A more direct approach for deletion:
    Instantiate VectorDBService and call delete_documents directly, or queue a specific delete task.
    For simplicity, we can rely on the fact that if an article is deleted, it can't be "active",
    so if process_knowledge_article_for_rag_task is called with a non-existent ID, it will fail gracefully.
    A better way is a dedicated delete task or direct service call if the instance is available.

    Let's assume for now that making it inactive before deletion is the workflow,
    and the save signal handles the deletion from RAG. If direct deletion needs RAG cleanup,
    a specific task or direct service call here would be better.

    Given the current task logic (delete if not active):
    If an article is deleted, its 'is_active' status at the point of deletion might be true.
    The task `process_knowledge_article_for_rag_task` tries to fetch the article by ID.
    If it's deleted, `KnowledgeArticle.objects.get(id=article_id)` will raise DoesNotExist.
    The task handles this and logs "KnowledgeArticle not found". This is acceptable.
    No separate action needed for post_delete if making it inactive first is the standard workflow.
    However, if a direct delete of an active article should clean RAG, we'd add:
    """
    logger.info(
        f"KnowledgeArticle post_delete signal triggered for article ID: {instance.id}"
    )
    # The updated task now handles DoesNotExist gracefully by deleting from the vector store.
    # This ensures that even if an active article is deleted directly, it gets cleaned up from RAG.
    process_knowledge_article_for_rag_task.delay(instance.id)
    logger.info(
        f"Queued RAG cleanup task for deleted KnowledgeArticle ID: {instance.id}"
    )
