from celery import shared_task
import logging
# from django.contrib.auth import get_user_model # User = get_user_model()
from apps.accounts.models import UserProfile # Assuming UserProfile is in accounts.models
from apps.jobs.services import JobMatchService # Or JobRecommendationService if created separately
from django.contrib.auth import get_user_model
from django.db.models import Q
from django.utils import timezone
from typing import Dict, List, Any, Optional
from apps.common.services import EmailService

logger = logging.getLogger(__name__)
User = get_user_model()

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


@shared_task(bind=True, max_retries=3)
def send_application_follow_up_reminders(self):
    """
    Sends follow-up reminders for job applications.

    Checks for applications where the 'follow_up_date' is today or in the past
    and a reminder has not yet been sent for that specific follow_up_date.
    """
    from apps.jobs.models import Application
    from django.utils import timezone
    from django.conf import settings
    from django.core.mail import send_mail
    from django.db.models import Q, F

    today = timezone.now().date()
    reminders_sent_count = 0
    applications_processed_count = 0

    # Query for applications needing a reminder:
    # - User is active
    # - follow_up_date is set and is today or in the past
    # - EITHER follow_up_reminder_sent_at is null (never sent for this follow_up_date)
    # - OR follow_up_reminder_sent_at is older than the current follow_up_date
    #   (meaning follow_up_date was changed after last reminder was sent, so a new reminder is due for the new date)
    applications_to_remind = Application.objects.filter(
        user__is_active=True,
        follow_up_date__isnull=False,
        follow_up_date__lte=today
    ).filter(
        Q(follow_up_reminder_sent_at__isnull=True) |
        Q(follow_up_reminder_sent_at__lt=F('follow_up_date'))
    ).select_related('user', 'job')

    if not applications_to_remind.exists():
        logger.info("No applications found requiring follow-up reminders at this time.")
        return {"status": "no_reminders_due", "sent_count": 0}

    logger.info(f"Found {applications_to_remind.count()} applications for potential follow-up reminders.")

    for app in applications_to_remind:
        applications_processed_count += 1
        if not app.user.email:
            logger.warning(f"User {app.user.id} for Application {app.id} has no email. Skipping reminder.")
            continue

        try:
            subject = f"Reminder: Follow up on your application for '{app.job.title}'"
            message = (
                f"Hello {app.user.first_name or app.user.username},\n\n"
                f"This is a reminder to follow up on your job application for the position of "
                f"'{app.job.title}' at {app.job.company}.\n\n"
                f"Your scheduled follow-up date was: {app.follow_up_date.strftime('%Y-%m-%d')}\n\n"
                f"Application notes: {app.user_notes or 'No notes provided.'}\n\n"
                f"Good luck!\n\nThe Jobraker Team"
            )
            # Potentially add link to application details page on the platform
            # site_url = getattr(settings, 'SITE_URL', '')
            # if site_url:
            #     app_detail_url = f"{site_url}/applications/{app.id}/" # Example
            #     message += f"\nView your application: {app_detail_url}"


            send_mail(
                subject,
                message,
                settings.DEFAULT_FROM_EMAIL,
                [app.user.email],
                fail_silently=False
            )

            app.follow_up_reminder_sent_at = timezone.now()
            app.save(update_fields=['follow_up_reminder_sent_at', 'updated_at'])
            reminders_sent_count += 1
            logger.info(f"Sent follow-up reminder for Application {app.id} to User {app.user.id} ({app.user.email}).")

        except Exception as e:
            logger.error(f"Failed to send follow-up reminder for Application {app.id} to User {app.user.id}: {e}", exc_info=True)
            # Optionally, self.retry(exc=e) if appropriate for specific errors

    logger.info(f"Finished sending application follow-up reminders. Processed: {applications_processed_count}. Sent: {reminders_sent_count}.")
    return {
        "status": "completed",
        "processed_count": applications_processed_count,
        "sent_count": reminders_sent_count
    }


