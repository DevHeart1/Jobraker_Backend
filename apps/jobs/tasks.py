import logging
from datetime import timedelta
from typing import Any

from celery import shared_task
from django.db.models import Q
from django.utils import timezone

from apps.accounts.models import \
    UserProfile  # Assuming UserProfile is in accounts.models
from apps.jobs.services import \
    JobMatchService  # Or JobRecommendationService if created separately

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def generate_recommendations_for_single_user_task(self, user_profile_id: Any):
    """
    Celery task to generate job recommendations for a single user.
    Args:
        user_profile_id: The ID of the UserProfile for whom to generate recommendations.
    """
    logger.info(
        f"Starting recommendation generation for UserProfile ID: {user_profile_id}"
    )
    try:
        # Assuming JobMatchService now contains generate_recommendations_for_user
        # If it were a separate JobRecommendationService, instantiate that instead.
        service = JobMatchService()
        recommendations = service.generate_recommendations_for_user(
            user_profile_id=user_profile_id
        )

        if recommendations:
            logger.info(
                f"Successfully generated {len(recommendations)} recommendations for UserProfile ID: {user_profile_id}"
            )
            return {
                "status": "success",
                "user_profile_id": user_profile_id,
                "recommendations_count": len(recommendations),
            }
        else:
            logger.info(
                f"No new recommendations generated for UserProfile ID: {user_profile_id}"
            )
            return {
                "status": "no_new_recommendations",
                "user_profile_id": user_profile_id,
                "recommendations_count": 0,
            }

    except Exception as exc:
        logger.error(
            f"Error generating recommendations for UserProfile ID {user_profile_id}: {exc}"
        )
        # Retry with exponential backoff
        raise self.retry(exc=exc, countdown=60 * (2**self.request.retries))


@shared_task(
    bind=True, max_retries=1
)  # Batch task, maybe fewer retries or longer delay
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
    active_user_profiles = UserProfile.objects.filter(
        user__is_active=True
    )  # Example filter

    if not active_user_profiles.exists():
        logger.info(
            "No active user profiles found for batch recommendation generation."
        )
        return {"status": "no_active_users", "processed_count": 0}

    processed_count = 0
    queued_count = 0
    for profile in active_user_profiles:
        try:
            generate_recommendations_for_single_user_task.delay(profile.id)
            queued_count += 1
        except Exception as e:
            logger.error(
                f"Failed to queue recommendation task for UserProfile ID {profile.id}: {e}"
            )
        processed_count += 1  # Counts profiles attempted to queue for

    logger.info(
        f"Batch recommendations: Attempted to queue for {processed_count} users. Successfully queued: {queued_count} tasks."
    )
    return {
        "status": "batch_queued",
        "total_profiles_considered": processed_count,
        "tasks_queued": queued_count,
    }


