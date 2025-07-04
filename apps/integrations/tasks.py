"""
Celery tasks for integration services.
"""

from celery import shared_task
from typing import Dict, Any, Optional, List
from django.utils import timezone
from django.contrib.auth import get_user_model
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
    Fetch jobs from Adzuna API.
    
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
            }
            
            for category in categories:
                stats = processor.fetch_and_process_jobs(
                    what=category,
                    max_pages=2,
                    max_days_old=max_days_old,
                )
                
                for key in total_stats:
                    total_stats[key] += stats[key]
            
            logger.info(f"Adzuna fetch completed for categories {categories}: {total_stats}")
            return total_stats
        else:
            # Sync recent jobs across multiple categories
            stats = processor.sync_recent_jobs(days=max_days_old)
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

        openai.api_key = api_key

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
                from apps.integrations.services.openai import EmbeddingService # Consolidated
                from apps.common.services import VectorDBService # Using actual service path

                embedding_service = EmbeddingService()
                vdb_service = VectorDBService() # Service with implemented ORM logic

                query_embedding_list = embedding_service.generate_embeddings([message])
                if query_embedding_list and query_embedding_list[0]:
                    query_embedding = query_embedding_list[0]

                    # For chat, a generic search might be okay, or we can add simple keyword-based filters.
                    # Example: if user asks about "jobs" or "roles", prioritize 'job_listing' source_type.
                    rag_filter = None
                    if "job" in message.lower() or "role" in message.lower() or "position" in message.lower():
                        rag_filter = {'source_type': 'job_listing'}
                    elif "interview" in message.lower() or "resume" in message.lower():
                        rag_filter = {'source_type__in': ['career_article', 'faq_item']}

                    logger.info(f"RAG: Searching documents for chat message with filter: {rag_filter}")
                    similar_docs = vdb_service.search_similar_documents(
                        query_embedding=query_embedding,
                        top_n=3,
                        filter_criteria=rag_filter
                    )

                    if similar_docs:
                        rag_context_parts = ["--- Start of Retrieved Context ---"]
                        for i, doc in enumerate(similar_docs):
                            doc_info = (
                                f"Retrieved Context Item {i+1} "
                                f"(Source Type: {doc.get('source_type', 'N/A')}, "
                                f"Source ID: {doc.get('source_id', 'N/A')}, "
                                f"Similarity: {doc.get('similarity_score', 0.0):.3f}):"
                            )
                            rag_context_parts.append(f"{doc_info}\n{doc.get('text_content', '')}")
                        rag_context_parts.append("--- End of Retrieved Context ---")
                        rag_context_str = "\n\n".join(rag_context_parts)
                        logger.info(f"RAG: Retrieved and formatted {len(similar_docs)} documents for chat task using functional VectorDBService.")
                    else:
                        logger.info("RAG: No similar documents found for chat task.")
                else:
                    logger.warning("RAG: Could not generate query embedding for chat task.")
            except Exception as e:
                logger.error(f"RAG pipeline error in get_openai_chat_response_task: {e}")
        # --- End RAG Implementation ---

        # Refined system prompt building
        user_profile_context = "Not specified."
        if user_profile_data:
            user_profile_context = f"Experience: {user_profile_data.get('experience_level', 'N/A')}, Skills: {', '.join(user_profile_data.get('skills', []))}."

        system_prompt_parts = [
            f"You are Jobraker AI, a helpful and friendly job search assistant.",
            f"User Profile Context: {user_profile_context}",
            "Always aim to be encouraging and provide actionable steps or information.",
            "Keep your responses conversational but professional."
        ]
        if rag_context_str:
            system_prompt_parts.append(f"\nUse the following retrieved context to inform your response if it's relevant to the user's message. Synthesize it with your general knowledge and do not simply repeat it:")
            system_prompt_parts.append(rag_context_str)
        else:
            system_prompt_parts.append("\nAnswer the user's questions based on your general knowledge and the conversation history.")

        final_system_prompt = "\n".join(system_prompt_parts)

        messages_payload = [{"role": "system", "content": final_system_prompt}]
        if conversation_history:
            messages_payload.extend(conversation_history[-10:])
        messages_payload.append({"role": "user", "content": message})

        if not api_key:
            logger.warning(f"OpenAI API key not configured for task: get_openai_chat_response_task for user {user_id}")
            return {'response': "Mock chat response due to no API key.", 'model_used': 'mock_task', 'success': True}

        # Moderation (simplified for task, ideally a utility function)
        OPENAI_MODERATION_CHECKS_TOTAL.labels(target='user_input').inc()
        mod_start_time = time.monotonic()
        # Use client instance for moderation
        mod_response = client.moderations.create(input=message)
        OPENAI_API_CALL_DURATION_SECONDS.labels(type='moderation', model='text-moderation-latest').observe(time.monotonic() - mod_start_time)
        OPENAI_API_CALLS_TOTAL.labels(type='moderation', model='text-moderation-latest', status='success').inc() # Assuming mod call itself succeeds

        if mod_response.results[0].flagged:
            OPENAI_MODERATION_FLAGGED_TOTAL.labels(target='user_input').inc()
            logger.warning(f"User message flagged in task: get_openai_chat_response_task for user {user_id}, session {session_id}") # Added session_id to log
            return {'response': "Input violates guidelines.", 'model_used': 'moderation_filter', 'success': False, 'error': 'flagged_input'}

        # No need to set openai.api_key globally if client instance is used

        start_time = time.monotonic()
        api_call_status = 'error' # Renamed to avoid conflict with task status for metrics
        ai_response_text = "" # Initialize
        try:
            # Simplified: Not including function calling logic directly in task for this refactor stage to keep it focused.
            # Use client instance for chat completion
            response = client.chat.completions.create(
                model=model,
                messages=messages_payload,
                max_tokens=800,
                temperature=0.7
            )
            ai_response_text = response.choices[0].message.content.strip()
            api_call_status = 'success'
        except Exception as e:
            logger.error(f"OpenAI API call failed in get_openai_chat_response_task: {e}")
            # OPENAI_API_CALLS_TOTAL is updated in finally block
            raise # Re-raise to trigger Celery retry
        finally:
            duration = time.monotonic() - start_time
            OPENAI_API_CALL_DURATION_SECONDS.labels(type='chat', model=model).observe(duration)
            OPENAI_API_CALLS_TOTAL.labels(type='chat', model=model, status=api_call_status).inc()


        # Moderation of AI output (simplified)
        OPENAI_MODERATION_CHECKS_TOTAL.labels(target='ai_output').inc()
        mod_ai_start_time = time.monotonic()
        # Use client instance for moderation
        mod_response_ai = client.moderations.create(input=ai_response_text)
        OPENAI_API_CALL_DURATION_SECONDS.labels(type='moderation', model='text-moderation-latest').observe(time.monotonic() - mod_ai_start_time)
        OPENAI_API_CALLS_TOTAL.labels(type='moderation', model='text-moderation-latest', status='success').inc()

        if mod_response_ai.results[0].flagged:
            OPENAI_MODERATION_FLAGGED_TOTAL.labels(target='ai_output').inc()
            logger.warning(f"AI response flagged in task: get_openai_chat_response_task for user {user_id}, session {session_id}")
            # Even if flagged, we might want to save a placeholder or the flagged message with a note.
            # For now, let's follow the pattern of returning an error status.
            # The actual saving of a "flagged response" message is not done here yet.
        # If AI output is flagged, we don't save it as a regular message.
            return {'response': "AI output violates content guidelines and was not saved.", 'model_used': 'moderation_filter', 'success': False, 'error': 'flagged_ai_output_not_saved'}

        # Save the AI message to the chat session (only if not flagged)
        try:
            chat_session = ChatSession.objects.get(id=session_id)
            ChatMessage.objects.create(
                session=chat_session,
                sender='ai',
                message_text=ai_response_text # Use the variable that holds the text
            )
            chat_session.save(update_fields=['updated_at'])
            logger.info(f"Successfully saved AI response for session {session_id}")
        except ChatSession.DoesNotExist:
            logger.error(f"ChatSession with id {session_id} not found. Cannot save AI message.")
            return {'response': ai_response_text, 'model_used': model, 'success': True, 'error': 'session_not_found_for_saving_message', 'message_saved': False}
        except Exception as e_save:
            logger.error(f"Failed to save AI message for session {session_id}: {e_save}")
            return {'response': ai_response_text, 'model_used': model, 'success': True, 'error': f'message_save_failed: {str(e_save)}', 'message_saved': False}

        return {
            'response': ai_response_text,
            'model_used': model,
            'success': True,
            'message_saved': True
        }
    except Exception as exc: # Outer try-except for Celery retry logic
        logger.error(f"Error in get_openai_chat_response_task for user {user_id}, session {session_id}: {exc}")
        raise self.retry(exc=exc, countdown=30 * (2 ** self.request.retries))