@shared_task(bind=True, max_retries=3)
def send_job_alert_notifications(self, alert_id: str = None):
    """
    Send job alert notifications to users based on their preferences.
    
    Args:
        alert_id: Specific alert ID to process, or None to process all active alerts
    """
    try:
        from apps.jobs.models import JobAlert, Job
        from apps.common.services import EmailService
        
        email_service = EmailService()
        
        # Get alerts to process
        if alert_id:
            alerts = JobAlert.objects.filter(id=alert_id, is_active=True)
        else:
            # Process alerts that are due for notification
            alerts = JobAlert.objects.filter(
                is_active=True,
                email_notifications=True
            )
        
        processed_alerts = 0
        total_emails_sent = 0
        
        for alert in alerts:
            try:
                # Build job search query based on alert criteria
                job_query = Q(status='active')
                
                if alert.keywords:
                    keyword_query = Q()
                    for keyword in alert.keywords:
                        keyword_query |= (
                            Q(title__icontains=keyword) |
                            Q(description__icontains=keyword) |
                            Q(skills_required__contains=[keyword]) |
                            Q(skills_preferred__contains=[keyword])
                        )
                    job_query &= keyword_query
                
                if alert.location:
                    job_query &= (
                        Q(location__icontains=alert.location) |
                        Q(city__icontains=alert.location) |
                        Q(state__icontains=alert.location)
                    )
                
                if alert.job_type:
                    job_query &= Q(job_type=alert.job_type)
                
                if alert.experience_level:
                    job_query &= Q(experience_level=alert.experience_level)
                
                if alert.remote_only:
                    job_query &= Q(is_remote=True)
                
                if alert.min_salary:
                    job_query &= Q(salary_min__gte=alert.min_salary)
                
                if alert.max_salary:
                    job_query &= Q(salary_max__lte=alert.max_salary)
                
                # Get matching jobs posted since last run
                since_date = alert.last_run or (timezone.now() - timezone.timedelta(days=7))
                job_query &= Q(created_at__gte=since_date)
                
                matching_jobs = Job.objects.filter(job_query)[:20]  # Limit to 20 jobs
                
                if matching_jobs.exists():
                    # Prepare job data for email
                    job_data = []
                    for job in matching_jobs:
                        job_data.append({
                            'title': job.title,
                            'company': job.company,
                            'location': job.location,
                            'salary_range': job.salary_range_display,
                            'job_type': job.get_job_type_display(),
                            'experience_level': job.get_experience_level_display(),
                            'posted_date': job.created_at.strftime('%Y-%m-%d'),
                            'url': f"https://jobraker.com/jobs/{job.id}",
                            'apply_url': f"https://jobraker.com/jobs/{job.id}/apply"
                        })
                    
                    # Send email notification
                    email_sent = email_service.send_job_alert_email(
                        user_email=alert.user.email,
                        user_name=alert.user.get_full_name(),
                        jobs=job_data,
                        alert_name=alert.name
                    )
                    
                    if email_sent:
                        total_emails_sent += 1
                        logger.info(f"Job alert email sent to {alert.user.email} for alert '{alert.name}' with {len(job_data)} jobs")
                    else:
                        logger.error(f"Failed to send job alert email to {alert.user.email} for alert '{alert.name}'")
                
                # Update last run time
                alert.last_run = timezone.now()
                alert.save(update_fields=['last_run'])
                processed_alerts += 1
                
            except Exception as e:
                logger.error(f"Error processing job alert {alert.id}: {e}")
                continue
        
        logger.info(f"Job alert notifications completed: {processed_alerts} alerts processed, {total_emails_sent} emails sent")
        return {
            'status': 'success',
            'processed_alerts': processed_alerts,
            'emails_sent': total_emails_sent
        }
        
    except Exception as exc:
        logger.error(f"Error in send_job_alert_notifications: {exc}")
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))