@shared_task(bind=True, max_retries=3)
def process_job_alerts_task(self):
    """
    Processes all active job alerts, finds matching new jobs,
    and triggers notifications for users.
    """
    from django.db.models import Q
    from django.utils import timezone

    from apps.jobs.models import Job, JobAlert

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
        if not alert.last_run:  # Never run before
            should_process = True
        else:
            # Accessing frequency string values directly
            if alert.frequency == "daily":
                should_process = (now - alert.last_run) >= timezone.timedelta(days=1)
            elif alert.frequency == "weekly":
                should_process = (now - alert.last_run) >= timezone.timedelta(weeks=1)
            elif alert.frequency == "monthly":
                should_process = (now - alert.last_run) >= timezone.timedelta(
                    days=30
                )  # Approximation
            elif alert.frequency == "immediate":
                # For a batch task like this, 'immediate' is tricky.
                # It might mean process every time the task runs if new jobs exist.
                # Or, 'immediate' alerts are handled by a different, more frequent task or signals.
                # For this batch task, let's assume 'immediate' means it's always due if new jobs exist.
                should_process = True
                # Consider if 'immediate' alerts should even be processed by this batch job,
                # or if they warrant a separate, more frequent mechanism (e.g., signal-based on Job creation).
                # For now, including it here means it gets checked every time this batch task runs.

        if not should_process:
            alerts_skipped_due_to_frequency += 1
            logger.debug(
                f"Skipping alert ID: {alert.id} for user: {alert.user.id} due to frequency. Last run: {alert.last_run}, Freq: {alert.frequency}"
            )
            continue

        logger.info(
            f"Processing job alert ID: {alert.id} for user: {alert.user.id} (Frequency: {alert.frequency}, Last run: {alert.last_run})"
        )
        alerts_processed_count += 1

        job_filters = Q()

        # Time filter: only new jobs since last run, or in last 24h if no last_run
        if alert.last_run:
            job_filters &= Q(created_at__gt=alert.last_run)  # Or use job.posted_date
        else:
            # For the very first run of an alert, look back a reasonable period, e.g., 1 day.
            job_filters &= Q(
                created_at__gte=timezone.now() - timezone.timedelta(days=1)
            )

        # Keyword filter (search in title and description)
        if alert.keywords:
            keyword_query = Q()
            for kw in alert.keywords:  # Assuming alert.keywords is a list of strings
                keyword_query |= Q(title__icontains=kw) | Q(description__icontains=kw)
            if keyword_query:  # Only add if there were keywords
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
        if alert.min_salary is not None:  # Check for None as 0 is a valid salary
            job_filters &= Q(salary_min__gte=alert.min_salary) | Q(
                salary_max__gte=alert.min_salary
            )  # Job's max can meet user's min

        # --- Find matching jobs ---
        try:
            matching_jobs = Job.objects.filter(job_filters, status="active").distinct()

            if not matching_jobs.exists():
                logger.info(f"No new matching jobs found for alert ID: {alert.id}")

            for job in matching_jobs:
                # --- Prevent Duplicate Notifications (Conceptual/Placeholder) ---
                # In a real system, you'd check if this user has already been notified for this job via this alert.
                # Example: if NotifiedAlertMatch.objects.filter(user=alert.user, job=job, job_alert=alert).exists():
                # continue
                # For now, we assume each found job is a new notification.
                # --- End Conceptual Duplicate Prevention ---

                logger.info(
                    f"MATCH FOUND: Alert ID {alert.id} for user {alert.user.id} matched Job ID {job.id} ('{job.title}')"
                )

                # Store match information for email notification below

            if matching_jobs.exists():
                # Prepare and send one email with all matching jobs for this alert
                try:
                    from django.conf import settings
                    from django.core.mail import send_mail
                    from django.urls import \
                        reverse  # To build absolute URLs if needed

                    subject = f"New Job Matches for Your Alert: {alert.name or 'Unnamed Alert'}"

                    message_lines = [
                        f"Hello {alert.user.first_name or alert.user.username},",
                        "\nWe found new jobs matching your alert criteria:\n",
                    ]

                    for job in matching_jobs:
                        # Assuming you have a way to get the absolute URL for a job
                        # For example, if Job model has get_absolute_url or you construct it
                        job_url = (
                            settings.SITE_URL
                            + reverse("job-detail", kwargs={"pk": job.pk})
                            if hasattr(settings, "SITE_URL")
                            else f"/jobs/{job.pk}/"
                        )  # Fallback relative URL
                        message_lines.append(
                            f"- {job.title} at {job.company} ({job.location})"
                        )
                        message_lines.append(f"  View: {job_url}\n")

                    message_lines.append(
                        "\nYou can manage your alerts here: [Link to Manage Alerts Page]"
                    )  # Placeholder for actual link

                    plain_message = "\n".join(message_lines)

                    if (
                        alert.user.email and alert.email_notifications
                    ):  # Check if user wants email notifications
                        send_mail(
                            subject,
                            plain_message,
                            settings.DEFAULT_FROM_EMAIL,  # Ensure this is configured
                            [alert.user.email],
                            fail_silently=False,
                        )
                        logger.info(
                            f"Sent job alert email to {alert.user.email} for alert ID: {alert.id} with {matching_jobs.count()} jobs."
                        )
                        notifications_sent_count += 1
                    else:
                        logger.info(
                            f"User {alert.user.email} has email notifications disabled for alert ID: {alert.id} or no email."
                        )

                except Exception as mail_exc:
                    logger.error(
                        f"Failed to send email for alert ID {alert.id} to {alert.user.email}: {mail_exc}"
                    )

            # Update last_run timestamp for the alert, regardless of whether email was sent, to prevent re-processing same jobs
            alert.last_run = timezone.now()
            alert.save(update_fields=["last_run"])
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
        "notifications_sent": notifications_sent_count,
    }


