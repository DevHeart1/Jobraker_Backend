"""
Celery tasks for integration services.
"""

from celery import shared_task
from typing import Dict, Any, Optional, List
from django.utils import timezone
from django.contrib.auth import get_user_model
from datetime import timedelta
import logging
import time

logger = logging.getLogger(__name__)
User = get_user_model()

# Import centralized metrics
from apps.common.metrics import (
    OPENAI_API_CALLS_TOTAL,
    OPENAI_API_CALL_DURATION_SECONDS,
    OPENAI_MODERATION_CHECKS_TOTAL,
    OPENAI_MODERATION_FLAGGED_TOTAL,
    ADZUNA_JOBS_PROCESSED_TOTAL,
    SKYVERN_APPLICATION_SUBMISSIONS_TOTAL
)


@shared_task(bind=True, max_retries=3)
def fetch_adzuna_jobs(self, categories=None, max_days_old=1):
    """
    Fetch jobs from Adzuna API and automatically generate embeddings.
    
    Args:
        categories: List of job categories to search (optional)
        max_days_old: How many days back to search
    """
    try:
        from apps.integrations.services.adzuna import AdzunaJobProcessor
        
        processor = AdzunaJobProcessor()
        
        if categories:
            # Fetch specific categories
            total_stats = {
                'total_found': 0,
                'processed': 0,
                'created': 0,
                'updated': 0,
                'errors': 0,
                'embeddings_queued': 0,
            }
            
            for category in categories:
                stats = processor.fetch_and_process_jobs(
                    what=category,
                    max_pages=2,
                    max_days_old=max_days_old,
                )
                
                for key in total_stats:
                    if key in stats:
                        total_stats[key] += stats[key]
                
                # Queue embedding generation for new jobs
                if 'new_job_ids' in stats:
                    for job_id in stats['new_job_ids']:
                        generate_job_embeddings_and_ingest_for_rag.delay(str(job_id))
                        total_stats['embeddings_queued'] += 1
            
            logger.info(f"Adzuna fetch completed for categories {categories}: {total_stats}")
            return total_stats
        else:
            # Sync recent jobs across multiple categories
            stats = processor.sync_recent_jobs(days=max_days_old)
            
            # Queue embedding generation for new jobs
            if 'new_job_ids' in stats:
                stats['embeddings_queued'] = 0
                for job_id in stats['new_job_ids']:
                    generate_job_embeddings_and_ingest_for_rag.delay(str(job_id))
                    stats['embeddings_queued'] += 1
            
            logger.info(f"Adzuna sync completed: {stats}")
            return stats
            
    except Exception as exc:
        logger.error(f"Error fetching Adzuna jobs: {exc}")
        # Retry with exponential backoff
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))


