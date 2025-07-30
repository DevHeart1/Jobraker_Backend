"""
Celery tasks for the accounts app.
"""

import logging

from celery import shared_task
from django.apps import apps

from apps.integrations.services.openai_service import EmbeddingService

logger = logging.getLogger(__name__)


@shared_task
def generate_user_profile_embedding_task(user_profile_id: str):
    """
    Celery task to generate and save embeddings for a UserProfile.
    """
    UserProfile = apps.get_model("accounts", "UserProfile")
    try:
        user_profile = UserProfile.objects.get(id=user_profile_id)

        # Combine relevant fields to create a text for embedding
        text_parts = [
            user_profile.current_title or "",
            user_profile.current_company or "",
            user_profile.experience_level or "",
            " ".join(user_profile.skills) if user_profile.skills else "",
            " ".join(user_profile.industries) if user_profile.industries else "",
            (
                " ".join(user_profile.preferred_locations)
                if user_profile.preferred_locations
                else ""
            ),
        ]
        text_to_embed = ". ".join(filter(None, text_parts))

        if not text_to_embed:
            logger.warning(
                f"No text content to generate embedding for UserProfile {user_profile_id}"
            )
            return

        embedding_service = EmbeddingService()
        embedding = embedding_service.generate_embedding(text_to_embed)

        if embedding:
            user_profile.profile_embedding = embedding
            user_profile.save(update_fields=["profile_embedding", "updated_at"])
            logger.info(
                f"Successfully generated and saved embedding for UserProfile {user_profile_id}"
            )
        else:
            logger.error(
                f"Failed to generate embedding for UserProfile {user_profile_id}"
            )

    except UserProfile.DoesNotExist:
        logger.error(
            f"UserProfile with id {user_profile_id} not found for embedding generation."
        )
    except Exception as e:
        logger.error(
            f"Error in generate_user_profile_embedding_task for id {user_profile_id}: {e}",
            exc_info=True,
        )


@shared_task(bind=True, max_retries=3)
def process_resume_task(self, user_id: str):
    """
    Celery task to process an uploaded resume, extract information,
    and update the user's profile.
    """
    User = apps.get_model("accounts", "User")
    UserProfile = apps.get_model("accounts", "UserProfile")
    try:
        user = User.objects.get(id=user_id)
        profile = UserProfile.objects.get(user=user)

        if not profile.resume:
            logger.error(
                f"No resume file found for UserProfile {profile.id} to process."
            )
            return

        resume_path = profile.resume.path
        resume_text = extract_text_from_resume(resume_path)

        if not resume_text:
            logger.warning(
                f"Could not extract text from resume for UserProfile {profile.id}"
            )
            # Optionally, update profile status to indicate failure
            return

        from apps.integrations.services.openai_service import \
            OpenAIJobAssistant

        assistant = OpenAIJobAssistant()
        analysis_result = assistant.analyze_resume(resume_text=resume_text)

        if analysis_result and analysis_result.get("success"):
            extracted_data = analysis_result.get("analysis", {})

            # Update profile fields based on extracted data
            # Use set for skills to avoid duplicates
            current_skills = set(profile.skills or [])
            extracted_skills = set(extracted_data.get("extracted_skills", []))
            profile.skills = sorted(list(current_skills.union(extracted_skills)))

            if extracted_data.get("professional_summary"):
                profile.bio = extracted_data["professional_summary"]

            # Example of updating other fields
            if extracted_data.get("current_job_title"):
                profile.current_title = extracted_data["current_job_title"]

            profile.save()
            logger.info(
                f"Successfully processed resume and updated profile for user {user_id}"
            )

            # After updating the profile with text, generate the new embedding
            generate_user_profile_embedding_task.delay(user_profile_id=str(profile.id))
        else:
            error_msg = analysis_result.get(
                "error", "Unknown error during resume analysis."
            )
            logger.error(f"Resume analysis failed for user {user_id}: {error_msg}")
            # Optionally, add a note to the user's profile about the failure

    except User.DoesNotExist:
        logger.error(f"User with id {user_id} not found for resume processing.")
    except UserProfile.DoesNotExist:
        logger.error(
            f"UserProfile for user id {user_id} not found for resume processing."
        )
    except Exception as e:
        logger.error(
            f"Error in process_resume_task for user id {user_id}: {e}", exc_info=True
        )
        raise self.retry(exc=e, countdown=60 * 5)


def extract_text_from_resume(file_path: str) -> str:
    """
    Extract text content from a resume file based on its extension.
    """
    try:
        file_extension = file_path.lower().split(".")[-1]

        if file_extension == "pdf":
            try:
                import PyPDF2

                with open(file_path, "rb") as f:
                    reader = PyPDF2.PdfReader(f)
                    text = "".join(page.extract_text() for page in reader.pages)
                return text
            except ImportError:
                logger.error(
                    "PyPDF2 is not installed. Please install it with `pip install PyPDF2`"
                )
                return ""

        elif file_extension in ["doc", "docx"]:
            try:
                import docx

                doc = docx.Document(file_path)
                return "\n".join(para.text for para in doc.paragraphs)
            except ImportError:
                logger.error(
                    "python-docx is not installed. Please install it with `pip install python-docx`"
                )
                return ""

        else:
            logger.warning(f"Unsupported resume file format: {file_extension}")
            return ""

    except Exception as e:
        logger.error(f"Error extracting text from resume at {file_path}: {e}")
        return ""