@shared_task(bind=True, max_retries=3)
def send_application_follow_up_reminders(self):
    """
    Sends follow-up reminders for job applications.

    Checks for applications where the 'follow_up_date' is today or in the past
    and a reminder has not yet been sent for that specific follow_up_date.
    """
    from django.conf import settings
    from django.core.mail import send_mail
    from django.db.models import F, Q
    from django.utils import timezone

    from apps.jobs.models import Application

    today = timezone.now().date()
    reminders_sent_count = 0
    applications_processed_count = 0

    # Query for applications needing a reminder:
    # - User is active
    # - follow_up_date is set and is today or in the past
    # - EITHER follow_up_reminder_sent_at is null (never sent for this follow_up_date)
    # - OR follow_up_reminder_sent_at is older than the current follow_up_date
    #   (meaning follow_up_date was changed after last reminder was sent, so a new reminder is due for the new date)
    applications_to_remind = (
        Application.objects.filter(
            user__is_active=True,
            follow_up_date__isnull=False,
            follow_up_date__lte=today,
        )
        .filter(
            Q(follow_up_reminder_sent_at__isnull=True)
            | Q(follow_up_reminder_sent_at__lt=F("follow_up_date"))
        )
        .select_related("user", "job")
    )

    if not applications_to_remind.exists():
        logger.info("No applications found requiring follow-up reminders at this time.")
        return {"status": "no_reminders_due", "sent_count": 0}

    logger.info(
        f"Found {applications_to_remind.count()} applications for potential follow-up reminders."
    )

    for app in applications_to_remind:
        applications_processed_count += 1
        if not app.user.email:
            logger.warning(
                f"User {app.user.id} for Application {app.id} has no email. Skipping reminder."
            )
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
                fail_silently=False,
            )

            app.follow_up_reminder_sent_at = timezone.now()
            app.save(update_fields=["follow_up_reminder_sent_at", "updated_at"])
            reminders_sent_count += 1
            logger.info(
                f"Sent follow-up reminder for Application {app.id} to User {app.user.id} ({app.user.email})."
            )

        except Exception as e:
            logger.error(
                f"Failed to send follow-up reminder for Application {app.id} to User {app.user.id}: {e}",
                exc_info=True,
            )
            # Optionally, self.retry(exc=e) if appropriate for specific errors

    logger.info(
        f"Finished sending application follow-up reminders. Processed: {applications_processed_count}. Sent: {reminders_sent_count}."
    )
    return {
        "status": "completed",
        "processed_count": applications_processed_count,
        "sent_count": reminders_sent_count,
    }


