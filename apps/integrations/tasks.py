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

        start_time = time.monotonic()
        status = 'error'
        try:
            from openai import OpenAI
            client = OpenAI(api_key=api_key)
            
            response = client.chat.completions.create(
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


# =======================
# CRITICAL MISSING TASKS
# =======================

@shared_task(bind=True, max_retries=3)
def automated_daily_job_sync(self):
    """
    Daily automated job synchronization from all sources.
    This is the main job that runs daily to fetch new jobs.
    """
    try:
        logger.info("Starting daily automated job sync")
        
        # 1. Fetch from Adzuna API
        adzuna_stats = fetch_adzuna_jobs.delay([
            'software', 'engineering', 'data', 'product', 'marketing', 
            'sales', 'finance', 'operations', 'design', 'hr'
        ], max_days_old=1)
        
        # 2. Clean up old jobs (older than 30 days)
        cleanup_stats = cleanup_old_jobs.delay(days_old=30)
        
        # 3. Update job statistics
        update_job_statistics.delay()
        
        logger.info("Daily job sync tasks queued successfully")
        return {
            'status': 'success',
            'adzuna_task_id': adzuna_stats.id,
            'cleanup_task_id': cleanup_stats.id,
            'timestamp': timezone.now().isoformat()
        }
        
    except Exception as exc:
        logger.error(f"Error in daily job sync: {exc}")
        raise self.retry(exc=exc, countdown=300)  # 5 minute retry


@shared_task(bind=True, max_retries=3)
def cleanup_old_jobs(self, days_old=30):
    """
    Clean up old job postings to keep database manageable.
    """
    try:
        from apps.jobs.models import Job
        
        cutoff_date = timezone.now() - timedelta(days=days_old)
        
        # Mark old jobs as inactive instead of deleting
        updated_count = Job.objects.filter(
            created_at__lt=cutoff_date,
            is_active=True
        ).update(is_active=False)
        
        logger.info(f"Marked {updated_count} old jobs as inactive")
        return {'cleaned_jobs': updated_count}
        
    except Exception as exc:
        logger.error(f"Error cleaning up old jobs: {exc}")
        raise self.retry(exc=exc, countdown=300)


@shared_task(bind=True, max_retries=3)
def update_job_statistics(self):
    """
    Update job market statistics and trends.
    """
    try:
        from apps.jobs.models import Job
        from django.db.models import Count, Avg
        
        # Calculate statistics
        stats = {
            'total_active_jobs': Job.objects.filter(is_active=True).count(),
            'jobs_by_type': dict(Job.objects.filter(is_active=True)
                                .values('job_type')
                                .annotate(count=Count('id'))),
            'avg_salary': Job.objects.filter(
                is_active=True, 
                salary_min__isnull=False
            ).aggregate(avg=Avg('salary_min'))['avg'],
            'updated_at': timezone.now().isoformat()
        }
        
        # Could store in cache or dedicated statistics table
        from django.core.cache import cache
        cache.set('job_market_stats', stats, timeout=86400)  # 24 hours
        
        logger.info(f"Updated job statistics: {stats['total_active_jobs']} active jobs")
        return stats
        
    except Exception as exc:
        logger.error(f"Error updating job statistics: {exc}")
        raise self.retry(exc=exc, countdown=300)


@shared_task(bind=True, max_retries=3)
def intelligent_job_matching(self, user_id):
    """
    AI-powered job matching for a specific user.
    Generates personalized job recommendations.
    """
    try:
        from apps.jobs.models import Job, RecommendedJob
        from apps.integrations.services.openai import EmbeddingService
        from apps.common.services import VectorDBService
        
        user = User.objects.get(id=user_id)
        profile = getattr(user, 'profile', None)
        
        if not profile:
            logger.warning(f"User {user_id} has no profile for job matching")
            return {'status': 'no_profile'}
        
        # Generate user profile embedding if not exists
        if not profile.profile_embedding:
            generate_user_profile_embeddings.delay(user_id)
            logger.info(f"Queued profile embedding generation for user {user_id}")
            return {'status': 'embedding_queued'}
        
        # Use vector search to find similar jobs
        vector_db_service = VectorDBService()
        embedding_service = EmbeddingService()
        
        # Create search query from user profile
        search_text = f"Job seeker with skills: {profile.skills}, experience: {profile.experience_level}, interests: {profile.bio}"
        
        # Get job recommendations
        similar_jobs = vector_db_service.search_similar_documents(
            query_text=search_text,
            source_type='job_listing',
            limit=20
        )
        
        # Process recommendations
        recommendations_created = 0
        for job_match in similar_jobs:
            try:
                job_id = job_match.get('metadata', {}).get('job_id_original')
                if job_id:
                    job = Job.objects.get(id=job_id, is_active=True)
                    
                    # Create or update recommendation
                    recommendation, created = RecommendedJob.objects.get_or_create(
                        user=user,
                        job=job,
                        defaults={
                            'match_score': job_match.get('similarity_score', 0.0),
                            'recommendation_reason': f"AI match score: {job_match.get('similarity_score', 0.0):.2f}"
                        }
                    )
                    
                    if created:
                        recommendations_created += 1
                        
            except Job.DoesNotExist:
                continue
        
        logger.info(f"Generated {recommendations_created} new job recommendations for user {user_id}")
        
        # Trigger email notification if user has recommendations
        if recommendations_created > 0:
            from apps.notifications.tasks import send_job_recommendations_task
            send_job_recommendations_task.delay(user_id)
        
        return {
            'status': 'success',
            'recommendations_created': recommendations_created,
            'user_id': str(user_id)
        }
        
    except User.DoesNotExist:
        logger.error(f"User {user_id} not found for job matching")
        return {'status': 'user_not_found'}
    except Exception as exc:
        logger.error(f"Error in intelligent job matching for user {user_id}: {exc}")
        raise self.retry(exc=exc, countdown=300)


@shared_task(bind=True, max_retries=3)
def batch_intelligent_job_matching(self, limit=50):
    """
    Run intelligent job matching for multiple users.
    """
    try:
        from apps.accounts.models import UserProfile
        
        # Get users with profiles who haven't had recommendations recently
        cutoff_time = timezone.now() - timedelta(days=7)  # Weekly recommendations
        
        users_for_matching = User.objects.filter(
            profile__isnull=False,
            is_active=True
        ).exclude(
            recommendedjob__created_at__gte=cutoff_time
        )[:limit]
        
        queued_count = 0
        for user in users_for_matching:
            intelligent_job_matching.delay(user.id)
            queued_count += 1
        
        logger.info(f"Queued intelligent job matching for {queued_count} users")
        return {'status': 'success', 'queued_users': queued_count}
        
    except Exception as exc:
        logger.error(f"Error in batch job matching: {exc}")
        raise self.retry(exc=exc, countdown=300)


@shared_task(bind=True, max_retries=3)
def submit_application_via_skyvern(self, application_id):
    """
    Submit job application using Skyvern automation.
    """
    try:
        from apps.jobs.models import Application
        from apps.integrations.services.skyvern import SkyvernAPIClient
        
        application = Application.objects.select_related('user', 'job').get(id=application_id)
        
        # Check if application can be automated
        if not application.job.application_url:
            logger.warning(f"Job {application.job.id} has no application URL for Skyvern automation")
            return {'status': 'no_url', 'application_id': application_id}
        
        skyvern_client = SkyvernAPIClient()
        
        # Prepare application data
        application_data = {
            'url': application.job.application_url,
            'user_data': {
                'name': f"{application.user.first_name} {application.user.last_name}",
                'email': application.user.email,
                'phone': getattr(application.user.profile, 'phone_number', ''),
                'resume_url': application.resume_file.url if application.resume_file else None,
                'cover_letter': application.cover_letter or ''
            },
            'job_data': {
                'title': application.job.title,
                'company': application.job.company,
                'location': application.job.location
            }
        }
        
        # Create Skyvern task
        task_result = skyvern_client.create_task(
            url=application.job.application_url,
            task_data=application_data
        )
        
        if task_result and 'task_id' in task_result:
            # Update application with Skyvern task ID
            application.skyvern_task_id = task_result['task_id']
            application.status = 'submitted'
            application.save()
            
            # Queue status monitoring
            monitor_skyvern_task.delay(application.id, task_result['task_id'])
            
            logger.info(f"Skyvern task {task_result['task_id']} created for application {application_id}")
            
            # Send status update email
            from apps.notifications.tasks import send_application_status_update_task
            send_application_status_update_task.delay(application_id, 'pending')
            
            return {
                'status': 'submitted',
                'task_id': task_result['task_id'],
                'application_id': application_id
            }
        else:
            logger.error(f"Failed to create Skyvern task for application {application_id}")
            return {'status': 'failed_to_create_task'}
        
    except Application.DoesNotExist:
        logger.error(f"Application {application_id} not found")
        return {'status': 'application_not_found'}
    except Exception as exc:
        logger.error(f"Error submitting application {application_id} via Skyvern: {exc}")
        raise self.retry(exc=exc, countdown=600)  # 10 minute retry


@shared_task(bind=True, max_retries=5)
def monitor_skyvern_task(self, application_id, task_id):
    """
    Monitor Skyvern task status and update application accordingly.
    """
    try:
        from apps.jobs.models import Application
        from apps.integrations.services.skyvern import SkyvernAPIClient
        
        application = Application.objects.get(id=application_id)
        skyvern_client = SkyvernAPIClient()
        
        # Check task status
        task_status = skyvern_client.get_task_status(task_id)
        
        if not task_status:
            logger.warning(f"Could not get status for Skyvern task {task_id}")
            raise self.retry(countdown=300)  # Retry in 5 minutes
        
        status = task_status.get('status', '').lower()
        
        if status == 'completed':
            # Get task results
            task_result = skyvern_client.get_task_result(task_id)
            
            if task_result and task_result.get('success'):
                application.status = 'submitted'
                application.skyvern_result = task_result
                application.save()
                
                logger.info(f"Skyvern application submission completed for application {application_id}")
                
                # Send success notification
                from apps.notifications.tasks import send_application_status_update_task
                send_application_status_update_task.delay(application_id, 'pending')
                
                return {'status': 'completed', 'success': True}
            else:
                application.status = 'failed'
                application.skyvern_result = task_result
                application.save()
                
                logger.error(f"Skyvern task {task_id} completed but failed for application {application_id}")
                return {'status': 'completed', 'success': False}
                
        elif status == 'failed':
            application.status = 'failed'
            application.skyvern_result = task_status
            application.save()
            
            logger.error(f"Skyvern task {task_id} failed for application {application_id}")
            return {'status': 'failed'}
            
        elif status in ['running', 'queued', 'pending']:
            # Task still in progress, retry monitoring
            logger.info(f"Skyvern task {task_id} still {status}, will retry monitoring")
            raise self.retry(countdown=300)  # Check again in 5 minutes
            
        else:
            logger.warning(f"Unknown Skyvern task status: {status} for task {task_id}")
            raise self.retry(countdown=300)
        
    except Application.DoesNotExist:
        logger.error(f"Application {application_id} not found while monitoring Skyvern task")
        return {'status': 'application_not_found'}
    except Exception as exc:
        logger.error(f"Error monitoring Skyvern task {task_id}: {exc}")
        raise self.retry(exc=exc, countdown=600)


@shared_task(bind=True, max_retries=3)
def process_pending_applications(self):
    """
    Process applications that are pending Skyvern automation.
    """
    try:
        from apps.jobs.models import Application
        
        # Get pending applications that haven't been processed
        pending_applications = Application.objects.filter(
            status='pending',
            skyvern_task_id__isnull=True,
            job__application_url__isnull=False
        ).select_related('user', 'job')[:10]  # Limit to avoid overwhelming Skyvern
        
        processed_count = 0
        for application in pending_applications:
            submit_application_via_skyvern.delay(application.id)
            processed_count += 1
        
        logger.info(f"Queued {processed_count} applications for Skyvern processing")
        return {'status': 'success', 'queued_applications': processed_count}
        
    except Exception as exc:
        logger.error(f"Error processing pending applications: {exc}")
        raise self.retry(exc=exc, countdown=300)


@shared_task(bind=True)
def weekly_system_maintenance(self):
    """
    Weekly maintenance tasks for the system.
    """
    try:
        logger.info("Starting weekly system maintenance")
        
        # 1. Batch generate missing embeddings
        batch_generate_job_embeddings.delay(limit=100)
        batch_generate_user_embeddings.delay(limit=100)
        
        # 2. Run intelligent job matching for all users
        batch_intelligent_job_matching.delay(limit=200)
        
        # 3. Clean up old data
        cleanup_old_jobs.delay(days_old=45)
        
        # 4. Update statistics
        update_job_statistics.delay()
        
        logger.info("Weekly maintenance tasks queued successfully")
        return {'status': 'success', 'timestamp': timezone.now().isoformat()}
        
    except Exception as exc:
        logger.error(f"Error in weekly maintenance: {exc}")
        return {'status': 'error', 'error': str(exc)}
