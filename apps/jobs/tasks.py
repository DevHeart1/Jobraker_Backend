from celery import shared_task
import logging
# from django.contrib.auth import get_user_model # User = get_user_model()
from apps.accounts.models import UserProfile # Assuming UserProfile is in accounts.models
from apps.jobs.services import JobMatchService # Or JobRecommendationService if created separately

logger = logging.getLogger(__name__)

@shared_task(bind=True, max_retries=3)
def generate_recommendations_for_single_user_task(self, user_profile_id: Any):
    """
    Celery task to generate job recommendations for a single user.
    Args:
        user_profile_id: The ID of the UserProfile for whom to generate recommendations.
    """
    logger.info(f"Starting recommendation generation for UserProfile ID: {user_profile_id}")
    try:
        # Assuming JobMatchService now contains generate_recommendations_for_user
        # If it were a separate JobRecommendationService, instantiate that instead.
        service = JobMatchService()
        recommendations = service.generate_recommendations_for_user(user_profile_id=user_profile_id)

        if recommendations:
            logger.info(f"Successfully generated {len(recommendations)} recommendations for UserProfile ID: {user_profile_id}")
            return {"status": "success", "user_profile_id": user_profile_id, "recommendations_count": len(recommendations)}
        else:
            logger.info(f"No new recommendations generated for UserProfile ID: {user_profile_id}")
            return {"status": "no_new_recommendations", "user_profile_id": user_profile_id, "recommendations_count": 0}

    except Exception as exc:
        logger.error(f"Error generating recommendations for UserProfile ID {user_profile_id}: {exc}")
        # Retry with exponential backoff
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))


@shared_task(bind=True, max_retries=1) # Batch task, maybe fewer retries or longer delay
def batch_generate_recommendations_for_active_users_task(self):
    """
    Celery task to batch generate job recommendations for all active users
    who have opted-in for recommendations (if such a flag exists).
    """
    logger.info("Starting batch generation of recommendations for active users.")

    # Fetch active UserProfiles.
    # Define what "active" means, e.g., recently logged in, or has an active subscription,
    # or has a flag `receive_recommendations=True` on UserProfile.
    # For this example, let's assume all UserProfiles are candidates.
    # In a real system, you'd filter this list.
    active_user_profiles = UserProfile.objects.filter(user__is_active=True) # Example filter

    if not active_user_profiles.exists():
        logger.info("No active user profiles found for batch recommendation generation.")
        return {"status": "no_active_users", "processed_count": 0}

    processed_count = 0
    queued_count = 0
    for profile in active_user_profiles:
        try:
            generate_recommendations_for_single_user_task.delay(profile.id)
            queued_count += 1
        except Exception as e:
            logger.error(f"Failed to queue recommendation task for UserProfile ID {profile.id}: {e}")
        processed_count +=1 # Counts profiles attempted to queue for

    logger.info(f"Batch recommendations: Attempted to queue for {processed_count} users. Successfully queued: {queued_count} tasks.")
    return {"status": "batch_queued", "total_profiles_considered": processed_count, "tasks_queued": queued_count}