@shared_task(bind=True, max_retries=2)
def analyze_openai_resume_task(self, resume_text: str, target_job: str = "", user_profile_data: dict = None):
    """Celery task for OpenAIJobAssistant resume analysis. Includes core logic."""
    try:
        from django.conf import settings
        import openai

        api_key = getattr(settings, 'OPENAI_API_KEY', '')
        model = getattr(settings, 'OPENAI_MODEL', 'gpt-4')

        # --- RAG Implementation for Resume Analysis ---
        rag_context_str = ""
        if target_job: # Only fetch RAG context if a target job is specified
            try:
                from apps.integrations.services.openai import EmbeddingService # Consolidated
                from apps.common.services import VectorDBService

                embedding_service = EmbeddingService()
                vdb_service = VectorDBService()

                # Embed the target_job description (or a summary/keywords from it)
                # For simplicity, embedding the whole target_job string if it's mostly a description.
                query_embedding_list = embedding_service.generate_embeddings([target_job])

                if query_embedding_list and query_embedding_list[0]:
                    query_embedding = query_embedding_list[0]

                    # Search for KnowledgeArticles related to resume writing or general career advice
                    rag_filter = {'source_type__in': ['career_advice', 'faq_item', 'interview_tips'],
                                  'metadata__category__icontains': 'resume'} # Example filter
                    # Or search for articles tagged with 'resume' or 'cv'
                    # rag_filter = {'metadata__tags__overlap': ['resume', 'cv_writing']}

                    logger.info(f"RAG (ResumeAnalysis): Searching documents with filter: {rag_filter}")
                    similar_docs = vdb_service.search_similar_documents(
                        query_embedding=query_embedding,
                        top_n=2, # Fetch 1-2 relevant advice articles
                        filter_criteria=rag_filter
                    )

                    if similar_docs:
                        rag_context_parts = ["--- Start: Relevant Resume Writing Advice ---"]
                        for i, doc in enumerate(similar_docs):
                            doc_info = (
                                f"Advice Article {i+1} "
                                f"(Source: {doc.get('source_type', 'N/A')}, "
                                f"Similarity to target job: {doc.get('similarity_score', 0.0):.3f}):"
                            )
                            rag_context_parts.append(f"{doc_info}\n{doc.get('text_content', '')}")
                        rag_context_parts.append("--- End: Relevant Resume Writing Advice ---")
                        rag_context_str = "\n\n".join(rag_context_parts)
                        logger.info(f"RAG (ResumeAnalysis): Retrieved {len(similar_docs)} advice articles.")
                    else:
                        logger.info("RAG (ResumeAnalysis): No relevant advice articles found.")
                else:
                    logger.warning("RAG (ResumeAnalysis): Could not generate query embedding for target_job.")
            except Exception as e:
                logger.error(f"RAG pipeline error in analyze_openai_resume_task: {e}")
        # --- End RAG Implementation ---

        # Refined prompt building
        prompt_parts = [
            "Please analyze the following resume and provide specific improvement suggestions.",
            f"\nResume Content:\n---\n{resume_text}\n---"
        ]
        if target_job:
            prompt_parts.append(f"\nThe resume is being tailored for the following Target Job (or job type):\n---\n{target_job}\n---")
        if user_profile_data: # Add user profile context if available
            user_exp = user_profile_data.get('experience_level', 'N/A')
            user_skills = ", ".join(user_profile_data.get('skills', [])) or "N/A"
            prompt_parts.append(f"\nUser Profile Context: Experience Level: {user_exp}, Skills: {user_skills}.")

        if rag_context_str:
            prompt_parts.append(f"\nConsider the following general resume advice when formulating your feedback, if relevant:")
            prompt_parts.append(rag_context_str)

        prompt_parts.append(f"""
Please structure your feedback to include:
1. Overall Assessment and Key Strengths: (General impression and what the resume does well)
2. Specific Areas for Improvement related to the Resume Content: (Actionable feedback on sections, wording, impact statements)
3. Tailoring for Target Job (if specified): (How to better align with the target job description/type)
4. Missing Skills or Experience to Highlight (if applicable based on target job):
5. Formatting and Structure Suggestions: (Readability, ATS compatibility)
6. Keyword Optimization: (Suggestions for incorporating relevant keywords, especially for ATS)""")

        prompt = "\n\n".join(prompt_parts)

        if not api_key:
            logger.warning("OpenAI API key not configured for task: analyze_openai_resume_task")
            return {'analysis': "Mock resume analysis due to no API key.", 'model_used': 'mock_task', 'success': True}

        openai.api_key = api_key

        start_time = time.monotonic()
        status = 'error'
        try:
            response = openai.ChatCompletion.create(
                model=model,
                messages=[
                    {"role": "system", "content": "You are an expert resume reviewer."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=1200,
                temperature=0.7
            )
            analysis = response.choices[0].message.content.strip()
            status = 'success'
            return {
                'analysis': analysis,
                'target_job': target_job,
                'model_used': model,
                'success': True
            }
        except Exception as e:
            logger.error(f"OpenAI API call failed in analyze_openai_resume_task: {e}")
            raise # Re-raise to trigger Celery retry
        finally:
            duration = time.monotonic() - start_time
            OPENAI_API_CALL_DURATION_SECONDS.labels(type='resume_analysis', model=model).observe(duration)
            OPENAI_API_CALLS_TOTAL.labels(type='resume_analysis', model=model, status=status).inc()

    except Exception as exc: # Outer try-except for Celery retry logic
        logger.error(f"Error in analyze_openai_resume_task: {exc}")
        raise self.retry(exc=exc, countdown=30 * (2 ** self.request.retries))

# --- Ensure existing OpenAI tasks correctly call service methods if they are also to be made async ---
# generate_job_embeddings, generate_user_profile_embeddings, analyze_job_match_for_user,
# and generate_cover_letter_for_application already call the respective service methods.
# If those service methods are changed to be async launchers, these tasks become the actual workers.
# No change needed here for those existing tasks, but the service methods they call will be changed.

# It's harder to get token counts consistently without parsing responses carefully,
# so omitting token metrics for now unless the library exposes them easily.
# --- End Prometheus Metrics ---


# --- Tasks for Skyvern API Integration ---
@shared_task(bind=True, max_retries=3)
def submit_skyvern_application_task(self, application_id: str, job_url: str, prompt_template: str, user_profile_data: Dict[str, Any], resume_base64: Optional[str] = None, cover_letter_base64: Optional[str] = None):
    """
    Submits a job application using Skyvern.
    Args:
        application_id: JobRaker internal application ID for tracking.
        job_url: The URL of the job posting to apply to.
        prompt_template: A template for the Skyvern prompt, e.g., "Apply to job at {job_url}..."
        user_profile_data: Serialized user profile information.
        resume_base64: Base64 encoded resume content.
        cover_letter_base64: Base64 encoded cover letter content (optional).
    """
    from apps.integrations.services.skyvern import SkyvernAPIClient
    from apps.jobs.models import Application # Now using the Application model

    logger.info(f"Starting Skyvern application task for JobRaker app ID: {application_id}, Job URL: {job_url}")

    try:
        application = Application.objects.get(id=application_id)
    except Application.DoesNotExist:
        logger.error(f"Application {application_id} not found in submit_skyvern_application_task.")
        # Increment a metric for this case if desired
        SKYVERN_APPLICATION_SUBMISSIONS_TOTAL.labels(status='application_not_found').inc()
        return {"status": "error", "application_id": application_id, "error": "Application not found"}

    client = SkyvernAPIClient()

    # Construct inputs for Skyvern
    skyvern_inputs = {
        "target_job_url": job_url,
        "user_profile_data": user_profile_data,
    }
    if resume_base64:
        skyvern_inputs["resume_base64"] = resume_base64
    if cover_letter_base64:
        skyvern_inputs["cover_letter_base64"] = cover_letter_base64

    prompt = prompt_template.format(job_url=job_url) # Basic prompt formatting

    # Potentially get webhook_url from settings or construct it
    # webhook_url = getattr(settings, 'SKYVERN_WEBHOOK_URL', None)
    webhook_url = None # Placeholder

    try:
        response = client.run_task(
            prompt=prompt,
            inputs=skyvern_inputs,
            webhook_url=webhook_url
        )

        if response and response.get("task_id"):
            skyvern_task_id = response["task_id"]
            logger.info(f"Skyvern task created: {skyvern_task_id} for JobRaker app ID: {application_id}")

            application.skyvern_task_id = skyvern_task_id
            application.status = 'submitting_via_skyvern' # Using one of the new statuses
            application.save(update_fields=['skyvern_task_id', 'status', 'updated_at'])

            SKYVERN_APPLICATION_SUBMISSIONS_TOTAL.labels(status='initiated').inc()
            return {"status": "success", "skyvern_task_id": skyvern_task_id, "application_id": application_id}
        else:
            logger.error(f"Skyvern task creation failed for JobRaker app ID: {application_id}. Response: {response}")
            application.status = 'skyvern_submission_failed' # New status
            application.skyvern_response_data = response # Store failure response if any
            application.save(update_fields=['status', 'skyvern_response_data', 'updated_at'])
            SKYVERN_APPLICATION_SUBMISSIONS_TOTAL.labels(status='creation_failed').inc()
            return {"status": "failure", "application_id": application_id, "error": "Task creation failed", "response": response}

    except Exception as exc:
        logger.error(f"Error in submit_skyvern_application_task for app ID {application_id}: {exc}")
        if 'application' in locals(): # Check if application object was fetched
            application.status = 'skyvern_submission_failed' # Or a more generic error status
            application.skyvern_response_data = {'error': str(exc)}
            application.save(update_fields=['status', 'skyvern_response_data', 'updated_at'])
        SKYVERN_APPLICATION_SUBMISSIONS_TOTAL.labels(status='task_exception').inc()
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))