@shared_task(bind=True, max_retries=3)
def send_job_recommendations(self, user_id: str, limit: int = 10):
    """
    Generate and send personalized job recommendations to a user.
    
    Args:
        user_id: UUID of the user to send recommendations to
        limit: Maximum number of jobs to recommend
    """
    try:
        from apps.jobs.models import Job, RecommendedJob
        from apps.common.services import EmailService
        from apps.integrations.services.openai import EmbeddingService
        
        user = User.objects.get(id=user_id)
        
        if not hasattr(user, 'profile'):
            logger.warning(f"User {user_id} has no profile for recommendations")
            return {'status': 'no_profile', 'user_id': str(user_id)}
        
        email_service = EmailService()
        embedding_service = EmbeddingService()
        
        # Generate user profile embedding if not exists
        if not user.profile.profile_embedding:
            from apps.integrations.tasks import generate_user_profile_embeddings
            generate_user_profile_embeddings.delay(str(user_id))
            logger.info(f"Queued profile embedding generation for user {user_id}")
            return {'status': 'embedding_queued', 'user_id': str(user_id)}
        
        # Find similar jobs using vector similarity
        from pgvector.django import L2Distance
        
        # Get active jobs with embeddings
        similar_jobs = Job.objects.filter(
            status='active',
            combined_embedding__isnull=False
        ).annotate(
            distance=L2Distance('combined_embedding', user.profile.profile_embedding)
        ).order_by('distance')[:limit * 2]  # Get more to filter out already recommended
        
        # Filter out jobs user has already applied to or been recommended
        excluded_job_ids = set()
        
        # Exclude applied jobs
        applied_jobs = user.applications.values_list('job_id', flat=True)
        excluded_job_ids.update(applied_jobs)
        
        # Exclude recently recommended jobs (last 7 days)
        recent_recommendations = RecommendedJob.objects.filter(
            user=user,
            recommended_at__gte=timezone.now() - timezone.timedelta(days=7)
        ).values_list('job_id', flat=True)
        excluded_job_ids.update(recent_recommendations)
        
        # Filter final recommendations
        final_recommendations = []
        for job in similar_jobs:
            if job.id not in excluded_job_ids and len(final_recommendations) < limit:
                # Calculate similarity score (convert L2 distance to similarity)
                distance = float(job.distance)
                similarity_score = max(0.0, 1.0 - (distance / 2.0))
                
                final_recommendations.append({
                    'job': job,
                    'similarity_score': similarity_score
                })
        
        if not final_recommendations:
            logger.info(f"No new job recommendations found for user {user_id}")
            return {'status': 'no_recommendations', 'user_id': str(user_id)}
        
        # Save recommendations to database
        recommendation_objects = []
        for rec in final_recommendations:
            recommendation_objects.append(
                RecommendedJob(
                    user=user,
                    job=rec['job'],
                    score=rec['similarity_score'],
                    algorithm_version='vector_similarity_v1'
                )
            )
        
        RecommendedJob.objects.bulk_create(recommendation_objects)
        
        # Prepare email data
        recommended_jobs_data = []
        for rec in final_recommendations:
            job = rec['job']
            recommended_jobs_data.append({
                'title': job.title,
                'company': job.company,
                'location': job.location,
                'salary_range': job.salary_range_display,
                'job_type': job.get_job_type_display(),
                'experience_level': job.get_experience_level_display(),
                'match_score': f"{rec['similarity_score']:.1%}",
                'posted_date': job.created_at.strftime('%Y-%m-%d'),
                'url': f"https://jobraker.com/jobs/{job.id}",
                'apply_url': f"https://jobraker.com/jobs/{job.id}/apply"
            })
        
        # Send recommendations email
        email_sent = email_service.send_job_recommendations_email(
            user_email=user.email,
            user_name=user.get_full_name(),
            recommended_jobs=recommended_jobs_data
        )
        
        if email_sent:
            logger.info(f"Job recommendations email sent to {user.email} with {len(recommended_jobs_data)} jobs")
        else:
            logger.error(f"Failed to send job recommendations email to {user.email}")
        
        return {
            'status': 'success',
            'user_id': str(user_id),
            'recommendations_count': len(final_recommendations),
            'email_sent': email_sent
        }
        
    except User.DoesNotExist:
        logger.error(f"User not found: {user_id}")
        return {'status': 'user_not_found', 'user_id': str(user_id)}
    except Exception as exc:
        logger.error(f"Error generating job recommendations for user {user_id}: {exc}")
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))