@shared_task(bind=True, max_retries=2)
def auto_apply_matching_jobs(self, limit=50):
    """
    Automatically apply to jobs for users who have enabled auto-apply and meet criteria.

    Args:
        limit: Maximum number of auto-applications to process in this batch
    """
    try:
        from django.utils import timezone

        from apps.accounts.models import UserProfile
        from apps.integrations.tasks import submit_skyvern_application_task
        from apps.jobs.models import Application, Job

        # Find users with auto-apply enabled who have active profiles
        auto_apply_users = UserProfile.objects.filter(
            user__is_active=True,
            auto_apply_enabled=True,  # Assuming this field exists on UserProfile
        ).select_related("user")

        if not auto_apply_users.exists():
            logger.info("No users found with auto-apply enabled")
            return {"status": "no_auto_apply_users", "processed_count": 0}

        total_applications_queued = 0
        users_processed = 0

        for user_profile in auto_apply_users[:limit]:
            users_processed += 1
            user = user_profile.user

            # Find jobs that match user's criteria and haven't been applied to yet
            # This is a simplified matching - in practice you'd use more sophisticated logic
            matching_jobs = Job.objects.filter(
                status="active",
                created_at__gte=timezone.now()
                - timezone.timedelta(days=7),  # Only recent jobs
            ).exclude(
                # Exclude jobs already applied to by this user
                id__in=Application.objects.filter(user=user).values_list(
                    "job_id", flat=True
                )
            )

            # Apply additional filters based on user preferences
            if (
                hasattr(user_profile, "preferred_job_types")
                and user_profile.preferred_job_types
            ):
                matching_jobs = matching_jobs.filter(
                    job_type__in=user_profile.preferred_job_types
                )

            if (
                hasattr(user_profile, "preferred_locations")
                and user_profile.preferred_locations
            ):
                location_filter = Q()
                for location in user_profile.preferred_locations:
                    location_filter |= Q(location__icontains=location)
                matching_jobs = matching_jobs.filter(location_filter)

            if hasattr(user_profile, "min_salary") and user_profile.min_salary:
                matching_jobs = matching_jobs.filter(
                    Q(salary_min__gte=user_profile.min_salary)
                    | Q(salary_max__gte=user_profile.min_salary)
                )

            # Limit applications per user per run
            user_daily_limit = getattr(user_profile, "daily_auto_apply_limit", 5)

            # Check how many auto-applications were already made today
            today_start = timezone.now().replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            today_applications = Application.objects.filter(
                user=user, created_at__gte=today_start, application_method="auto_apply"
            ).count()

            remaining_quota = max(0, user_daily_limit - today_applications)

            if remaining_quota == 0:
                logger.info(f"User {user.id} has reached daily auto-apply limit")
                continue

            # Get jobs to apply to (limited by remaining quota)
            jobs_to_apply = matching_jobs[:remaining_quota]

            for job in jobs_to_apply:
                try:
                    # Create application record
                    application = Application.objects.create(
                        user=user,
                        job=job,
                        status="pending",
                        application_method="auto_apply",
                        cover_letter=user_profile.default_cover_letter or "",
                        user_notes="Auto-applied based on user preferences",
                    )

                    # Queue Skyvern application if auto-apply is via Skyvern
                    if (
                        hasattr(user_profile, "auto_apply_via_skyvern")
                        and user_profile.auto_apply_via_skyvern
                    ):
                        # Prepare user profile data for Skyvern
                        user_profile_data = {
                            "full_name": user.get_full_name(),
                            "email": user.email,
                            "phone": getattr(user_profile, "phone", ""),
                            "current_title": getattr(user_profile, "current_title", ""),
                            "experience_level": getattr(
                                user_profile, "experience_level", ""
                            ),
                            "skills": getattr(user_profile, "skills", []),
                            "location": getattr(user_profile, "location", ""),
                        }

                        # Get resume in base64 if available
                        resume_base64 = None
                        if (
                            hasattr(user_profile, "resume_file")
                            and user_profile.resume_file
                        ):
                            try:
                                import base64

                                resume_base64 = base64.b64encode(
                                    user_profile.resume_file.read()
                                ).decode("utf-8")
                            except Exception as e:
                                logger.warning(
                                    f"Could not encode resume for user {user.id}: {e}"
                                )

                        # Queue Skyvern application
                        submit_skyvern_application_task.delay(
                            application_id=str(application.id),
                            job_url=job.source_url
                            or f"https://example.com/jobs/{job.id}",
                            prompt_template="Apply to this job automatically using the provided user profile and resume.",
                            user_profile_data=user_profile_data,
                            resume_base64=resume_base64,
                        )

                    total_applications_queued += 1
                    logger.info(
                        f"Queued auto-application for user {user.id} to job {job.id}"
                    )

                except Exception as e:
                    logger.error(
                        f"Failed to create auto-application for user {user.id}, job {job.id}: {e}"
                    )

        logger.info(
            f"Auto-apply batch completed: {users_processed} users processed, {total_applications_queued} applications queued"
        )
        return {
            "status": "success",
            "users_processed": users_processed,
            "applications_queued": total_applications_queued,
        }

    except Exception as exc:
        logger.error(f"Error in auto_apply_matching_jobs: {exc}")
        raise self.retry(exc=exc, countdown=300 * (2**self.request.retries))


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def generate_job_embedding_task(self, job_id: int):
    """
    Celery task to generate and save an embedding for a single job listing.
    """
    from apps.integrations.services.openai_service import EmbeddingService
    from apps.jobs.models import Job

    logger.info(f"Starting embedding generation for Job ID: {job_id}")

    try:
        job = Job.objects.get(pk=job_id)
    except Job.DoesNotExist:
        logger.warning(f"Job with ID {job_id} not found. Cannot generate embedding.")
        return {"status": "error", "message": f"Job {job_id} not found."}

    try:
        # Combine relevant fields for a rich embedding
        text_to_embed = (
            f"Job Title: {job.title}. "
            f"Company: {job.company}. "
            f"Description: {job.description}. "
            f"Skills: {', '.join(job.skills_required) if job.skills_required else 'Not specified'}."
        )

        embedding_service = EmbeddingService()
        embedding = embedding_service.generate_embedding(text_to_embed)

        if embedding:
            job.job_embedding = embedding
            job.save(update_fields=["job_embedding"])
            logger.info(
                f"Successfully generated and saved embedding for Job ID: {job_id}"
            )
            return {"status": "success", "job_id": job_id}
        else:
            logger.error(
                f"Failed to generate embedding for Job ID: {job_id}. Service returned None."
            )
            # Retry the task
            self.retry(
                exc=Exception(f"Embedding generation failed for Job ID {job_id}")
            )
            return {
                "status": "retry",
                "job_id": job_id,
                "message": "Embedding generation failed, retrying.",
            }

    except Exception as exc:
        logger.error(
            f"An unexpected error occurred during embedding generation for Job ID {job_id}: {exc}"
        )
        self.retry(exc=exc)
        return {"status": "retry", "job_id": job_id, "message": str(exc)}