@shared_task(bind=True, max_retries=5, default_retry_delay=5 * 60) # Retry less frequently for status checks
def check_skyvern_task_status_task(self, skyvern_task_id: str, application_id: str):
    """
    Checks the status of a Skyvern task and updates the JobRaker application.
    Args:
        skyvern_task_id: The task ID from Skyvern.
        application_id: JobRaker internal application ID for tracking.
    """
    from apps.integrations.services.skyvern import SkyvernAPIClient
    from apps.jobs.models import Application # Now using the Application model
    from django.utils import timezone

    logger.info(f"Checking Skyvern task status for task_id: {skyvern_task_id}, JobRaker app ID: {application_id}")

    try:
        application = Application.objects.get(id=application_id, skyvern_task_id=skyvern_task_id)
    except Application.DoesNotExist:
        logger.error(f"Application {application_id} with Skyvern task ID {skyvern_task_id} not found in check_skyvern_task_status_task.")
        SKYVERN_APPLICATION_SUBMISSIONS_TOTAL.labels(status='check_app_not_found').inc()
        # Do not retry if app not found, as it's a data integrity issue.
        return {"status": "error", "application_id": application_id, "error": "Application for Skyvern task not found"}

    client = SkyvernAPIClient()

    try:
        status_response = client.get_task_status(skyvern_task_id)

        if not status_response:
            logger.warning(f"Failed to get status for Skyvern task {skyvern_task_id}. Will retry.")
            raise Exception(f"No response from Skyvern for task status {skyvern_task_id}") # Trigger retry

        current_skyvern_status = status_response.get("status") # e.g., PENDING, RUNNING, COMPLETED, FAILED
        logger.info(f"Skyvern task {skyvern_task_id} status: {current_skyvern_status}")

        new_jobraker_status = application.status # Keep current status if no change
        skyvern_message = status_response.get("message", "")

        if current_skyvern_status == "COMPLETED":
            new_jobraker_status = 'submitted' # Successfully submitted via Skyvern
            application.applied_at = timezone.now() # Mark as applied now
            SKYVERN_APPLICATION_SUBMISSIONS_TOTAL.labels(status='completed_success').inc()
            # Trigger results fetching task
            retrieve_skyvern_task_results_task.delay(skyvern_task_id, application_id)
        elif current_skyvern_status == "FAILED":
            new_jobraker_status = 'skyvern_submission_failed'
            SKYVERN_APPLICATION_SUBMISSIONS_TOTAL.labels(status='failed').inc()
            # Store error details from Skyvern if available in results, or this message
            application.skyvern_response_data = status_response # Store the status response itself
        elif current_skyvern_status == "CANCELED":
            new_jobraker_status = 'skyvern_canceled'
            SKYVERN_APPLICATION_SUBMISSIONS_TOTAL.labels(status='canceled').inc()
            application.skyvern_response_data = status_response
        elif current_skyvern_status == "REQUIRES_ATTENTION":
            new_jobraker_status = 'skyvern_requires_attention'
            SKYVERN_APPLICATION_SUBMISSIONS_TOTAL.labels(status='requires_attention').inc()
            application.skyvern_response_data = status_response
        elif current_skyvern_status in ["PENDING", "RUNNING"]:
            # Still ongoing, ensure JobRaker status reflects this if it was different
            if application.status not in ['submitting_via_skyvern']:
                 new_jobraker_status = 'submitting_via_skyvern'
            logger.info(f"Skyvern task {skyvern_task_id} is still {current_skyvern_status}.")
            # No need to explicitly retry here for PENDING/RUNNING if this task is scheduled periodically by Celery Beat,
            # or if a webhook is the primary update mechanism. If purely polling, a retry might be desired.
            # For now, assume periodic checks or webhook will handle follow-up.
        else: # Unknown status
            logger.warning(f"Unknown Skyvern status '{current_skyvern_status}' for task {skyvern_task_id}.")
            # Potentially set a generic error or requires attention status
            # For now, no status change for unknown Skyvern status.

        if new_jobraker_status != application.status or application.applied_at: # If status changed or applied_at set
            application.status = new_jobraker_status
            fields_to_update = ['status', 'updated_at']
            if application.applied_at: # Ensure applied_at is in update_fields if set
                fields_to_update.append('applied_at')
            if application.skyvern_response_data: # Ensure response data is in update_fields if set
                fields_to_update.append('skyvern_response_data')
            application.save(update_fields=fields_to_update)
            logger.info(f"Updated JobRaker app ID {application_id} status to {new_jobraker_status} for Skyvern task {skyvern_task_id}")

        return {"status": "polled", "skyvern_task_id": skyvern_task_id, "skyvern_status": current_skyvern_status, "application_id": application_id}

    except Exception as exc: # For API call errors or other issues
        logger.error(f"Error in check_skyvern_task_status_task for Skyvern task {skyvern_task_id}: {exc}")
        raise self.retry(exc=exc) # Celery will use default_retry_delay