@shared_task(bind=True, max_retries=3)
def generate_job_embeddings_and_ingest_for_rag(self, job_id: str):
    """
    Generates AI embeddings for a job posting, saves them to the Job model,
    and then ingests the job's content and combined_embedding into the RAG vector store.
    
    Args:
        job_id: UUID string of the job to process.
    """
    try:
        from apps.jobs.models import Job
        from apps.integrations.services.openai import EmbeddingService # Consolidated
        from apps.common.services import VectorDBService
        
        job = Job.objects.get(id=job_id)
        embedding_service = EmbeddingService()
        vector_db_service = VectorDBService()
        model_name = embedding_service.embedding_model # Get model name for labels

        # --- 1. Generate and Save Embeddings to Job Model ---
        job_model_embedding_status = 'error'
        job_embeddings_dict = None
        try:
            emb_start_time = time.monotonic()
            job_embeddings_dict = embedding_service.generate_job_embeddings(job)
            job_model_embedding_status = 'success' if job_embeddings_dict else 'no_embeddings_generated'
        except Exception as e:
            logger.error(f"EmbeddingService call failed in generate_job_embeddings_and_ingest_for_rag for job {job_id}: {e}")
            # Decide if to retry or just log and fail this part. For now, let it propagate to task retry.
            raise
        finally:
            emb_duration = time.monotonic() - emb_start_time
            OPENAI_API_CALL_DURATION_SECONDS.labels(type='embedding_job', model=model_name).observe(emb_duration)
            OPENAI_API_CALLS_TOTAL.labels(type='embedding_job', model=model_name, status=job_model_embedding_status).inc()

        rag_ingested_successfully = False
        if job_embeddings_dict and 'combined_embedding' in job_embeddings_dict:
            if 'title_embedding' in job_embeddings_dict: # Save title embedding if present
                job.title_embedding = job_embeddings_dict['title_embedding']
            job.combined_embedding = job_embeddings_dict['combined_embedding'] # This is used for RAG
            
            try:
                job.save(update_fields=['title_embedding', 'combined_embedding'])
                logger.info(f"Saved embeddings to Job model for job_id: {job_id}")
            except Exception as e:
                logger.error(f"Failed to save embeddings to Job model {job_id}: {e}")
                # Continue to RAG ingestion if combined_embedding is available, but log this error.

            # --- 2. Ingest Job Content into RAG Vector Store ---
            # Prepare text content for RAG
            rag_text_content = (
                f"Job Title: {job.title or 'N/A'}\n"
                f"Company: {job.company or 'N/A'}\n"
                f"Location: {job.location or 'N/A'}\n"
                f"Type: {job.get_job_type_display() or 'N/A'}\n" # Use display value for job_type
                f"Description: {job.description or 'N/A'}"
            )
            # Add salary if available and makes sense for RAG search context
            if job.salary_min and job.salary_max:
                rag_text_content += f"\nSalary Range: ${job.salary_min} - ${job.salary_max}"
            elif job.salary_min:
                rag_text_content += f"\nSalary Min: ${job.salary_min}"


            metadata_for_rag = {
                'job_id_original': str(job.id), # Keep original job ID for reference
                'company': job.company,
                'location': job.location,
                'posted_date': str(job.posted_date.isoformat() if job.posted_date else None),
                'job_type': job.job_type, # Store the key, not display value, for potential filtering
                'title': job.title, # Useful for display with RAG results
                # Add any other filterable/useful metadata, e.g., from job.tags if it exists
            }

            # Delete existing RAG document for this job_id to ensure freshness
            # This uses source_id which is str(job.id) for 'job_listing' type
            vector_db_service.delete_documents(source_type='job_listing', source_ids=[str(job.id)])

            add_status = vector_db_service.add_document(
                text_content=rag_text_content,
                embedding=job_embeddings_dict['combined_embedding'], # Use the combined embedding
                source_type='job_listing',
                source_id=str(job.id),
                metadata=metadata_for_rag
            )
            if add_status:
                rag_ingested_successfully = True
                logger.info(f"Successfully added/updated job {job.id} in RAG vector store.")
            else:
                logger.error(f"Failed to add/update job {job.id} in RAG vector store.")

            return {'status': 'success', 'job_id': str(job_id), 'embeddings_saved_to_job': True, 'rag_ingested': rag_ingested_successfully}

        else: # No embeddings generated
            logger.warning(f"No embeddings generated for job: {job.title}, RAG ingestion skipped.")
            return {'status': 'no_embeddings', 'job_id': str(job_id), 'embeddings_saved_to_job': False, 'rag_ingested': False}
            
    except Job.DoesNotExist:
        logger.error(f"Job not found: {job_id}")
        # OPENAI_API_CALLS_TOTAL.labels(type='embedding_job', model='N/A', status='prereq_not_found').inc() # Covered by job_model_embedding_status if needed
        return {'status': 'job_not_found', 'job_id': str(job_id)}
    except Exception as exc:
        logger.error(f"Error in generate_job_embeddings_and_ingest_for_rag for job {job_id}: {exc}")
        # OPENAI_API_CALLS_TOTAL.labels(type='embedding_job', model='N/A', status='task_error').inc() # Covered by job_model_embedding_status
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))


@shared_task(bind=True, max_retries=3)
def generate_user_profile_embeddings(self, user_id):
    """
    Generate AI embeddings for a user profile.
    
    Args:
        user_id: UUID of the user to process
    """
    try:
        from apps.integrations.services.openai import EmbeddingService
        
        user = User.objects.get(id=user_id)
        if not hasattr(user, 'profile'):
            logger.warning(f"User {user_id} has no profile")
            return {'status': 'no_profile', 'user_id': str(user_id)}
        
        embedding_service = EmbeddingService()
        model_name = embedding_service.embedding_model

        start_time = time.monotonic()
        status = 'error'
        try:
            # Generate embeddings
            embeddings = embedding_service.generate_user_profile_embeddings(user.profile)
            status = 'success' if embeddings else 'no_embeddings_generated'
        except Exception as e:
            logger.error(f"EmbeddingService call failed in generate_user_profile_embeddings for user {user_id}: {e}")
            raise # Re-raise to trigger Celery retry
        finally:
            duration = time.monotonic() - start_time
            OPENAI_API_CALL_DURATION_SECONDS.labels(type='embedding_profile', model=model_name).observe(duration)
            OPENAI_API_CALLS_TOTAL.labels(type='embedding_profile', model=model_name, status=status).inc()

        if embeddings:
            # Update profile with embeddings
            if 'profile_embedding' in embeddings:
                user.profile.profile_embedding = embeddings['profile_embedding']
            if 'skills_embedding' in embeddings:
                user.profile.skills_embedding = embeddings['skills_embedding']
            
            user.profile.save(update_fields=['profile_embedding', 'skills_embedding'])
            logger.info(f"Generated embeddings for user profile: {user.get_full_name()}")
            return {'status': 'success', 'user_id': str(user_id)}
        else:
            logger.warning(f"No embeddings generated for user: {user.get_full_name()}")
            return {'status': 'no_embeddings', 'user_id': str(user_id)}
            
    except User.DoesNotExist:
        logger.error(f"User not found: {user_id}")
        return {'status': 'user_not_found', 'user_id': str(user_id)}
    except Exception as exc:
        logger.error(f"Error generating embeddings for user {user_id}: {exc}")
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))


