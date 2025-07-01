"""
Celery tasks for integration services.
"""

from celery import shared_task
from typing import Dict, Any, Optional, List
from django.utils import timezone
from django.contrib.auth import get_user_model
import logging
import time
from prometheus_client import Counter, Histogram

logger = logging.getLogger(__name__)
User = get_user_model()

# Prometheus metrics
OPENAI_API_CALLS_TOTAL = Counter(
    'jobraker_openai_api_calls_total',
    'Total calls made to OpenAI API.',
    ['type', 'model', 'status']
)

OPENAI_API_CALL_DURATION_SECONDS = Histogram(
    'jobraker_openai_api_call_duration_seconds',
    'Latency of OpenAI API calls.',
    ['type', 'model']
)

OPENAI_MODERATION_CHECKS_TOTAL = Counter(
    'jobraker_openai_moderation_checks_total',
    'Total moderation checks performed.',
    ['target']
)

OPENAI_MODERATION_FLAGGED_TOTAL = Counter(
    'jobraker_openai_moderation_flagged_total',
    'Total times content was flagged by moderation.',
    ['target']
)

SKYVERN_APPLICATION_SUBMISSIONS_TOTAL = Counter(
    'jobraker_skyvern_application_submissions_total',
    'Total job applications submitted via Skyvern.',
    ['status']
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
        from apps.integrations.services.openai import EmbeddingService
        from apps.common.services import VectorDBService
        
        job = Job.objects.get(id=job_id)
        embedding_service = EmbeddingService()
        vector_db_service = VectorDBService()
        model_name = embedding_service.embedding_model

        # Generate and Save Embeddings to Job Model
        job_model_embedding_status = 'error'
        job_embeddings_dict = None
        try:
            emb_start_time = time.monotonic()
            job_embeddings_dict = embedding_service.generate_job_embeddings(job)
            job_model_embedding_status = 'success' if job_embeddings_dict else 'no_embeddings_generated'
        except Exception as e:
            logger.error(f"EmbeddingService call failed in generate_job_embeddings_and_ingest_for_rag for job {job_id}: {e}")
            raise
        finally:
            emb_duration = time.monotonic() - emb_start_time
            OPENAI_API_CALL_DURATION_SECONDS.labels(type='embedding_job', model=model_name).observe(emb_duration)
            OPENAI_API_CALLS_TOTAL.labels(type='embedding_job', model=model_name, status=job_model_embedding_status).inc()

        rag_ingested_successfully = False
        if job_embeddings_dict and 'combined_embedding' in job_embeddings_dict:
            if 'title_embedding' in job_embeddings_dict:
                job.title_embedding = job_embeddings_dict['title_embedding']
            job.combined_embedding = job_embeddings_dict['combined_embedding']
            
            try:
                job.save(update_fields=['title_embedding', 'combined_embedding'])
                logger.info(f"Saved embeddings to Job model for job_id: {job_id}")
            except Exception as e:
                logger.error(f"Failed to save embeddings to Job model {job_id}: {e}")

            # Ingest Job Content into RAG Vector Store
            rag_text_content = (
                f"Job Title: {job.title or 'N/A'}\n"
                f"Company: {job.company or 'N/A'}\n"
                f"Location: {job.location or 'N/A'}\n"
                f"Type: {job.get_job_type_display() or 'N/A'}\n"
                f"Description: {job.description or 'N/A'}"
            )
            
            if job.salary_min and job.salary_max:
                rag_text_content += f"\nSalary Range: ${job.salary_min} - ${job.salary_max}"
            elif job.salary_min:
                rag_text_content += f"\nSalary Min: ${job.salary_min}"

            metadata_for_rag = {
                'job_id_original': str(job.id),
                'company': job.company,
                'location': job.location,
                'posted_date': str(job.posted_date.isoformat() if job.posted_date else None),
                'job_type': job.job_type,
                'title': job.title,
            }

            # Delete existing RAG document for this job_id
            vector_db_service.delete_documents(source_type='job_listing', source_id=str(job.id))

            add_status = vector_db_service.add_documents(
                texts=[rag_text_content],
                embeddings=[job_embeddings_dict['combined_embedding']],
                source_types=['job_listing'],
                source_ids=[str(job.id)],
                metadatas=[metadata_for_rag]
            )
            
            if add_status:
                rag_ingested_successfully = True
                logger.info(f"Successfully added/updated job {job.id} in RAG vector store.")
            else:
                logger.error(f"Failed to add/update job {job.id} in RAG vector store.")

            return {
                'status': 'success', 
                'job_id': str(job_id), 
                'embeddings_saved_to_job': True, 
                'rag_ingested': rag_ingested_successfully
            }

        else:
            logger.warning(f"No embeddings generated for job: {job.title}, RAG ingestion skipped.")
            return {
                'status': 'no_embeddings', 
                'job_id': str(job_id), 
                'embeddings_saved_to_job': False, 
                'rag_ingested': False
            }
            
    except Job.DoesNotExist:
        logger.error(f"Job not found: {job_id}")
        return {'status': 'job_not_found', 'job_id': str(job_id)}
    except Exception as exc:
        logger.error(f"Error in generate_job_embeddings_and_ingest_for_rag for job {job_id}: {exc}")
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
            embeddings = embedding_service.generate_user_profile_embeddings(user.profile)
            status = 'success' if embeddings else 'no_embeddings_generated'
        except Exception as e:
            logger.error(f"EmbeddingService call failed in generate_user_profile_embeddings for user {user_id}: {e}")
            raise
        finally:
            duration = time.monotonic() - start_time
            OPENAI_API_CALL_DURATION_SECONDS.labels(type='embedding_profile', model=model_name).observe(duration)
            OPENAI_API_CALLS_TOTAL.labels(type='embedding_profile', model=model_name, status=status).inc()

        if embeddings:
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
        model_name = client.model
        
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
            raise
        finally:
            duration = time.monotonic() - start_time
            OPENAI_API_CALL_DURATION_SECONDS.labels(type='job_match_analysis', model=model_name).observe(duration)
            OPENAI_API_CALLS_TOTAL.labels(type='job_match_analysis', model=model_name, status=api_status).inc()

        if analysis:
            logger.info(f"Generated job match analysis for user {user_id} and job {job_id}")
            return {
                'status': 'success',
                'user_id': str(user_id),
                'job_id': str(job_id),
                'analysis': analysis,
            }
        else:
            logger.warning(f"No analysis content from OpenAIClient for user {user_id}, job {job_id}")
            return {'status': 'no_analysis_content', 'user_id': str(user_id), 'job_id': str(job_id)}
        
    except (User.DoesNotExist, Job.DoesNotExist) as e:
        logger.error(f"User or job not found: {e}")
        OPENAI_API_CALLS_TOTAL.labels(type='job_match_analysis', model='N/A', status='prereq_not_found').inc()
        return {'status': 'not_found', 'error': str(e)}
    except Exception as exc:
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
        model_name = client.model

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
            raise
        finally:
            duration = time.monotonic() - start_time
            OPENAI_API_CALL_DURATION_SECONDS.labels(type='cover_letter_generation', model=model_name).observe(duration)
            OPENAI_API_CALLS_TOTAL.labels(type='cover_letter_generation', model=model_name, status=api_status).inc()

        if cover_letter:
            logger.info(f"Generated cover letter for user {user_id} and job {job_id}")
            return {
                'status': 'success',
                'user_id': str(user_id),
                'job_id': str(job_id),
                'cover_letter': cover_letter,
            }
        else:
            logger.warning(f"No cover letter content from OpenAIClient for user {user_id}, job {job_id}")
            return {'status': 'no_letter_content', 'user_id': str(user_id), 'job_id': str(job_id)}
        
    except (User.DoesNotExist, Job.DoesNotExist) as e:
        logger.error(f"User or job not found: {e}")
        OPENAI_API_CALLS_TOTAL.labels(type='cover_letter_generation', model='N/A', status='prereq_not_found').inc()
        return {'status': 'not_found', 'error': str(e)}
    except Exception as exc:
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


@shared_task(bind=True, max_retries=2)
def get_openai_job_advice_task(self, user_id: int, advice_type: str, context: str = "", user_profile_data: dict = None, query_for_rag: str = None):
    """Celery task to get job advice from OpenAI with RAG support."""
    try:
        from django.conf import settings
        import openai
        
        api_key = getattr(settings, 'OPENAI_API_KEY', '')
        model = getattr(settings, 'OPENAI_MODEL', 'gpt-4o-mini')

        # RAG Implementation
        rag_context_str = ""
        text_for_rag_embedding = query_for_rag if query_for_rag else context
        if text_for_rag_embedding:
            try:
                from apps.integrations.services.openai import EmbeddingService
                from apps.common.services import VectorDBService

                embedding_service = EmbeddingService()
                vdb_service = VectorDBService()

                query_embedding_list = embedding_service.generate_embeddings([text_for_rag_embedding])
                if query_embedding_list and query_embedding_list[0]:
                    query_embedding = query_embedding_list[0]

                    rag_filter = None
                    if advice_type == "salary":
                        rag_filter = {'source_type__in': ['job_listing', 'salary_data_article']}
                    elif advice_type in ["resume", "interview", "application", "skills", "networking"]:
                        rag_filter = {'source_type__in': ['career_article', 'faq_item']}

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
                                f"Source ID: {doc.get('source_id', 'N/A')}, "
                                f"Similarity: {doc.get('similarity_score', 0.0):.3f}):"
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

        # Build prompt
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
            response = openai.chat.completions.create(
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
            raise
        finally:
            duration = time.monotonic() - start_time
            OPENAI_API_CALL_DURATION_SECONDS.labels(type='advice', model=model).observe(duration)
            OPENAI_API_CALLS_TOTAL.labels(type='advice', model=model, status=status).inc()

    except Exception as exc:
        logger.error(f"Error in get_openai_job_advice_task for user {user_id}: {exc}")
        raise self.retry(exc=exc, countdown=30 * (2 ** self.request.retries))


@shared_task(bind=True, max_retries=2)
def get_openai_chat_response_task(self, user_id: int, session_id: int, message: str, conversation_history: list = None, user_profile_data: dict = None):
    """Celery task for OpenAIJobAssistant chat responses. Includes core logic and saves AI message."""
    try:
        from django.conf import settings
        from openai import OpenAI as OpenAI_API
        import json
        from apps.chat.models import ChatSession, ChatMessage

        api_key = getattr(settings, 'OPENAI_API_KEY', '')
        if not api_key:
            logger.warning(f"OpenAI API key not configured for task: get_openai_chat_response_task for user {user_id}, session {session_id}")
            return {'response': "OpenAI API key not configured.", 'model_used': 'config_error', 'success': False, 'error': 'api_key_missing'}

        client = OpenAI_API(api_key=api_key)
        model = getattr(settings, 'OPENAI_MODEL', 'gpt-4')

        # RAG Implementation
        rag_context_str = ""
        if message:
            try:
                from apps.integrations.services.openai import EmbeddingService
                from apps.common.services import VectorDBService

                embedding_service = EmbeddingService()
                vdb_service = VectorDBService()

                query_embedding_list = embedding_service.generate_embeddings([message])
                if query_embedding_list and query_embedding_list[0]:
                    query_embedding = query_embedding_list[0]

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
        mod_response = client.moderations.create(input=message)
        OPENAI_API_CALL_DURATION_SECONDS.labels(type='moderation', model='text-moderation-latest').observe(time.monotonic() - mod_start_time)
        OPENAI_API_CALLS_TOTAL.labels(type='moderation', model='text-moderation-latest', status='success').inc()

        if mod_response.results[0].flagged:
            OPENAI_MODERATION_FLAGGED_TOTAL.labels(target='user_input').inc()
            logger.warning(f"User message flagged in task: get_openai_chat_response_task for user {user_id}, session {session_id}")
            return {'response': "Input violates guidelines.", 'model_used': 'moderation_filter', 'success': False, 'error': 'flagged_input'}

        start_time = time.monotonic()
        api_call_status = 'error'
        ai_response_text = ""
        try:
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
            raise
        finally:
            duration = time.monotonic() - start_time
            OPENAI_API_CALL_DURATION_SECONDS.labels(type='chat', model=model).observe(duration)
            OPENAI_API_CALLS_TOTAL.labels(type='chat', model=model, status=api_call_status).inc()

        # Moderation of AI output (simplified)
        OPENAI_MODERATION_CHECKS_TOTAL.labels(target='ai_output').inc()
        mod_ai_start_time = time.monotonic()
        mod_response_ai = client.moderations.create(input=ai_response_text)
        OPENAI_API_CALL_DURATION_SECONDS.labels(type='moderation', model='text-moderation-latest').observe(time.monotonic() - mod_ai_start_time)
        OPENAI_API_CALLS_TOTAL.labels(type='moderation', model='text-moderation-latest', status='success').inc()

        if mod_response_ai.results[0].flagged:
            OPENAI_MODERATION_FLAGGED_TOTAL.labels(target='ai_output').inc()
            logger.warning(f"AI response flagged in task: get_openai_chat_response_task for user {user_id}, session {session_id}")
            return {'response': "AI output violates content guidelines and was not saved.", 'model_used': 'moderation_filter', 'success': False, 'error': 'flagged_ai_output_not_saved'}

        try:
            chat_session = ChatSession.objects.get(id=session_id)
            ChatMessage.objects.create(
                session=chat_session,
                sender='ai',
                message_text=ai_response_text
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
    except Exception as exc:
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

        # RAG Implementation for Resume Analysis
        rag_context_str = ""
        if target_job:
            try:
                from apps.integrations.services.openai import EmbeddingService
                from apps.common.services import VectorDBService

                embedding_service = EmbeddingService()
                vdb_service = VectorDBService()

                query_embedding_list = embedding_service.generate_embeddings([target_job])

                if query_embedding_list and query_embedding_list[0]:
                    query_embedding = query_embedding_list[0]

                    rag_filter = {'source_type__in': ['career_advice', 'faq_item', 'interview_tips'],
                                  'metadata__category__icontains': 'resume'}

                    logger.info(f"RAG (ResumeAnalysis): Searching documents with filter: {rag_filter}")
                    similar_docs = vdb_service.search_similar_documents(
                        query_embedding=query_embedding,
                        top_n=2,
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

        # Refined prompt building
        prompt_parts = [
            "Please analyze the following resume and provide specific improvement suggestions.",
            f"\nResume Content:\n---\n{resume_text}\n---"
        ]
        if target_job:
            prompt_parts.append(f"\nThe resume is being tailored for the following Target Job (or job type):\n---\n{target_job}\n---")
        if user_profile_data:
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
            raise
        finally:
            duration = time.monotonic() - start_time
            OPENAI_API_CALL_DURATION_SECONDS.labels(type='resume_analysis', model=model).observe(duration)
            OPENAI_API_CALLS_TOTAL.labels(type='resume_analysis', model=model, status=status).inc()

    except Exception as exc:
        logger.error(f"Error in analyze_openai_resume_task: {exc}")
        raise self.retry(exc=exc, countdown=30 * (2 ** self.request.retries))


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
    from apps.jobs.models import Application

    logger.info(f"Starting Skyvern application task for JobRaker app ID: {application_id}, Job URL: {job_url}")

    try:
        application = Application.objects.get(id=application_id)
    except Application.DoesNotExist:
        logger.error(f"Application {application_id} not found in submit_skyvern_application_task.")
        SKYVERN_APPLICATION_SUBMISSIONS_TOTAL.labels(status='application_not_found').inc()
        return {"status": "error", "application_id": application_id, "error": "Application not found"}

    client = SkyvernAPIClient()

    skyvern_inputs = {
        "target_job_url": job_url,
        "user_profile_data": user_profile_data,
    }
    if resume_base64:
        skyvern_inputs["resume_base64"] = resume_base64
    if cover_letter_base64:
        skyvern_inputs["cover_letter_base64"] = cover_letter_base64

    prompt = prompt_template.format(job_url=job_url)

    webhook_url = None

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
            application.status = 'submitting_via_skyvern'
            application.save(update_fields=['skyvern_task_id', 'status', 'updated_at'])

            SKYVERN_APPLICATION_SUBMISSIONS_TOTAL.labels(status='initiated').inc()
            return {"status": "success", "skyvern_task_id": skyvern_task_id, "application_id": application_id}
        else:
            logger.error(f"Skyvern task creation failed for JobRaker app ID: {application_id}. Response: {response}")
            application.status = 'skyvern_submission_failed'
            application.skyvern_response_data = response
            application.save(update_fields=['status', 'skyvern_response_data', 'updated_at'])
            SKYVERN_APPLICATION_SUBMISSIONS_TOTAL.labels(status='creation_failed').inc()
            return {"status": "failure", "application_id": application_id, "error": "Task creation failed", "response": response}

    except Exception as exc:
        logger.error(f"Error in submit_skyvern_application_task for app ID {application_id}: {exc}")
        if 'application' in locals():
            application.status = 'skyvern_submission_failed'
            application.skyvern_response_data = {'error': str(exc)}
            application.save(update_fields=['status', 'skyvern_response_data', 'updated_at'])
        SKYVERN_APPLICATION_SUBMISSIONS_TOTAL.labels(status='task_exception').inc()
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))


@shared_task(bind=True, max_retries=5, default_retry_delay=5 * 60)
def check_skyvern_task_status_task(self, skyvern_task_id: str, application_id: str):
    """
    Checks the status of a Skyvern task and updates the JobRaker application.
    Args:
        skyvern_task_id: The task ID from Skyvern.
        application_id: JobRaker internal application ID for tracking.
    """
    from apps.integrations.services.skyvern import SkyvernAPIClient
    from apps.jobs.models import Application
    from django.utils import timezone

    logger.info(f"Checking Skyvern task status for task_id: {skyvern_task_id}, JobRaker app ID: {application_id}")

    try:
        application = Application.objects.get(id=application_id, skyvern_task_id=skyvern_task_id)
    except Application.DoesNotExist:
        logger.error(f"Application {application_id} with Skyvern task ID {skyvern_task_id} not found in check_skyvern_task_status_task.")
        SKYVERN_APPLICATION_SUBMISSIONS_TOTAL.labels(status='check_app_not_found').inc()
        return {"status": "error", "application_id": application_id, "error": "Application for Skyvern task not found"}

    client = SkyvernAPIClient()

    try:
        status_response = client.get_task_status(skyvern_task_id)

        if not status_response:
            logger.warning(f"Failed to get status for Skyvern task {skyvern_task_id}. Will retry.")
            raise Exception(f"No response from Skyvern for task status {skyvern_task_id}")

        current_skyvern_status = status_response.get("status")
        logger.info(f"Skyvern task {skyvern_task_id} status: {current_skyvern_status}")

        new_jobraker_status = application.status
        skyvern_message = status_response.get("message", "")

        if current_skyvern_status == "COMPLETED":
            new_jobraker_status = 'submitted'
            application.applied_at = timezone.now()
            SKYVERN_APPLICATION_SUBMISSIONS_TOTAL.labels(status='completed_success').inc()
            retrieve_skyvern_task_results_task.delay(skyvern_task_id, application_id)
        elif current_skyvern_status == "FAILED":
            new_jobraker_status = 'skyvern_submission_failed'
            SKYVERN_APPLICATION_SUBMISSIONS_TOTAL.labels(status='failed').inc()
            application.skyvern_response_data = status_response
        elif current_skyvern_status == "CANCELED":
            new_jobraker_status = 'skyvern_canceled'
            SKYVERN_APPLICATION_SUBMISSIONS_TOTAL.labels(status='canceled').inc()
            application.skyvern_response_data = status_response
        elif current_skyvern_status == "REQUIRES_ATTENTION":
            new_jobraker_status = 'skyvern_requires_attention'
            SKYVERN_APPLICATION_SUBMISSIONS_TOTAL.labels(status='requires_attention').inc()
            application.skyvern_response_data = status_response
        elif current_skyvern_status in ["PENDING", "RUNNING"]:
            if application.status not in ['submitting_via_skyvern']:
                 new_jobraker_status = 'submitting_via_skyvern'
            logger.info(f"Skyvern task {skyvern_task_id} is still {current_skyvern_status}.")

        if new_jobraker_status != application.status or application.applied_at:
            application.status = new_jobraker_status
            fields_to_update = ['status', 'updated_at']
            if application.applied_at:
                fields_to_update.append('applied_at')
            if application.skyvern_response_data:
                fields_to_update.append('skyvern_response_data')
            application.save(update_fields=fields_to_update)
            logger.info(f"Updated JobRaker app ID {application_id} status to {new_jobraker_status} for Skyvern task {skyvern_task_id}")

        return {"status": "polled", "skyvern_task_id": skyvern_task_id, "skyvern_status": current_skyvern_status, "application_id": application_id}

    except Exception as exc:
        logger.error(f"Error in check_skyvern_task_status_task for Skyvern task {skyvern_task_id}: {exc}")
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=3)
def retrieve_skyvern_task_results_task(self, skyvern_task_id: str, application_id: str):
    from apps.integrations.services.skyvern import SkyvernAPIClient
    from apps.jobs.models import Application

    logger.info(f"Retrieving results for Skyvern task {skyvern_task_id}, JobRaker app ID: {application_id}")

    try:
        application = Application.objects.get(id=application_id, skyvern_task_id=skyvern_task_id)
    except Application.DoesNotExist:
        logger.error(f"Application {application_id} with Skyvern task ID {skyvern_task_id} not found in retrieve_skyvern_task_results_task.")
        return {"status": "error", "application_id": application_id, "error": "Application for Skyvern task not found"}

    client = SkyvernAPIClient()
    try:
        results_response = client.get_task_results(skyvern_task_id)

        if results_response:
            logger.info(f"Results for Skyvern task {skyvern_task_id}: {results_response}")
            application.skyvern_response_data = results_response

            skyvern_status_in_results = results_response.get("status")
            if skyvern_status_in_results == "FAILED" and application.status != 'skyvern_submission_failed':
                application.status = 'skyvern_submission_failed'
                logger.info(f"Updating application {application_id} status to 'skyvern_submission_failed' based on task results.")

            application.save(update_fields=['skyvern_response_data', 'status', 'updated_at'])
            return {"status": "success", "skyvern_task_id": skyvern_task_id, "application_id": application_id, "results_fetched": True}
        else:
            logger.warning(f"No results data found for Skyvern task {skyvern_task_id} (API call might have returned None or empty).")
            application.skyvern_response_data = {"info": "Results retrieval attempted, no data returned by Skyvern."}
            application.save(update_fields=['skyvern_response_data', 'updated_at'])
            return {"status": "no_results_data", "skyvern_task_id": skyvern_task_id, "application_id": application_id}

    except Exception as exc:
        logger.error(f"Error retrieving results for Skyvern task {skyvern_task_id}: {exc}")
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=3)
def process_knowledge_article_for_rag_task(self, article_id: int):
    """
    Generates embedding for a KnowledgeArticle and ingests/updates it in the RAG vector store.
    Args:
        article_id: ID of the KnowledgeArticle to process.
    """
    try:
        from apps.common.models import KnowledgeArticle
        from apps.integrations.services.openai import EmbeddingService
        from apps.common.services import VectorDBService

        article = KnowledgeArticle.objects.get(id=article_id)

        if not article.is_active:
            logger.info(f"KnowledgeArticle {article_id} is not active. Deleting from RAG store if present.")
            vector_db_service = VectorDBService()
            vector_db_service.delete_documents(source_type=article.source_type, source_id=str(article.id))
            return {'status': 'skipped_inactive_deleted', 'article_id': article_id}

        embedding_service = EmbeddingService()
        vector_db_service = VectorDBService()
        model_name = embedding_service.embedding_model

        text_to_embed = f"Title: {article.title}\nContent: {article.content}"

        embedding_generation_status = 'error'
        article_embedding_list = None
        try:
            emb_start_time = time.monotonic()
            article_embedding_list = embedding_service.generate_embeddings([text_to_embed])
            embedding_generation_status = 'success' if article_embedding_list and article_embedding_list[0] else 'no_embedding_generated'
        except Exception as e:
            logger.error(f"EmbeddingService call failed for KnowledgeArticle {article_id}: {e}")
            raise
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
                'tags': article.get_tags_list(),
                'source_type_display': article.get_source_type_display()
            }

            vector_db_service.delete_documents(source_type=article.source_type, source_id=str(article.id))

            add_status = vector_db_service.add_documents(
                texts=[text_to_embed],
                embeddings=[article_embedding],
                source_types=[article.source_type],
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
    from apps.accounts.models import UserProfile
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
            summary_parts = []
            if user_profile.current_title:
                summary_parts.append(f"Current Title: {user_profile.current_title}")
            if user_profile.experience_level:
                summary_parts.append(f"Experience Level: {user_profile.get_experience_level_display()}")
            if user_profile.skills:
                summary_parts.append(f"Key Skills: {', '.join(user_profile.skills[:5])}")
            if user_profile.bio:
                summary_parts.append(f"Bio Snippet: {user_profile.bio[:200]}...")

            if summary_parts:
                user_profile_summary = ". ".join(summary_parts)
            logger.info(f"User profile summary for personalization: {user_profile_summary}")

        except UserProfile.DoesNotExist:
            logger.warning(f"UserProfile not found for User ID: {user_id}. Proceeding without personalization.")
        except Exception as e:
            logger.error(f"Error fetching or summarizing UserProfile for User ID {user_id}: {e}")
            return {"status": "error", "error": "Error fetching or summarizing UserProfile", "job_id": job_id}

    client = OpenAIClient()
    model_name_client = client.model

    api_call_status = 'error'
    questions = []
    start_time = time.monotonic()

    try:
        questions = client.generate_interview_questions(
            job_title=job.title,
            job_description=job.description,
            user_profile_summary=user_profile_summary
        )
        api_call_status = 'success' if questions else 'no_questions_generated'

        logger.info(f"Generated {len(questions)} interview questions for Job ID: {job_id}. API status: {api_call_status}")

        return {
            "job_id": str(job.id),
            "job_title": job.title,
            "questions": questions,
            "status": api_call_status
        }

    except Exception as e:
        logger.error(f"OpenAIClient call failed in generate_interview_questions_task for Job {job_id}: {e}", exc_info=True)
        raise self.retry(exc=e, countdown=60 * (2 ** self.request.retries))
    finally:
        duration = time.monotonic() - start_time
        OPENAI_API_CALL_DURATION_SECONDS.labels(type='interview_question_generation', model=model_name_client or 'unknown').observe(duration)
        OPENAI_API_CALLS_TOTAL.labels(type='interview_question_generation', model=model_name_client or 'unknown', status=api_call_status).inc()
