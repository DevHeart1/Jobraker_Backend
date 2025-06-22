from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from .models import KnowledgeArticle
# Ensure this task path is correct based on where you defined it.
# If tasks.py is in apps.integrations, this import is fine.
from apps.integrations.tasks import process_knowledge_article_for_rag_task
import logging

logger = logging.getLogger(__name__)

@receiver(post_save, sender=KnowledgeArticle)
def knowledge_article_post_save(sender, instance: KnowledgeArticle, created: bool, **kwargs):
    """
    Signal handler for when a KnowledgeArticle instance is saved.
    If the article is active, it triggers a Celery task to process it for RAG.
    If it's made inactive, it also triggers the task to potentially remove it from RAG.
    """
    logger.info(f"KnowledgeArticle post_save signal triggered for article ID: {instance.id}, active: {instance.is_active}")
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
    # from apps.common.services import VectorDBService
    # logger.info(f"KnowledgeArticle post_delete signal triggered for article ID: {instance.id}. Type: {instance.source_type}")
    # vector_db_service = VectorDBService()
    # success = vector_db_service.delete_documents(source_type=instance.source_type, source_id=str(instance.id))
    # if success:
    #     logger.info(f"Successfully deleted documents from RAG for deleted KnowledgeArticle ID: {instance.id}")
    # else:
    #     logger.error(f"Failed to delete documents from RAG for deleted KnowledgeArticle ID: {instance.id}")
    # For now, relying on the save signal and making articles inactive before deletion.
    # If an active article is hard-deleted, its RAG entry might remain if not handled explicitly.
    # The current `process_knowledge_article_for_rag_task` will attempt to fetch it, fail, and do nothing to RAG.
    # This is a potential inconsistency.
    # A better post_delete would be to directly call vector_db_service.delete_documents.

    logger.info(f"KnowledgeArticle (ID: {instance.id}, Title: {instance.title}) was deleted. "
                f"If it was active, its RAG entry should be manually verified or a dedicated "
                f"RAG cleanup task for deletions should be implemented if not handled by setting is_active=False first.")
    # For a robust system, let's trigger a delete from RAG store
    try:
        from apps.common.services import VectorDBService
        vector_db_service = VectorDBService()
        # We use instance.source_type and instance.id as they are available from the instance being deleted
        deleted_from_rag = vector_db_service.delete_documents(source_type=instance.source_type, source_id=str(instance.id))
        if deleted_from_rag:
            logger.info(f"Successfully triggered deletion from RAG for KnowledgeArticle ID: {instance.id}")
        else:
            logger.warning(f"Deletion from RAG for KnowledgeArticle ID: {instance.id} reported failure or no action by service.")
    except Exception as e:
        logger.error(f"Error trying to delete KnowledgeArticle ID: {instance.id} from RAG on post_delete: {e}")