@shared_task(bind=True)
def batch_generate_job_embeddings(self, limit=50):
    """
    Generate embeddings for jobs that don't have them yet.
    
    Args:
        limit: Maximum number of jobs to process
    """
    try:
        from apps.jobs.models import Job
        
        # Find jobs without embeddings
        jobs_without_embeddings = Job.objects.filter(
            combined_embedding__isnull=True,
            status='active'
        )[:limit]
        
        processed = 0
        for job in jobs_without_embeddings:
            # Queue individual embedding task (now renamed)
            generate_job_embeddings_and_ingest_for_rag.delay(str(job.id))
            processed += 1
        
        logger.info(f"Queued embedding generation and RAG ingestion for {processed} jobs")
        return {'status': 'queued', 'count': processed}
        
    except Exception as exc:
        logger.error(f"Error in batch embedding generation: {exc}")
        return {'status': 'error', 'error': str(exc)}


@shared_task(bind=True)
def batch_generate_user_embeddings(self, limit=50):
    """
    Generate embeddings for user profiles that don't have them yet.
    
    Args:
        limit: Maximum number of profiles to process
    """
    try:
        from apps.accounts.models import UserProfile
        
        # Find profiles without embeddings
        profiles_without_embeddings = UserProfile.objects.filter(
            profile_embedding__isnull=True
        ).select_related('user')[:limit]
        
        processed = 0
        for profile in profiles_without_embeddings:
            # Queue individual embedding task
            generate_user_profile_embeddings.delay(str(profile.user.id))
            processed += 1
        
        logger.info(f"Queued embedding generation for {processed} user profiles")
        return {'status': 'queued', 'count': processed}
        
    except Exception as exc:
        logger.error(f"Error in batch user embedding generation: {exc}")
        return {'status': 'error', 'error': str(exc)}


@shared_task(bind=True)
def analyze_job_match_for_user(self, user_id, job_id):
    """
    Analyze how well a user matches a specific job.
    
    Args:
        user_id: UUID of the user
        job_id: UUID of the job
    """
    try:
        from apps.jobs.models import Job
        from apps.integrations.services.openai import OpenAIClient
        
        user = User.objects.get(id=user_id)
        job = Job.objects.get(id=job_id)
        
        if not hasattr(user, 'profile'):
            return {'status': 'no_profile', 'user_id': str(user_id)}
        
        client = OpenAIClient()
        model_name = "gpt-4"  # Default model name for labels
        
        # Prepare user profile text
        profile = user.profile
        user_profile_text = f"""
        Name: {user.get_full_name()}
        Current Title: {profile.current_title or 'Not specified'}
        Experience Level: {profile.get_experience_level_display()}
        Skills: {', '.join(profile.skills) if profile.skills else 'None listed'}
        Location: {profile.location or 'Not specified'}
        """
        
        start_time = time.monotonic()
        api_status = 'error'
        analysis = None
        try:
            # Analyze match
            analysis = client.analyze_job_match(
                job_description=job.description,
                user_profile=user_profile_text,
                user_skills=profile.skills or [],
            )
            api_status = 'success' if analysis else 'no_analysis_generated'
        except Exception as e:
            logger.error(f"OpenAIClient call failed in analyze_job_match_for_user for user {user_id}, job {job_id}: {e}")
            raise # Re-raise for Celery retry
        finally:
            duration = time.monotonic() - start_time
            OPENAI_API_CALL_DURATION_SECONDS.labels(type='job_match_analysis', model=model_name).observe(duration)
            OPENAI_API_CALLS_TOTAL.labels(type='job_match_analysis', model=model_name, status=api_status).inc()

        if analysis:
            logger.info(f"Generated job match analysis for user {user_id} and job {job_id}")
            return {
                'status': 'success', # Task overall status
                'user_id': str(user_id),
                'job_id': str(job_id),
                'analysis': analysis,
            }
        else: # If no analysis content but no exception
            logger.warning(f"No analysis content from OpenAIClient for user {user_id}, job {job_id}")
            return {'status': 'no_analysis_content', 'user_id': str(user_id), 'job_id': str(job_id)}
        
    except (User.DoesNotExist, Job.DoesNotExist) as e:
        logger.error(f"User or job not found: {e}")
        OPENAI_API_CALLS_TOTAL.labels(type='job_match_analysis', model='N/A', status='prereq_not_found').inc()
        return {'status': 'not_found', 'error': str(e)}
    except Exception as exc: # Outer try-except for Celery retry logic
        logger.error(f"Error analyzing job match: {exc}")
        return {'status': 'error', 'error': str(exc)}