# Placeholder for task to retrieve results, can be called after status is COMPLETED
@shared_task(bind=True, max_retries=3)
def retrieve_skyvern_task_results_task(self, skyvern_task_id: str, application_id: str):
    from apps.integrations.services.skyvern import SkyvernAPIClient
    from apps.jobs.models import Application # Now using the Application model

    logger.info(f"Retrieving results for Skyvern task {skyvern_task_id}, JobRaker app ID: {application_id}")

    try:
        application = Application.objects.get(id=application_id, skyvern_task_id=skyvern_task_id)
    except Application.DoesNotExist:
        logger.error(f"Application {application_id} with Skyvern task ID {skyvern_task_id} not found in retrieve_skyvern_task_results_task.")
        # No retry, data issue.
        return {"status": "error", "application_id": application_id, "error": "Application for Skyvern task not found"}

    client = SkyvernAPIClient()
    try:
        results_response = client.get_task_results(skyvern_task_id)

        if results_response:
            logger.info(f"Results for Skyvern task {skyvern_task_id}: {results_response}")
            application.skyvern_response_data = results_response # Store the entire raw response

            # Potentially parse results_response.get('data') for specific confirmation details
            # or results_response.get('error_details') if status was FAILED.
            # For now, storing raw response is sufficient.
            # If Skyvern task failed and results contain error details, ensure status reflects this.
            skyvern_status_in_results = results_response.get("status")
            if skyvern_status_in_results == "FAILED" and application.status != 'skyvern_submission_failed':
                application.status = 'skyvern_submission_failed'
                logger.info(f"Updating application {application_id} status to 'skyvern_submission_failed' based on task results.")

            application.save(update_fields=['skyvern_response_data', 'status', 'updated_at'])
            return {"status": "success", "skyvern_task_id": skyvern_task_id, "application_id": application_id, "results_fetched": True}
        else:
            logger.warning(f"No results data found for Skyvern task {skyvern_task_id} (API call might have returned None or empty).")
            # Optionally update application model to note that results retrieval was attempted but empty.
            application.skyvern_response_data = {"info": "Results retrieval attempted, no data returned by Skyvern."}
            application.save(update_fields=['skyvern_response_data', 'updated_at'])
            return {"status": "no_results_data", "skyvern_task_id": skyvern_task_id, "application_id": application_id}

    except Exception as exc:
        logger.error(f"Error retrieving results for Skyvern task {skyvern_task_id}: {exc}")
        raise self.retry(exc=exc)