@shared_task(bind=True, max_retries=3)
def send_application_status_update(self, application_id: str, new_status: str):
    """
    Send application status update notification to user.
    
    Args:
        application_id: UUID of the application
        new_status: New status of the application
    """
    try:
        from apps.jobs.models import Application
        from apps.common.services import EmailService
        
        application = Application.objects.select_related('user', 'job').get(id=application_id)
        email_service = EmailService()
        
        # Map internal status to user-friendly status
        status_mapping = {
            'submitted': 'Application Submitted',
            'under_review': 'Under Review',
            'interview_scheduled': 'Interview Scheduled',
            'interview_completed': 'Interview Completed',
            'offer_received': 'Offer Received',
            'accepted': 'Offer Accepted',
            'rejected': 'Application Declined',
            'withdrawn': 'Application Withdrawn',
            'failed_to_submit': 'Submission Failed',
            'skyvern_submission_failed': 'Automatic Submission Failed'
        }
        
        user_friendly_status = status_mapping.get(new_status, new_status.replace('_', ' ').title())
        
        # Send status update email
        email_sent = email_service.send_application_status_email(
            user_email=application.user.email,
            user_name=application.user.get_full_name(),
            job_title=application.job.title,
            company_name=application.job.company,
            status=user_friendly_status,
            additional_info=application.notes if application.notes else None
        )
        
        if email_sent:
            logger.info(f"Application status email sent to {application.user.email} for job '{application.job.title}' with status '{user_friendly_status}'")
        else:
            logger.error(f"Failed to send application status email to {application.user.email}")
        
        return {
            'status': 'success',
            'application_id': str(application_id),
            'new_status': new_status,
            'email_sent': email_sent
        }
        
    except Application.DoesNotExist:
        logger.error(f"Application not found: {application_id}")
        return {'status': 'application_not_found', 'application_id': str(application_id)}
    except Exception as exc:
        logger.error(f"Error sending application status update for {application_id}: {exc}")
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))


@shared_task(bind=True)
def daily_job_recommendations_batch(self, limit_per_user: int = 10):
    """
    Send daily job recommendations to all eligible users.
    
    Args:
        limit_per_user: Maximum recommendations per user
    """
    try:
        from apps.accounts.models import UserProfile
        
        # Get users who want email notifications and have complete profiles
        eligible_users = User.objects.filter(
            profile__email_notifications=True,
            profile__profile_embedding__isnull=False,
            is_active=True
        ).exclude(
            email__isnull=True
        ).exclude(
            email__exact=''
        )
        
        processed_users = 0
        queued_tasks = 0
        
        for user in eligible_users:
            try:
                # Check if user already received recommendations today
                today = timezone.now().date()
                recent_recommendations = RecommendedJob.objects.filter(
                    user=user,
                    recommended_at__date=today
                ).exists()
                
                if not recent_recommendations:
                    # Queue individual recommendation task
                    send_job_recommendations.delay(str(user.id), limit_per_user)
                    queued_tasks += 1
                
                processed_users += 1
                
            except Exception as e:
                logger.error(f"Error processing daily recommendations for user {user.id}: {e}")
                continue
        
        logger.info(f"Daily job recommendations batch completed: {processed_users} users processed, {queued_tasks} tasks queued")
        return {
            'status': 'success',
            'processed_users': processed_users,
            'queued_tasks': queued_tasks
        }
        
    except Exception as exc:
        logger.error(f"Error in daily_job_recommendations_batch: {exc}")
        return {'status': 'error', 'error': str(exc)}


@shared_task(bind=True)
def cleanup_old_recommendations(self, days_old: int = 30):
    """
    Clean up old job recommendations to keep the database lean.
    
    Args:
        days_old: Number of days after which recommendations are considered old
    """
    try:
        from apps.jobs.models import RecommendedJob
        from datetime import timedelta
        
        cutoff_date = timezone.now() - timedelta(days=days_old)
        
        # Delete old recommendations that have been viewed or dismissed
        deleted_count = RecommendedJob.objects.filter(
            recommended_at__lt=cutoff_date,
            status__in=['viewed', 'dismissed', 'irrelevant']
        ).delete()[0]
        
        logger.info(f"Cleaned up {deleted_count} old job recommendations")
        return {'status': 'success', 'deleted_count': deleted_count}
        
    except Exception as exc:
        logger.error(f"Error cleaning up old recommendations: {exc}")
        return {'status': 'error', 'error': str(exc)}