@shared_task(bind=True)
def generate_cover_letter_for_application(self, user_id, job_id):
    """
    Generate a cover letter for a job application.
    
    Args:
        user_id: UUID of the user
        job_id: UUID of the job
    """
    try:
        from apps.jobs.models import Job
        from apps.integrations.services.openai import OpenAIClient
        
        user = User.objects.get(id=user_id)
        job = Job.objects.get(id=job_id)
        
        if not hasattr(user, 'profile'):
            return {'status': 'no_profile', 'user_id': str(user_id)}
        
        client = OpenAIClient()
        profile = user.profile
        
        # Prepare user profile text
        user_profile_text = f"""
        Experience Level: {profile.get_experience_level_display()}
        Current Role: {profile.current_title or 'Seeking new opportunities'}
        Skills: {', '.join(profile.skills) if profile.skills else 'Various skills'}
        """
        
        # Get cover letter template if available
        template = profile.cover_letter_template if profile.cover_letter_template else None
        model_name = "gpt-4"  # Default model name for labels

        start_time = time.monotonic()
        api_status = 'error'
        cover_letter = None
        try:
            # Generate cover letter
            cover_letter = client.generate_cover_letter(
                job_title=job.title,
                company_name=job.company,
                job_description=job.description,
                user_profile=user_profile_text,
                user_name=user.get_full_name(),
                template=template,
            )
            api_status = 'success' if cover_letter else 'no_letter_generated'
        except Exception as e:
            logger.error(f"OpenAIClient call failed in generate_cover_letter_for_application for user {user_id}, job {job_id}: {e}")
            raise # Re-raise for Celery retry
        finally:
            duration = time.monotonic() - start_time
            OPENAI_API_CALL_DURATION_SECONDS.labels(type='cover_letter_generation', model=model_name).observe(duration)
            OPENAI_API_CALLS_TOTAL.labels(type='cover_letter_generation', model=model_name, status=api_status).inc()

        if cover_letter:
            logger.info(f"Generated cover letter for user {user_id} and job {job_id}")
            return {
                'status': 'success', # Task overall status
                'user_id': str(user_id),
                'job_id': str(job_id),
                'cover_letter': cover_letter,
            }
        else: # If no cover letter content but no exception
            logger.warning(f"No cover letter content from OpenAIClient for user {user_id}, job {job_id}")
            return {'status': 'no_letter_content', 'user_id': str(user_id), 'job_id': str(job_id)}
        
    except (User.DoesNotExist, Job.DoesNotExist) as e:
        logger.error(f"User or job not found: {e}")
        OPENAI_API_CALLS_TOTAL.labels(type='cover_letter_generation', model='N/A', status='prereq_not_found').inc()
        return {'status': 'not_found', 'error': str(e)}
    except Exception as exc: # Outer try-except for Celery retry logic
        logger.error(f"Error generating cover letter: {exc}")
        return {'status': 'error', 'error': str(exc)}


@shared_task(bind=True)
def cleanup_old_jobs(self, days_old=30):
    """
    Clean up old job postings.
    
    Args:
        days_old: Number of days after which jobs are considered old
    """
    try:
        from apps.jobs.models import Job
        from datetime import timedelta
        
        cutoff_date = timezone.now() - timedelta(days=days_old)
        
        # Update old jobs to expired status
        updated = Job.objects.filter(
            posted_date__lt=cutoff_date,
            status='active'
        ).update(status='expired')
        
        logger.info(f"Marked {updated} old jobs as expired")
        return {'status': 'success', 'updated': updated}
        
    except Exception as exc:
        logger.error(f"Error cleaning up old jobs: {exc}")
        return {'status': 'error', 'error': str(exc)}


