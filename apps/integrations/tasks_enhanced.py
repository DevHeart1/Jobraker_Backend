"""
Enhanced job processing tasks with proper vector storage.
"""

import logging

from celery import shared_task
from django.utils import timezone

from apps.common.vector_storage import VectorStorageService
from apps.integrations.services.openai_service import EmbeddingService

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def process_job_for_embeddings(self, job_id: str):
    """
    Enhanced task to process job for embeddings and store in vector database.

    Args:
        job_id: Job ID to process
    """
    try:
        from apps.jobs.models import Job

        job = Job.objects.get(id=job_id)

        # Create comprehensive text for embedding
        text_parts = [
            job.title or "",
            job.company or "",
            job.location or "",
            job.description or "",
            job.requirements or "",
            " ".join(job.skills) if job.skills else "",
        ]

        # Combine all text parts
        combined_text = ". ".join(filter(None, text_parts))

        if not combined_text.strip():
            logger.warning(f"No text content to embed for job {job_id}")
            return

        # Generate embedding
        embedding_service = EmbeddingService()
        embedding = embedding_service.generate_embedding(combined_text)

        if not embedding:
            logger.error(f"Failed to generate embedding for job {job_id}")
            return

        # Store in vector database
        vector_service = VectorStorageService()
        document = {
            "text_content": combined_text,
            "embedding": embedding,
            "source_type": "job_listing",
            "source_id": str(job.id),
            "metadata": {
                "title": job.title,
                "company": job.company,
                "location": job.location,
                "job_type": job.job_type,
                "experience_level": job.experience_level,
                "salary_min": job.salary_min,
                "salary_max": job.salary_max,
                "is_remote": job.is_remote,
                "external_source": job.external_source,
                "posted_date": job.posted_date.isoformat() if job.posted_date else None,
                "skills": job.skills,
            },
        }

        result = vector_service._store_single_document(document, update_existing=True)

        # Update job embedding field and mark as processed
        job.combined_embedding = embedding
        job.processed_for_matching = True
        job.save(
            update_fields=["combined_embedding", "processed_for_matching", "updated_at"]
        )

        logger.info(f"Successfully processed job {job_id} for embeddings: {result}")

    except Exception as e:
        logger.error(
            f"Error processing job {job_id} for embeddings: {e}", exc_info=True
        )

        # Retry with exponential backoff
        countdown = 2**self.request.retries
        raise self.retry(exc=e, countdown=countdown, max_retries=3)


@shared_task(bind=True, max_retries=3)
def batch_process_jobs_for_embeddings(self, job_ids: list, batch_size: int = 10):
    """
    Process multiple jobs for embeddings in batches.

    Args:
        job_ids: List of job IDs to process
        batch_size: Number of jobs to process in each batch
    """
    try:
        from apps.jobs.models import Job

        # Process jobs in batches
        for i in range(0, len(job_ids), batch_size):
            batch_ids = job_ids[i : i + batch_size]

            # Get jobs for this batch
            jobs = Job.objects.filter(id__in=batch_ids)

            documents = []
            jobs_to_update = []

            embedding_service = EmbeddingService()

            for job in jobs:
                # Create text for embedding
                text_parts = [
                    job.title or "",
                    job.company or "",
                    job.location or "",
                    job.description or "",
                    job.requirements or "",
                    " ".join(job.skills) if job.skills else "",
                ]

                combined_text = ". ".join(filter(None, text_parts))

                if not combined_text.strip():
                    logger.warning(f"No text content for job {job.id}")
                    continue

                # Generate embedding
                embedding = embedding_service.generate_embedding(combined_text)

                if embedding:
                    documents.append(
                        {
                            "text_content": combined_text,
                            "embedding": embedding,
                            "source_type": "job_listing",
                            "source_id": str(job.id),
                            "metadata": {
                                "title": job.title,
                                "company": job.company,
                                "location": job.location,
                                "job_type": job.job_type,
                                "experience_level": job.experience_level,
                                "salary_min": job.salary_min,
                                "salary_max": job.salary_max,
                                "is_remote": job.is_remote,
                                "external_source": job.external_source,
                                "posted_date": (
                                    job.posted_date.isoformat()
                                    if job.posted_date
                                    else None
                                ),
                                "skills": job.skills,
                            },
                        }
                    )

                    # Update job object
                    job.combined_embedding = embedding
                    job.processed_for_matching = True
                    jobs_to_update.append(job)

            # Batch store in vector database
            if documents:
                vector_service = VectorStorageService()
                stats = vector_service.store_embeddings_batch(documents)
                logger.info(f"Batch {i//batch_size + 1} vector storage stats: {stats}")

            # Batch update jobs
            if jobs_to_update:
                Job.objects.bulk_update(
                    jobs_to_update,
                    ["combined_embedding", "processed_for_matching", "updated_at"],
                    batch_size=batch_size,
                )

                logger.info(f"Updated {len(jobs_to_update)} jobs as processed")

        logger.info(f"Completed batch processing of {len(job_ids)} jobs")

    except Exception as e:
        logger.error(f"Error in batch processing jobs: {e}", exc_info=True)
        raise self.retry(exc=e, countdown=60, max_retries=3)


@shared_task
def cleanup_old_embeddings():
    """
    Clean up old embeddings to manage storage.
    """
    try:
        vector_service = VectorStorageService()

        # Clean up job embeddings older than 90 days
        deleted_count = vector_service.cleanup_old_vectors(
            days_old=90, source_types=["job_listing"]
        )

        logger.info(f"Cleaned up {deleted_count} old job embeddings")

        # Get storage statistics
        stats = vector_service.get_storage_stats()
        logger.info(f"Vector storage stats: {stats}")

    except Exception as e:
        logger.error(f"Error in cleanup task: {e}", exc_info=True)


@shared_task
def reindex_vector_database():
    """
    Rebuild vector database indexes for optimal performance.
    """
    try:
        vector_service = VectorStorageService()

        success = vector_service.reindex_vectors()

        if success:
            logger.info("Vector database reindexing completed successfully")
        else:
            logger.warning("Vector database reindexing failed or not available")

    except Exception as e:
        logger.error(f"Error in reindex task: {e}", exc_info=True)


@shared_task
def sync_unprocessed_jobs():
    """
    Find and process jobs that haven't been processed for embeddings.
    """
    try:
        from apps.jobs.models import Job

        # Find jobs that haven't been processed
        unprocessed_jobs = Job.objects.filter(
            processed_for_matching=False, status="active"
        ).values_list("id", flat=True)

        if not unprocessed_jobs:
            logger.info("No unprocessed jobs found")
            return

        # Convert to list of strings
        job_ids = [str(job_id) for job_id in unprocessed_jobs]

        # Process in batches
        batch_process_jobs_for_embeddings.delay(job_ids, batch_size=20)

        logger.info(f"Queued {len(job_ids)} unprocessed jobs for embedding generation")

    except Exception as e:
        logger.error(f"Error syncing unprocessed jobs: {e}", exc_info=True)