# --- Task for KnowledgeArticle RAG Ingestion ---
@shared_task(bind=True, max_retries=3)
def process_knowledge_article_for_rag_task(self, article_id: int):
    """
    Generates embedding for a KnowledgeArticle and ingests/updates it in the RAG vector store.
    Args:
        article_id: ID of the KnowledgeArticle to process.
    """
    try:
        from apps.common.models import KnowledgeArticle
        from apps.integrations.services.openai import EmbeddingService # Consolidated
        from apps.common.services import VectorDBService

        article = KnowledgeArticle.objects.get(id=article_id)

        if not article.is_active:
            logger.info(f"KnowledgeArticle {article_id} is not active. Deleting from RAG store if present.")
            vector_db_service = VectorDBService()
            vector_db_service.delete_documents(source_type=article.source_type, source_id=str(article.id))
            return {'status': 'skipped_inactive_deleted', 'article_id': article_id}

        embedding_service = EmbeddingService()
        vector_db_service = VectorDBService()
        model_name = embedding_service.embedding_model # For metrics

        text_to_embed = f"Title: {article.title}\nContent: {article.content}"

        embedding_generation_status = 'error'
        article_embedding_list = None
        try:
            emb_start_time = time.monotonic()
            article_embedding_list = embedding_service.generate_embeddings([text_to_embed])
            embedding_generation_status = 'success' if article_embedding_list and article_embedding_list[0] else 'no_embedding_generated'
        except Exception as e:
            logger.error(f"EmbeddingService call failed for KnowledgeArticle {article_id}: {e}")
            raise # Re-raise to trigger Celery retry
        finally:
            emb_duration = time.monotonic() - emb_start_time
            OPENAI_API_CALL_DURATION_SECONDS.labels(type=f'embedding_knowledge_{article.source_type}', model=model_name).observe(emb_duration)
            OPENAI_API_CALLS_TOTAL.labels(type=f'embedding_knowledge_{article.source_type}', model=model_name, status=embedding_generation_status).inc()

        if article_embedding_list and article_embedding_list[0]:
            article_embedding = article_embedding_list[0]

            metadata_for_rag = {
                'article_id_original': str(article.id),
                'title': article.title,
                'category': article.category,
                'tags': article.get_tags_list(), # Store as list
                'source_type_display': article.get_source_type_display() # Store display name
            }

            # Delete existing RAG document for this article_id to ensure freshness
            vector_db_service.delete_documents(source_type=article.source_type, source_id=str(article.id))

            add_status = vector_db_service.add_documents(
                texts=[text_to_embed], # Could also store just article.content if title is only for metadata
                embeddings=[article_embedding],
                source_types=[article.source_type], # Use the article's own source_type
                source_ids=[str(article.id)],
                metadatas=[metadata_for_rag]
            )

            if add_status:
                logger.info(f"Successfully processed and ingested KnowledgeArticle {article.id} ('{article.title}') for RAG.")
                return {'status': 'success', 'article_id': article_id, 'rag_ingested': True}
            else:
                logger.error(f"Failed to add/update KnowledgeArticle {article.id} in RAG vector store.")
                return {'status': 'rag_add_failed', 'article_id': article_id, 'rag_ingested': False}
        else:
            logger.warning(f"No embedding generated for KnowledgeArticle {article.id}, RAG ingestion skipped.")
            return {'status': 'no_embedding', 'article_id': article_id, 'rag_ingested': False}

    except KnowledgeArticle.DoesNotExist:
        logger.error(f"KnowledgeArticle not found: {article_id}")
        return {'status': 'article_not_found', 'article_id': article_id}
    except Exception as exc:
        logger.error(f"Error processing KnowledgeArticle {article_id} for RAG: {exc}")
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))