@shared_task(bind=True)
def update_job_source_sync_status(self, source_name, status='success', error_message=None):
    """
    Update job source sync status.
    
    Args:
        source_name: Name of the job source
        status: Sync status ('success', 'error', etc.)
        error_message: Optional error message
    """
    try:
        from apps.jobs.models import JobSource
        
        source = JobSource.objects.get(name=source_name)
        source.last_sync = timezone.now()
        source.save(update_fields=['last_sync'])
        
        logger.info(f"Updated sync status for {source_name}: {status}")
        return {'status': 'updated', 'source': source_name}
        
    except JobSource.DoesNotExist:
        logger.error(f"Job source not found: {source_name}")
        return {'status': 'source_not_found', 'source': source_name}
    except Exception as exc:
        logger.error(f"Error updating job source status: {exc}")
        return {'status': 'error', 'error': str(exc)}


# --- Tasks for OpenAIJobAssistant ---
@shared_task(bind=True, max_retries=2) # Shorter retries for potentially faster user-facing features
def get_openai_job_advice_task(self, user_id: int, advice_type: str, context: str = "", user_profile_data: dict = None, query_for_rag: str = None): # Ensure time is imported if used here
    """Celery task to get job advice from OpenAIJobAssistant."""
    # This task IS the implementation that was in OpenAIJobAssistant.get_job_advice
    try:
        # Imports for the actual logic
        from django.conf import settings
        import openai # Ensure openai is imported here if not at top level of tasks.py
        # We need the helper methods from OpenAIJobAssistant or replicate them here.
        # For simplicity, instantiating a slimmed down assistant or directly using its helpers if static.
        # Assuming _build_advice_prompt and _get_mock_advice are part of the assistant
        # and OPENAI_API_KEY, OPENAI_MODEL are accessible via settings.

        api_key = getattr(settings, 'OPENAI_API_KEY', '')
        model = getattr(settings, 'OPENAI_MODEL', 'gpt-4')

        # Replicating _build_advice_prompt logic or making it accessible
        # This is a simplified version. Ideally, _build_advice_prompt would be a static method or utility.
        # For now, let's assume we can call a helper or reconstruct.
        # To avoid circular dependencies if _build_advice_prompt uses other instance methods,
        # it's better to have it as a static/utility or replicate its core logic.
        # For this step, we'll mock the prompt building to focus on the async structure.

        # --- RAG Implementation ---
        rag_context_str = ""
        text_for_rag_embedding = query_for_rag if query_for_rag else context
        if text_for_rag_embedding:
            try:
                from apps.integrations.services.openai import EmbeddingService  # Consolidated
                from apps.common.services import VectorDBService

                embedding_service = EmbeddingService()
                vdb_service = VectorDBService() # Service with implemented ORM logic

                query_embedding_list = embedding_service.generate_embeddings([text_for_rag_embedding])
                if query_embedding_list and query_embedding_list[0]:
                    query_embedding = query_embedding_list[0]

                    rag_filter = None
                    if advice_type == "salary":
                        rag_filter = {'source_type__in': ['job_listing', 'salary_data_article']} # Example source types
                    elif advice_type in ["resume", "interview", "application", "skills", "networking"]:
                        rag_filter = {'source_type__in': ['career_article', 'faq_item']} # Example source types

                    logger.info(f"RAG: Searching documents for advice_type '{advice_type}' with filter: {rag_filter}")
                    similar_docs = vdb_service.search_similar_documents(
                        query_embedding=query_embedding,
                        top_n=3,
                        filter_criteria=rag_filter
                    )

                    if similar_docs:
                        rag_context_parts = ["--- Start of Retrieved Information ---"]
                        for i, doc in enumerate(similar_docs):
                            doc_info = (
                                f"Retrieved Document {i+1} "
                                f"(Source Type: {doc.get('source_type', 'N/A')}, "
                                f"Source ID: {doc.get('source_id', 'N/A')}, " # Useful for debugging/tracing
                                f"Similarity: {doc.get('similarity_score', 0.0):.3f}):" # Display score
                            )
                            rag_context_parts.append(f"{doc_info}\n{doc.get('text_content', '')}")
                        rag_context_parts.append("--- End of Retrieved Information ---")
                        rag_context_str = "\n\n".join(rag_context_parts)
                        logger.info(f"RAG: Retrieved and formatted {len(similar_docs)} documents for advice task.")
                    else:
                        logger.info("RAG: No similar documents found for advice task.")
                else:
                    logger.warning("RAG: Could not generate query embedding for advice task.")
            except Exception as e:
                logger.error(f"RAG pipeline error in get_openai_job_advice_task: {e}")
        # --- End RAG Implementation ---

        # Refined prompt building
        user_profile_summary = "Not specified."
        if user_profile_data:
            user_profile_summary = f"Experience: {user_profile_data.get('experience_level', 'N/A')}, Skills: {', '.join(user_profile_data.get('skills', []))}."

        user_prompt_main_query = f"A user (Profile: {user_profile_summary}) is asking for {advice_type} advice. Their specific question or context is: \"{context}\"."

        prompt_parts = [user_prompt_main_query]
        if rag_context_str:
            prompt_parts.append("\nPlease use the following retrieved information, if relevant, to enhance your answer:")
            prompt_parts.append(rag_context_str)
        user_content_prompt = "\n\n".join(prompt_parts)

        system_message_content = """You are an expert career advisor. Your goal is to provide helpful, actionable advice.
If you are provided with 'Retrieved Information', prioritize using it to answer the user's query, but also use your general knowledge.
Synthesize information rather than just copying from the retrieved documents.
If the retrieved information is not relevant, rely on your general expertise.
Be specific and tailor your advice to the user's profile and question."""

        if not api_key:
            logger.warning(f"OpenAI API key not configured for task: get_openai_job_advice_task for user {user_id}")
            return {'advice_type': advice_type, 'advice': "Mock advice due to no API key.", 'model_used': 'mock_task', 'success': True}

        start_time = time.monotonic()
        status = 'error'
        try:
            from openai import OpenAI
            client = OpenAI(api_key=api_key)
            
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_message_content},
                    {"role": "user", "content": user_content_prompt}
                ],
                max_tokens=1000,
                temperature=0.7
            )
            advice_text = response.choices[0].message.content.strip()
            status = 'success'
            return {
                'advice_type': advice_type,
                'advice': advice_text,
                'model_used': model,
                'success': True
            }
        except Exception as e:
            logger.error(f"OpenAI API call failed in get_openai_job_advice_task: {e}")
            # This return is for the task caller, actual exception is raised for Celery retry
            raise # Re-raise to trigger Celery retry
        finally:
            duration = time.monotonic() - start_time
            OPENAI_API_CALL_DURATION_SECONDS.labels(type='advice', model=model).observe(duration)
            OPENAI_API_CALLS_TOTAL.labels(type='advice', model=model, status=status).inc()

    except Exception as exc: # Outer try-except for Celery retry logic
        logger.error(f"Error in get_openai_job_advice_task for user {user_id}: {exc}")
        raise self.retry(exc=exc, countdown=30 * (2 ** self.request.retries))