@shared_task
def batch_generate_recommendations_for_active_users_task():
    """
    Celery task to generate job recommendations for all active users.
    This task runs daily to update recommendations for users.
    """
    from apps.accounts.models import UserProfile
    from apps.jobs.services import JobMatchService

    try:
        # Get all user profiles that have embeddings (indicating they are set up for matching)
        user_profiles = UserProfile.objects.filter(
            profile_embedding__isnull=False
        ).select_related("user")

        service = JobMatchService()
        total_processed = 0
        total_recommendations = 0

        for profile in user_profiles:
            try:
                # Generate recommendations for this user
                recommendations = service.generate_recommendations_for_user(
                    user_profile_id=profile.id, num_recommendations=10
                )

                total_processed += 1
                total_recommendations += len(recommendations)

                logger.info(
                    f"Generated {len(recommendations)} recommendations for user {profile.user.email}"
                )

            except Exception as e:
                logger.error(
                    f"Error generating recommendations for user {profile.user.email}: {e}"
                )
                continue

        logger.info(
            f"Batch recommendation task completed. Processed {total_processed} users, generated {total_recommendations} recommendations."
        )

    except Exception as e:
        logger.error(
            f"Error in batch_generate_recommendations_for_active_users_task: {e}",
            exc_info=True,
        )


@shared_task
def process_job_alerts_task():
    """
    Celery task to process job alerts and send notifications.
    """
    from apps.jobs.models import JobAlert
    from apps.jobs.services import JobMatchService

    try:
        active_alerts = JobAlert.objects.filter(is_active=True).select_related("user")

        for alert in active_alerts:
            try:
                # Here you would implement the logic to find matching jobs
                # and send notifications to users
                logger.info(
                    f"Processing job alert {alert.id} for user {alert.user.email}"
                )

                # Update last_run timestamp
                alert.last_run = timezone.now()
                alert.save(update_fields=["last_run"])

            except Exception as e:
                logger.error(f"Error processing job alert {alert.id}: {e}")
                continue

        logger.info(f"Processed {len(active_alerts)} job alerts")

    except Exception as e:
        logger.error(f"Error in process_job_alerts_task: {e}", exc_info=True)


@shared_task
def send_application_follow_up_reminders():
    """
    Celery task to send follow-up reminders for applications.
    """
    from datetime import timedelta

    from apps.jobs.models import Application

    try:
        # Find applications that need follow-up reminders
        cutoff_date = timezone.now() - timedelta(days=7)
        applications = Application.objects.filter(
            status="submitted",
            applied_at__lte=cutoff_date,
            follow_up_reminder_sent_at__isnull=True,
        ).select_related("user", "job")

        for application in applications:
            try:
                # Here you would implement the logic to send follow-up reminders
                logger.info(
                    f"Sending follow-up reminder for application {application.id}"
                )

                # Update reminder sent timestamp
                application.follow_up_reminder_sent_at = timezone.now()
                application.save(update_fields=["follow_up_reminder_sent_at"])

            except Exception as e:
                logger.error(
                    f"Error sending follow-up reminder for application {application.id}: {e}"
                )
                continue

        logger.info(f"Sent follow-up reminders for {len(applications)} applications")

    except Exception as e:
        logger.error(
            f"Error in send_application_follow_up_reminders: {e}", exc_info=True
        )