@shared_task(bind=True, max_retries=3)
def generate_interview_questions_task(self, job_id: str, user_id: Optional[str] = None):
    """
    Generates interview questions for a specific job using OpenAI.
    Optionally considers user profile for personalization if user_id is provided.
    """
    from apps.jobs.models import Job
    from apps.accounts.models import UserProfile # For fetching user profile summary
    from apps.integrations.services.openai import OpenAIClient

    logger.info(f"Starting interview question generation for Job ID: {job_id}, User ID: {user_id}")

    try:
        job = Job.objects.get(id=job_id)
    except Job.DoesNotExist:
        logger.error(f"Job with ID {job_id} not found for interview question generation.")
        return {"status": "error", "error": "Job not found", "job_id": job_id}

    user_profile_summary = None
    if user_id:
        try:
            user_profile = UserProfile.objects.get(user_id=user_id)
            # Create a concise summary from the profile. Adjust fields as needed.
            summary_parts = []
            if user_profile.current_title:
                summary_parts.append(f"Current Title: {user_profile.current_title}")
            if user_profile.experience_level:
                summary_parts.append(f"Experience Level: {user_profile.get_experience_level_display()}") # Use display value
            if user_profile.skills:
                summary_parts.append(f"Key Skills: {', '.join(user_profile.skills[:5])}") # Top 5 skills
            if user_profile.bio:
                summary_parts.append(f"Bio Snippet: {user_profile.bio[:200]}...") # Short bio snippet

            if summary_parts:
                user_profile_summary = ". ".join(summary_parts)
            logger.info(f"User profile summary for personalization: {user_profile_summary}")

        except UserProfile.DoesNotExist:
            logger.warning(f"UserProfile not found for User ID: {user_id}. Proceeding without personalization.")
        except Exception as e:
            logger.error(f"Error fetching or summarizing UserProfile for User ID {user_id}: {e}")
            # Proceed without personalization if profile fetching fails

    client = OpenAIClient()
    model_name_client = "gpt-4"  # Default model name for metrics

    api_call_status = 'error'
    questions = []
    start_time = time.monotonic() # For duration metric

    try:
        questions = client.generate_interview_questions(
            job_title=job.title,
            job_description=job.description,
            # num_questions=10, # Default in client method
            # question_types=["technical", "behavioral", "situational"], # Example, or let client default
            user_profile_summary=user_profile_summary
        )
        api_call_status = 'success' if questions else 'no_questions_generated'

        # Log result for now. The task result will be stored by Celery if a backend is configured.
        logger.info(f"Generated {len(questions)} interview questions for Job ID: {job_id}. API status: {api_call_status}")

        # The return value of the task is what gets stored in the result backend.
        return {
            "job_id": str(job.id),
            "job_title": job.title,
            "questions": questions,
            "status": api_call_status # To indicate if questions were successfully generated by OpenAI
        }

    except Exception as e:
        logger.error(f"OpenAIClient call failed in generate_interview_questions_task for Job {job_id}: {e}", exc_info=True)
        # Re-raise to allow Celery to retry if max_retries not reached
        # OPENAI_API_CALLS_TOTAL metric will be updated by the finally block if it's outside this try
        raise self.retry(exc=e, countdown=60 * (2 ** self.request.retries))
    finally:
        duration = time.monotonic() - start_time
        OPENAI_API_CALL_DURATION_SECONDS.labels(type='interview_question_generation', model=model_name_client or 'unknown').observe(duration)
        OPENAI_API_CALLS_TOTAL.labels(type='interview_question_generation', model=model_name_client or 'unknown', status=api_call_status).inc()