@shared_task(bind=True, max_retries=2)
def get_openai_chat_response_task(self, user_id: int, session_id: int, message: str, conversation_history: list = None, user_profile_data: dict = None): # Added session_id
    """Celery task for OpenAIJobAssistant chat responses. Includes core logic and saves AI message."""
    try:
        from django.conf import settings
        from openai import OpenAI as OpenAI_API # Renamed to avoid conflict if openai module is used directly
        import json # For function calling if used directly in task
        from apps.chat.models import ChatSession, ChatMessage # Added for saving message

        api_key = getattr(settings, 'OPENAI_API_KEY', '')
        if not api_key:
            logger.warning(f"OpenAI API key not configured for task: get_openai_chat_response_task for user {user_id}, session {session_id}")
            # Simulate a specific type of failure that the caller might expect (e.g., related to OpenAI setup)
            return {'response': "OpenAI API key not configured.", 'model_used': 'config_error', 'success': False, 'error': 'api_key_missing'}

        client = OpenAI_API(api_key=api_key) # Instantiate OpenAI client with API key
        model = getattr(settings, 'OPENAI_MODEL', 'gpt-4')

        # --- RAG Implementation ---
        rag_context_str = ""
        if message: # Use the user's message for RAG query
            try:
                from apps.integrations.services.openai_service import EmbeddingService
                from apps.common.services import VectorDBService

                embedding_service = EmbeddingService()
                vdb_service = VectorDBService()

                query_embedding_list = embedding_service.generate_embeddings([message])
                if query_embedding_list and query_embedding_list[0]:
                    query_embedding = query_embedding_list[0]
                    
                    # Generic filter for knowledge articles and potentially relevant job listings
                    rag_filter = {
                        "$or": [
                            {"source_type": {"$eq": "knowledge_article"}},
                            {"source_type": {"$eq": "job_listing"}}
                        ]
                    }

                    logger.info(f"RAG (Chat): Searching documents with filter: {rag_filter}")
                    similar_docs = vdb_service.search_similar_documents(
                        query_embedding=query_embedding,
                        top_n=3,
                        filter_criteria=rag_filter
                    )

                    if similar_docs:
                        rag_context_str = "\n\nRetrieved Information:\n" + "\n".join([f"- {doc['text_content']}" for doc in similar_docs])
                        logger.info(f"RAG (Chat): Found {len(similar_docs)} relevant documents for session {session_id}.")
                    else:
                        logger.info(f"RAG (Chat): No relevant documents found for session {session_id}.")
                else:
                    logger.warning(f"RAG (Chat): Could not generate query embedding for session {session_id}.")
            except Exception as e:
                logger.error(f"RAG pipeline error in get_openai_chat_response_task for session {session_id}: {e}")
        # --- End RAG Implementation ---

        # Build conversation history for OpenAI API
        history = conversation_history or []
        
        # System message setup
        system_message_content = """You are Jobraker's AI Assistant, a friendly and expert career advisor.
Your goal is to help users with their job search, providing advice, finding jobs, and answering questions.
If you are provided with 'Retrieved Information', prioritize using it to answer the user's query, but also use your general knowledge.
Synthesize information rather than just copying from the retrieved documents.
If the retrieved information is not relevant, rely on your general expertise."""
        
        messages_for_api = [{"role": "system", "content": system_message_content}]
        messages_for_api.extend(history)
        
        # Add the current user message, potentially with RAG context
        user_content_prompt = message
        if rag_context_str:
            user_content_prompt += f"\n\n--- Context for your answer ---\n{rag_context_str}"
        messages_for_api.append({"role": "user", "content": user_content_prompt})

        start_time = time.monotonic()
        api_status = 'error'
        ai_response_text = "An error occurred while processing your request."
        try:
            response = client.chat.completions.create(
                model=model,
                messages=messages_for_api,
                max_tokens=1500,
                temperature=0.7,
            )
            ai_response_text = response.choices[0].message.content.strip()
            api_status = 'success'
            
            # Save the AI's response to the database
            ChatMessage.objects.create(
                session_id=session_id,
                sender_type='ai',
                content=ai_response_text
            )
            logger.info(f"Successfully generated and saved AI chat response for session {session_id}")

            return {'response': ai_response_text, 'model_used': model, 'success': True}

        except Exception as e:
            logger.error(f"OpenAI API call failed in get_openai_chat_response_task for session {session_id}: {e}")
            # Save an error message to the chat
            ChatMessage.objects.create(
                session_id=session_id,
                sender_type='ai',
                content="I'm sorry, but I encountered an error and couldn't generate a response. Please try again."
            )
            raise self.retry(exc=e, countdown=30 * (2 ** self.request.retries))
        finally:
            duration = time.monotonic() - start_time
            OPENAI_API_CALL_DURATION_SECONDS.labels(type='chat', model=model).observe(duration)
            OPENAI_API_CALLS_TOTAL.labels(type='chat', model=model, status=api_status).inc()

    except ChatSession.DoesNotExist:
        logger.error(f"Chat session not found: {session_id}")
        return {'response': "Chat session not found.", 'success': False, 'error': 'session_not_found'}
    except Exception as exc:
        logger.error(f"Error in get_openai_chat_response_task for user {user_id}, session {session_id}: {exc}")
        # Don't retry if it's not an API error, just log it.
        if not self.request.retries: # Avoid retrying non-API errors repeatedly
             return {'response': "A critical error occurred.", 'success': False, 'error': str(exc)}
        raise


