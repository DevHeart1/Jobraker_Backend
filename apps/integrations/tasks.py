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
        
        # Generate embeddings
        embeddings = embedding_service.generate_job_embeddings(job)
        
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
        
        # Generate embeddings
        embeddings = embedding_service.generate_user_profile_embeddings(user.profile)
        
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
        
        # Prepare user profile text
        profile = user.profile
        user_profile_text = f"""
        Name: {user.get_full_name()}
        Current Title: {profile.current_title or 'Not specified'}
        Experience Level: {profile.get_experience_level_display()}
        Skills: {', '.join(profile.skills) if profile.skills else 'None listed'}
        Location: {profile.location or 'Not specified'}
        """
        
        # Analyze match
        analysis = client.analyze_job_match(
            job_description=job.description,
            user_profile=user_profile_text,
            user_skills=profile.skills or [],
        )
        
        logger.info(f"Generated job match analysis for user {user_id} and job {job_id}")
        return {
            'status': 'success',
            'user_id': str(user_id),
            'job_id': str(job_id),
            'analysis': analysis,
        }
        
    except (User.DoesNotExist, Job.DoesNotExist) as e:
        logger.error(f"User or job not found: {e}")
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
        
        # Generate cover letter
        cover_letter = client.generate_cover_letter(
            job_title=job.title,
            company_name=job.company,
            job_description=job.description,
            user_profile=user_profile_text,
            user_name=user.get_full_name(),
            template=template,
        )
        
        logger.info(f"Generated cover letter for user {user_id} and job {job_id}")
        return {
            'status': 'success',
            'user_id': str(user_id),
            'job_id': str(job_id),
            'cover_letter': cover_letter,
        }
        
    except (User.DoesNotExist, Job.DoesNotExist) as e:
        logger.error(f"User or job not found: {e}")
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
