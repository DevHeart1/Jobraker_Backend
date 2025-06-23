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


@shared_task(bind=True, max_retries=3)
def process_job_alerts_task(self):
    """
    Processes all active job alerts, finds matching new jobs,
    and triggers notifications for users.
    """
    from apps.jobs.models import Job, JobAlert
    from django.db.models import Q
    from django.utils import timezone

    active_alerts = JobAlert.objects.filter(is_active=True)
    if not active_alerts.exists():
        logger.info("No active job alerts to process.")
        return {"status": "no_active_alerts", "processed_alerts": 0}

    alerts_processed_count = 0
    notifications_sent_count = 0
    alerts_skipped_due_to_frequency = 0

    for alert in active_alerts:
        # Check if alert is due based on its frequency
        now = timezone.now()
        should_process = False
        if not alert.last_run: # Never run before
            should_process = True
        else:
            # Accessing frequency string values directly
            if alert.frequency == 'daily':
                should_process = (now - alert.last_run) >= timezone.timedelta(days=1)
            elif alert.frequency == 'weekly':
                should_process = (now - alert.last_run) >= timezone.timedelta(weeks=1)
            elif alert.frequency == 'monthly':
                should_process = (now - alert.last_run) >= timezone.timedelta(days=30) # Approximation
            elif alert.frequency == 'immediate':
                # For a batch task like this, 'immediate' is tricky.
                # It might mean process every time the task runs if new jobs exist.
                # Or, 'immediate' alerts are handled by a different, more frequent task or signals.
                # For this batch task, let's assume 'immediate' means it's always due if new jobs exist.
                should_process = True
                # Consider if 'immediate' alerts should even be processed by this batch job,
                # or if they warrant a separate, more frequent mechanism (e.g., signal-based on Job creation).
                # For now, including it here means it gets checked every time this batch task runs.

        if not should_process:
            alerts_skipped_due_to_frequency +=1
            logger.debug(f"Skipping alert ID: {alert.id} for user: {alert.user.id} due to frequency. Last run: {alert.last_run}, Freq: {alert.frequency}")
            continue

        logger.info(f"Processing job alert ID: {alert.id} for user: {alert.user.id} (Frequency: {alert.frequency}, Last run: {alert.last_run})")
        alerts_processed_count += 1

        job_filters = Q()

        # Time filter: only new jobs since last run, or in last 24h if no last_run
        if alert.last_run:
            job_filters &= Q(created_at__gt=alert.last_run) # Or use job.posted_date
        else:
            # For the very first run of an alert, look back a reasonable period, e.g., 1 day.
            job_filters &= Q(created_at__gte=timezone.now() - timezone.timedelta(days=1))

        # Keyword filter (search in title and description)
        if alert.keywords:
            keyword_query = Q()
            for kw in alert.keywords: # Assuming alert.keywords is a list of strings
                keyword_query |= Q(title__icontains=kw) | Q(description__icontains=kw)
            if keyword_query: # Only add if there were keywords
                job_filters &= keyword_query

        # Location filter
        if alert.location:
            job_filters &= Q(location__icontains=alert.location)

        # Job type filter
        if alert.job_type:
            job_filters &= Q(job_type=alert.job_type)

        # Experience level filter
        if alert.experience_level:
            job_filters &= Q(experience_level=alert.experience_level)

        # Remote only filter
        if alert.remote_only:
            job_filters &= Q(is_remote=True)

        # Min salary filter
        if alert.min_salary is not None: # Check for None as 0 is a valid salary
            job_filters &= Q(salary_min__gte=alert.min_salary) | Q(salary_max__gte=alert.min_salary) # Job's max can meet user's min

        # --- Find matching jobs ---
        try:
            matching_jobs = Job.objects.filter(job_filters, status='active').distinct()

            if not matching_jobs.exists():
                logger.info(f"No new matching jobs found for alert ID: {alert.id}")

            for job in matching_jobs:
                # --- Prevent Duplicate Notifications (Conceptual/Placeholder) ---
                # In a real system, you'd check if this user has already been notified for this job via this alert.
                # Example: if NotifiedAlertMatch.objects.filter(user=alert.user, job=job, job_alert=alert).exists():
                # continue
                # For now, we assume each found job is a new notification.
                # --- End Conceptual Duplicate Prevention ---

                logger.info(f"MATCH FOUND: Alert ID {alert.id} for user {alert.user.id} matched Job ID {job.id} ('{job.title}')")

                # --- Trigger Notification (Conceptual) ---
                # This would typically involve creating a Notification object in the DB
                # and/or queuing another task to send email/push.
                # from apps.notifications.services import NotificationService # Example
                # NotificationService.create_notification(
                # user=alert.user,
                # message_type='job_alert',
                # content=f"New job matching your alert '{alert.name}': {job.title} at {job.company}",
                # related_object=job
                # )
                # logger.info(f"  -> Conceptual notification triggered for user {alert.user.id}, job {job.id}, alert '{alert.name}'.")
                # notifications_sent_count += 1 # This will be counted per email sent now
                # --- End Conceptual Notification Trigger ---
                pass # Placeholder if no specific action per job other than collecting them

            if matching_jobs.exists():
                # Prepare and send one email with all matching jobs for this alert
                try:
                    from django.core.mail import send_mail
                    from django.conf import settings
                    from django.urls import reverse # To build absolute URLs if needed

                    subject = f"New Job Matches for Your Alert: {alert.name or 'Unnamed Alert'}"

                    message_lines = [f"Hello {alert.user.first_name or alert.user.username},",
                                     "\nWe found new jobs matching your alert criteria:\n"]

                    for job in matching_jobs:
                        # Assuming you have a way to get the absolute URL for a job
                        # For example, if Job model has get_absolute_url or you construct it
                        job_url = settings.SITE_URL + reverse('job-detail', kwargs={'pk': job.pk}) if hasattr(settings, 'SITE_URL') else f"/jobs/{job.pk}/" # Fallback relative URL
                        message_lines.append(f"- {job.title} at {job.company} ({job.location})")
                        message_lines.append(f"  View: {job_url}\n")

                    message_lines.append("\nYou can manage your alerts here: [Link to Manage Alerts Page]") # Placeholder for actual link

                    plain_message = "\n".join(message_lines)
                    # html_message = ... # Optionally create an HTML version

                    if alert.user.email and alert.email_notifications: # Check if user wants email notifications
                        send_mail(
                            subject,
                            plain_message,
                            settings.DEFAULT_FROM_EMAIL, # Ensure this is configured
                            [alert.user.email],
                            # html_message=html_message, # Optional
                            fail_silently=False,
                        )
                        logger.info(f"Sent job alert email to {alert.user.email} for alert ID: {alert.id} with {matching_jobs.count()} jobs.")
                        notifications_sent_count += 1
                    else:
                        logger.info(f"User {alert.user.email} has email notifications disabled for alert ID: {alert.id} or no email.")

                except Exception as mail_exc:
                    logger.error(f"Failed to send email for alert ID {alert.id} to {alert.user.email}: {mail_exc}")

            # Update last_run timestamp for the alert, regardless of whether email was sent, to prevent re-processing same jobs
            alert.last_run = timezone.now()
            alert.save(update_fields=['last_run'])
            # alerts_processed_count was incremented when we started processing this alert

        except Exception as e:
            logger.error(f"Error processing jobs for alert ID {alert.id}: {e}")
            # Continue to next alert, or re-raise if critical

    logger.info(
        f"Finished processing job alerts. "
        f"Total active alerts considered: {active_alerts.count()}. "
        f"Skipped due to frequency: {alerts_skipped_due_to_frequency}. "
        f"Actually processed: {alerts_processed_count} alerts. "
        f"Email notifications sent: {notifications_sent_count}."
    )
    return {
        "status": "completed",
        "total_active_alerts": active_alerts.count(),
        "alerts_skipped_frequency": alerts_skipped_due_to_frequency,
        "alerts_processed": alerts_processed_count,
        "notifications_sent": notifications_sent_count
    }