@shared_task(bind=True, max_retries=3)
def submit_job_application_with_skyvern(self, user_id: str, job_id: str, application_id: str):
    """
    Submits a job application using the Skyvern service.
    
    Args:
        user_id: The ID of the user applying.
        job_id: The ID of the job being applied for.
        application_id: The ID of the JobApplication model instance.
    """
    try:
        from apps.jobs.models import Job, JobApplication
        from apps.integrations.services.skyvern import SkyvernService
        from django.contrib.auth import get_user_model
        User = get_user_model()


        user = User.objects.get(id=user_id)
        job = Job.objects.get(id=job_id)
        application = JobApplication.objects.get(id=application_id)
        
        if not job.application_url:
            application.status = 'failed'
            application.notes = 'Application failed: No application URL for the job.'
            application.save()
            logger.error(f"Skyvern submission failed for application {application_id}: No job URL.")
            return {'status': 'error', 'reason': 'no_job_url'}

        skyvern_service = SkyvernService()
        
        # This is a simplified mapping. A real implementation would be more robust.
        user_data = {
            "first_name": user.first_name,
            "last_name": user.last_name,
            "email": user.email,
            "phone": user.profile.phone_number if hasattr(user, 'profile') else "",
            "resume_url": user.profile.resume.url if hasattr(user, 'profile') and user.profile.resume else "",
            # Add other fields as required by Skyvern
        }

        # Filter out empty values
        user_data = {k: v for k, v in user_data.items() if v}

        submission_result = skyvern_service.submit_application(
            application_url=job.application_url,
            user_data=user_data
        )

        SKYVERN_APPLICATION_SUBMISSIONS_TOTAL.inc()

        if submission_result and submission_result.get('success'):
            application.status = 'submitted'
            application.external_application_id = submission_result.get('application_id')
            application.notes = f"Successfully submitted to Skyvern. Monitoring ID: {application.external_application_id}"
            application.save()
            
            # Kick off the monitoring task
            monitor_skyvern_application_status.delay(application_id=str(application.id))
            
            logger.info(f"Successfully submitted application {application_id} to Skyvern.")
            return {'status': 'success', 'application_id': str(application_id), 'skyvern_id': application.external_application_id}
        else:
            error_message = submission_result.get('error', 'Unknown error from Skyvern.')
            application.status = 'failed'
            application.notes = f"Skyvern submission failed: {error_message}"
            application.save()
            logger.error(f"Skyvern submission failed for application {application_id}: {error_message}")
            return {'status': 'error', 'reason': error_message}

    except (User.DoesNotExist, Job.DoesNotExist, JobApplication.DoesNotExist) as e:
        logger.error(f"Could not find User, Job, or Application for Skyvern task: {e}")
        return {'status': 'error', 'reason': 'model_not_found'}
    except Exception as exc:
        logger.error(f"Critical error in submit_job_application_with_skyvern: {exc}")
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))


