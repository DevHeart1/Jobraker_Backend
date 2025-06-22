"""
Celery tasks for integration services.
"""

from celery import shared_task
from django.utils import timezone
from django.contrib.auth import get_user_model
import logging

logger = logging.getLogger(__name__)
User = get_user_model()


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
def generate_job_embeddings(self, job_id):
    """
    Generate AI embeddings for a job posting.
    
    Args:
        job_id: UUID of the job to process
    """
    try:
        from apps.jobs.models import Job
        from apps.integrations.services.openai import EmbeddingService
        
        job = Job.objects.get(id=job_id)
        embedding_service = EmbeddingService()
        model_name = embedding_service.embedding_model # Get model name for labels

        start_time = time.monotonic()
        status = 'error'
        try:
            # Generate embeddings
            embeddings = embedding_service.generate_job_embeddings(job)
            status = 'success' if embeddings else 'no_embeddings_generated' # More specific status
        except Exception as e: # Catch errors from service call itself
            logger.error(f"EmbeddingService call failed in generate_job_embeddings for job {job_id}: {e}")
            raise # Re-raise to trigger Celery retry
        finally:
            duration = time.monotonic() - start_time
            OPENAI_API_CALL_DURATION_SECONDS.labels(type='embedding_job', model=model_name).observe(duration)
            # Status here reflects the outcome of the service call, not necessarily the overall task if db save fails
            OPENAI_API_CALLS_TOTAL.labels(type='embedding_job', model=model_name, status=status).inc()

        if embeddings:
            # Update job with embeddings
            if 'title_embedding' in embeddings:
                job.title_embedding = embeddings['title_embedding']
            if 'combined_embedding' in embeddings:
                job.combined_embedding = embeddings['combined_embedding']
            
            job.save(update_fields=['title_embedding', 'combined_embedding'])
            logger.info(f"Generated embeddings for job: {job.title}")
            return {'status': 'success', 'job_id': str(job_id)}
        else:
            logger.warning(f"No embeddings generated for job: {job.title}")
            return {'status': 'no_embeddings', 'job_id': str(job_id)}
            
    except Job.DoesNotExist:
        logger.error(f"Job not found: {job_id}")
        return {'status': 'job_not_found', 'job_id': str(job_id)}
    except Exception as exc:
        logger.error(f"Error generating embeddings for job {job_id}: {exc}")
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
            # Queue individual embedding task
            generate_job_embeddings.delay(str(job.id))
            processed += 1
        
        logger.info(f"Queued embedding generation for {processed} jobs")
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
        model_name = client.model # Get model name for labels
        
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
        model_name = client.model # Get model name for labels

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
def get_openai_job_advice_task(self, user_id: int, advice_type: str, context: str = "", user_profile_data: dict = None, query_for_rag: str = None):
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
                from apps.integrations.services.openai_service import EmbeddingService
                from apps.common.vector_db_service import VectorDBService # Conceptual

                embedding_service = EmbeddingService()
                vdb_service = VectorDBService()

                query_embedding_list = embedding_service.generate_embeddings([text_for_rag_embedding])
                if query_embedding_list and query_embedding_list[0]:
                    query_embedding = query_embedding_list[0]
                    # Example: Filter RAG search by source_type if relevant to advice_type
                    rag_filter = None
                    if advice_type in ["resume", "interview", "application"]:
                        rag_filter = {'source_type': 'career_article'} # Fetch general advice articles
                    elif advice_type == "salary":
                         rag_filter = {'source_type': 'salary_data_source'} # Hypothetical source type

                    similar_docs = vdb_service.search_similar_documents(query_embedding, top_n=3, filter_criteria=rag_filter)

                    if similar_docs:
                        rag_context_parts = ["Here is some relevant information to consider:"]
                        for doc in similar_docs:
                            rag_context_parts.append(f"- {doc.get('text_content', '')} (Source: {doc.get('source_type', 'N/A')})")
                        rag_context_str = "\n".join(rag_context_parts)
                        logger.info(f"RAG: Successfully retrieved and formatted {len(similar_docs)} documents for advice task.")
                else:
                    logger.warning("RAG: Could not generate query embedding for advice task.")
            except Exception as e:
                logger.error(f"RAG pipeline error in get_openai_job_advice_task: {e}")
        # --- End RAG Implementation ---


                    if similar_docs:
                        rag_context_parts = ["--- Start of Retrieved Information ---"]
                        for i, doc in enumerate(similar_docs):
                            doc_info = f"Document {i+1} (Source: {doc.get('source_type', 'N/A')}, ID: {doc.get('source_id', 'N/A')}):"
                            rag_context_parts.append(f"{doc_info}\n{doc.get('text_content', '')}")
                        rag_context_parts.append("--- End of Retrieved Information ---")
                        rag_context_str = "\n\n".join(rag_context_parts)
                        logger.info(f"RAG: Successfully retrieved and formatted {len(similar_docs)} documents for advice task.")
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
            response = openai.ChatCompletion.create(
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
def get_openai_chat_response_task(self, user_id: int, message: str, conversation_history: list = None, user_profile_data: dict = None):
    """Celery task for OpenAIJobAssistant chat responses. Includes core logic."""
    try:
        from django.conf import settings
        import openai
        import json # For function calling if used directly in task

        api_key = getattr(settings, 'OPENAI_API_KEY', '')
        model = getattr(settings, 'OPENAI_MODEL', 'gpt-4')

        # --- RAG Implementation ---
        rag_context_str = ""
        if message: # Use the user's message for RAG query
            try:
                from apps.integrations.services.openai_service import EmbeddingService
                from apps.common.vector_db_service import VectorDBService # Conceptual

                embedding_service = EmbeddingService()
                vdb_service = VectorDBService()

                query_embedding_list = embedding_service.generate_embeddings([message])
                if query_embedding_list and query_embedding_list[0]:
                    query_embedding = query_embedding_list[0]
                    # Generic search for chat, could be refined with intent detection later
                    similar_docs = vdb_service.search_similar_documents(query_embedding, top_n=3)

                    if similar_docs:
                        rag_context_parts = ["Here is some relevant information to consider:"]
                        for doc in similar_docs:
                            rag_context_parts.append(f"- {doc.get('text_content', '')} (Source: {doc.get('source_type', 'N/A')})")
                        rag_context_str = "\n".join(rag_context_parts)
                        logger.info(f"RAG: Successfully retrieved and formatted {len(similar_docs)} documents for chat task.")
                else:
                    logger.warning("RAG: Could not generate query embedding for chat task.")
            except Exception as e:
                logger.error(f"RAG pipeline error in get_openai_chat_response_task: {e}")
        # --- End RAG Implementation ---


                    if similar_docs:
                        rag_context_parts = ["--- Start of Retrieved Context ---"]
                        for i, doc in enumerate(similar_docs):
                            doc_info = f"Context Item {i+1} (Source: {doc.get('source_type', 'N/A')}, ID: {doc.get('source_id', 'N/A')}):"
                            rag_context_parts.append(f"{doc_info}\n{doc.get('text_content', '')}")
                        rag_context_parts.append("--- End of Retrieved Context ---")
                        rag_context_str = "\n\n".join(rag_context_parts)
                        logger.info(f"RAG: Successfully retrieved and formatted {len(similar_docs)} documents for chat task.")
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
        mod_response = openai.Moderation.create(input=message)
        OPENAI_API_CALL_DURATION_SECONDS.labels(type='moderation', model='text-moderation-latest').observe(time.monotonic() - mod_start_time)
        OPENAI_API_CALLS_TOTAL.labels(type='moderation', model='text-moderation-latest', status='success').inc() # Assuming mod call itself succeeds

        if mod_response.results[0].flagged:
            OPENAI_MODERATION_FLAGGED_TOTAL.labels(target='user_input').inc()
            logger.warning(f"User message flagged in task: get_openai_chat_response_task for user {user_id}")
            return {'response': "Input violates guidelines.", 'model_used': 'moderation_filter', 'success': False, 'error': 'flagged_input'}

        openai.api_key = api_key

        start_time = time.monotonic()
        status = 'error'
        try:
            # Simplified: Not including function calling logic directly in task for this refactor stage to keep it focused.
            response = openai.ChatCompletion.create(
                model=model,
                messages=messages_payload,
                max_tokens=800,
                temperature=0.7
            )
            ai_response = response.choices[0].message.content.strip()
            status = 'success'
        except Exception as e:
            logger.error(f"OpenAI API call failed in get_openai_chat_response_task: {e}")
            raise # Re-raise to trigger Celery retry
        finally:
            duration = time.monotonic() - start_time
            OPENAI_API_CALL_DURATION_SECONDS.labels(type='chat', model=model).observe(duration)
            OPENAI_API_CALLS_TOTAL.labels(type='chat', model=model, status=status).inc()


        # Moderation of AI output (simplified)
        OPENAI_MODERATION_CHECKS_TOTAL.labels(target='ai_output').inc()
        mod_ai_start_time = time.monotonic()
        mod_response_ai = openai.Moderation.create(input=ai_response)
        OPENAI_API_CALL_DURATION_SECONDS.labels(type='moderation', model='text-moderation-latest').observe(time.monotonic() - mod_ai_start_time)
        OPENAI_API_CALLS_TOTAL.labels(type='moderation', model='text-moderation-latest', status='success').inc()

        if mod_response_ai.results[0].flagged:
            OPENAI_MODERATION_FLAGGED_TOTAL.labels(target='ai_output').inc()
            logger.warning(f"AI response flagged in task: get_openai_chat_response_task for user {user_id}")
            return {'response': "Output violates guidelines.", 'model_used': 'moderation_filter', 'success': False, 'error': 'flagged_output'}

        return {
            'response': ai_response,
            'model_used': model,
            'success': True
        }
    except Exception as exc: # Outer try-except for Celery retry logic
        logger.error(f"Error in get_openai_chat_response_task for user {user_id}: {exc}")
        raise self.retry(exc=exc, countdown=30 * (2 ** self.request.retries))


@shared_task(bind=True, max_retries=2)
def analyze_openai_resume_task(self, resume_text: str, target_job: str = "", user_profile_data: dict = None):
    """Celery task for OpenAIJobAssistant resume analysis. Includes core logic."""
    try:
        from django.conf import settings
        import openai

        api_key = getattr(settings, 'OPENAI_API_KEY', '')
        model = getattr(settings, 'OPENAI_MODEL', 'gpt-4')

        # Simplified prompt building
        prompt = f"Analyze this resume: {resume_text[:200]}... for target job: {target_job}."
        if user_profile_data:
             prompt += f"\nUser profile context: {user_profile_data.get('experience_level', 'N/A')}"


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

# --- Prometheus Metrics for OpenAI Tasks ---
from prometheus_client import Counter, Histogram
import time

OPENAI_API_CALLS_TOTAL = Counter(
    'jobraker_openai_api_calls_total',
    'Total calls made to OpenAI API.',
    ['type', 'model', 'status'] # type: chat, advice, resume_analysis, embedding, moderation
)

OPENAI_API_CALL_DURATION_SECONDS = Histogram(
    'jobraker_openai_api_call_duration_seconds',
    'Latency of OpenAI API calls.',
    ['type', 'model']
)

OPENAI_MODERATION_CHECKS_TOTAL = Counter(
    'jobraker_openai_moderation_checks_total',
    'Total moderation checks performed.',
    ['target'] # target: user_input, ai_output
)

OPENAI_MODERATION_FLAGGED_TOTAL = Counter(
    'jobraker_openai_moderation_flagged_total',
    'Total times content was flagged by moderation.',
    ['target']
)

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
    # from apps.jobs.models import Application # To update application status

    logger.info(f"Starting Skyvern application task for JobRaker app ID: {application_id}, Job URL: {job_url}")
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
            # Update JobRaker Application model with skyvern_task_id and set status to 'PENDING_SKYVERN'
            # Example:
            # Application.objects.filter(id=application_id).update(
            #     skyvern_task_id=skyvern_task_id,
            #     status='pending_skyvern_submission' # Example status
            # )
            SKYVERN_APPLICATION_SUBMISSIONS_TOTAL.labels(status='initiated').inc()
            return {"status": "success", "skyvern_task_id": skyvern_task_id, "application_id": application_id}
        else:
            logger.error(f"Skyvern task creation failed for JobRaker app ID: {application_id}. Response: {response}")
            # Application.objects.filter(id=application_id).update(status='skyvern_submission_failed')
            SKYVERN_APPLICATION_SUBMISSIONS_TOTAL.labels(status='creation_failed').inc()
            return {"status": "failure", "application_id": application_id, "error": "Task creation failed", "response": response}

    except Exception as exc:
        logger.error(f"Error in submit_skyvern_application_task for app ID {application_id}: {exc}")
        # Application.objects.filter(id=application_id).update(status='skyvern_submission_error')
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
    # from apps.jobs.models import Application # To update application status

    logger.info(f"Checking Skyvern task status for task_id: {skyvern_task_id}, JobRaker app ID: {application_id}")
    client = SkyvernAPIClient()

    try:
        status_response = client.get_task_status(skyvern_task_id)

        if not status_response:
            logger.warning(f"Failed to get status for Skyvern task {skyvern_task_id}. Will retry.")
            # No status update, rely on retry
            raise Exception(f"No response from Skyvern for task status {skyvern_task_id}")

        current_skyvern_status = status_response.get("status")
        logger.info(f"Skyvern task {skyvern_task_id} status: {current_skyvern_status}")

        # Determine JobRaker application status based on Skyvern status
        # new_jobraker_status = None
        # if current_skyvern_status == "COMPLETED":
        #     new_jobraker_status = 'applied_via_skyvern' # Example
        #     SKYVERN_APPLICATION_SUBMISSIONS_TOTAL.labels(status='completed_success').inc()
        #     # Optionally, trigger results fetching task or do it here if response is small
        #     # retrieve_skyvern_task_results_task.delay(skyvern_task_id, application_id)
        # elif current_skyvern_status == "FAILED":
        #     new_jobraker_status = 'skyvern_application_failed' # Example
        #     SKYVERN_APPLICATION_SUBMISSIONS_TOTAL.labels(status='failed').inc()
        # elif current_skyvern_status in ["PENDING", "RUNNING"]:
        #     # Task is still ongoing, schedule another check if not using webhooks
        #     logger.info(f"Skyvern task {skyvern_task_id} is still {current_skyvern_status}. Will re-check if polled.")
        #     # self.retry(countdown=15 * 60) # Retry after 15 mins if still pending/running
        #     return {"status": "pending_skyvern", "skyvern_task_id": skyvern_task_id, "application_id": application_id}
        # else: # CANCELED, REQUIRES_ATTENTION, or other unknown statuses
        #     new_jobraker_status = 'skyvern_attention_needed' # Example
        #     SKYVERN_APPLICATION_SUBMISSIONS_TOTAL.labels(status=str(current_skyvern_status).lower()).inc()

        # if new_jobraker_status:
        #     Application.objects.filter(id=application_id).update(status=new_jobraker_status)
        #     logger.info(f"Updated JobRaker app ID {application_id} status to {new_jobraker_status} based on Skyvern task {skyvern_task_id}")

        # For now, just returning the Skyvern status. DB update logic is commented out.
        return {"status": "polled", "skyvern_task_id": skyvern_task_id, "skyvern_status": current_skyvern_status, "application_id": application_id}

    except Exception as exc:
        logger.error(f"Error in check_skyvern_task_status_task for Skyvern task {skyvern_task_id}: {exc}")
        raise self.retry(exc=exc) # Celery will use default_retry_delay


# Placeholder for task to retrieve results, can be called after status is COMPLETED
@shared_task(bind=True, max_retries=3)
def retrieve_skyvern_task_results_task(self, skyvern_task_id: str, application_id: str):
    from apps.integrations.services.skyvern import SkyvernAPIClient
    # from apps.jobs.models import Application # To store results

    logger.info(f"Retrieving results for Skyvern task {skyvern_task_id}, JobRaker app ID: {application_id}")
    client = SkyvernAPIClient()
    try:
        results_response = client.get_task_results(skyvern_task_id)
        if results_response:
            # Process and store results_response.get('data') or results_response.get('error_details')
            # For example, store confirmation ID or error messages in Application model
            logger.info(f"Results for Skyvern task {skyvern_task_id}: {results_response}")
            # Application.objects.filter(id=application_id).update(skyvern_results=results_response)
            return {"status": "success", "skyvern_task_id": skyvern_task_id, "results": results_response}
        else:
            logger.warning(f"No results found for Skyvern task {skyvern_task_id} (or API call failed).")
            return {"status": "no_results", "skyvern_task_id": skyvern_task_id}
    except Exception as exc:
        logger.error(f"Error retrieving results for Skyvern task {skyvern_task_id}: {exc}")
        raise self.retry(exc=exc)
