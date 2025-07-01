from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django_elasticsearch_dsl.registries import registry
# It's better to avoid importing the model directly at the module level in signals
# if the model itself might import signals, to prevent circular dependencies.
# Instead, use sender=AppName.ModelName string or get model in the handler.
# However, for type checking or direct use if safe, importing is fine.
from .models import Job

@receiver(post_save, sender=Job, dispatch_uid="update_job_document_on_save")
def update_job_document_on_save(sender, instance, created, **kwargs):
    """
    Update or create the Elasticsearch document when a Job instance is saved.
    """
    # Using registry.update(instance) is generally preferred as it handles
    # both creation and update of the document.
    # It internally checks if the document exists and then updates or creates it.
    try:
        registry.update(instance)
        # Optional: For immediate visibility in ES, though often not needed
        # registry.update_related(instance) # If there are related models to update in ES
    except Exception as e:
        # Log the error, but don't let signal handling break the main save operation.
        # In a production system, you might queue this for retry.
        print(f"Error updating Elasticsearch for Job {instance.pk} on save: {e}")


@receiver(post_delete, sender=Job, dispatch_uid="delete_job_document_on_delete")
def delete_job_document_on_delete(sender, instance, **kwargs):
    """
    Delete the Elasticsearch document when a Job instance is deleted.
    """
    try:
        registry.delete(instance, raise_on_error=False) # raise_on_error=False will not fail if doc not found
    except Exception as e:
        print(f"Error deleting Elasticsearch document for Job {instance.pk} on delete: {e}")

# Note: If using ELASTICSEARCH_DSL_AUTOSYNC = True in settings,
# django-elasticsearch-dsl attempts to handle these signals automatically.
# However, explicit signal handlers provide more control, especially for error handling
# or more complex logic (e.g., conditional indexing).
# The current plan assumes manual signal handling (ELASTICSEARCH_DSL_AUTOSYNC = False, which is default).