@shared_task(bind=True, max_retries=10, default_retry_delay=5 * 60) # Retry over a longer period
def monitor_skyvern_application_status(self, application_id: str):
    """
    Periodically checks the status of a submitted Skyvern application.
    
    Args:
        application_id: The ID of our JobApplication model instance.
    """
    try:
        from apps.jobs.models import JobApplication
        from apps.integrations.services.skyvern import SkyvernService

        application = JobApplication.objects.get(id=application_id)
        
        if not application.external_application_id:
            logger.warning(f"Cannot monitor Skyvern status for application {application_id}: no external ID.")
            return {'status': 'error', 'reason': 'no_external_id'}

        skyvern_service = SkyvernService()
        status_result = skyvern_service.get_application_status(application.external_application_id)

        if status_result and status_result.get('success'):
            skyvern_status = status_result.get('status')
            
            # Update our internal status based on Skyvern's response
            # This mapping might need to be adjusted based on actual Skyvern statuses
            if skyvern_status == 'completed':
                application.status = 'applied'
                application.notes = "Skyvern confirmed application completion."
                logger.info(f"Skyvern application {application.external_application_id} completed successfully.")
                # Stop retrying
            elif skyvern_status == 'failed':
                application.status = 'failed'
                application.notes = f"Skyvern reported application failure: {status_result.get('error', 'No details provided.')}
                logger.error(f"Skyvern application {application.external_application_id} failed.")
                # Stop retrying
            else: # e.g., 'in_progress', 'queued'
                # Re-queue the task to check again later
                logger.info(f"Skyvern application {application.external_application_id} is still in progress ({skyvern_status}). Re-checking later.")
                raise self.retry(countdown=15 * 60) # Check again in 15 minutes
            
            application.save()
            return {'status': 'updated', 'new_status': application.status}
        else:
            # The API call to Skyvern failed
            logger.error(f"Failed to get status from Skyvern for application {application.external_application_id}. Retrying...")
            raise self.retry()

    except JobApplication.DoesNotExist:
        logger.error(f"Cannot monitor Skyvern status, JobApplication not found: {application_id}")
        # Do not retry if the application doesn't exist
    except Exception as exc:
        logger.error(f"Critical error in monitor_skyvern_application_status: {exc}")
        raise self.retry(exc=exc)
