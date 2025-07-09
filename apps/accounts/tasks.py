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
    UserProfile = apps.get_model('accounts', 'UserProfile')
    try:
        user_profile = UserProfile.objects.get(id=user_profile_id)
        
        # Combine relevant fields to create a text for embedding
        text_parts = [
            user_profile.current_title or "",
            user_profile.current_company or "",
            user_profile.experience_level or "",
            " ".join(user_profile.skills) if user_profile.skills else "",
            " ".join(user_profile.industries) if user_profile.industries else "",
            " ".join(user_profile.preferred_locations) if user_profile.preferred_locations else "",
        ]
        text_to_embed = ". ".join(filter(None, text_parts))

        if not text_to_embed:
            logger.warning(f"No text content to generate embedding for UserProfile {user_profile_id}")
            return

        embedding_service = EmbeddingService()
        embedding = embedding_service.generate_embedding(text_to_embed)

        if embedding:
            user_profile.profile_embedding = embedding
            user_profile.save(update_fields=['profile_embedding', 'updated_at'])
            logger.info(f"Successfully generated and saved embedding for UserProfile {user_profile_id}")
        else:
            logger.error(f"Failed to generate embedding for UserProfile {user_profile_id}")

    except UserProfile.DoesNotExist:
        logger.error(f"UserProfile with id {user_profile_id} not found for embedding generation.")
    except Exception as e:
        logger.error(f"Error in generate_user_profile_embedding_task for id {user_profile_id}: {e}", exc_info=True)


@shared_task
def process_resume_task(user_profile_id: str, resume_file_path: str):
    """
    Celery task to process uploaded resume and extract relevant information.
    """
    import os
    import json
    from django.core.files.storage import default_storage
    from apps.integrations.services.openai_service import OpenAIService
    
    UserProfile = apps.get_model('accounts', 'UserProfile')
    
    try:
        user_profile = UserProfile.objects.get(id=user_profile_id)
        
        # Read resume file content
        if default_storage.exists(resume_file_path):
            with default_storage.open(resume_file_path, 'rb') as file:
                resume_content = extract_text_from_resume(file, resume_file_path)
        else:
            logger.error(f"Resume file not found: {resume_file_path}")
            return
        
        if not resume_content:
            logger.warning(f"No content extracted from resume for UserProfile {user_profile_id}")
            return
        
        # Use OpenAI to extract structured information from resume
        openai_service = OpenAIService()
        extraction_prompt = f"""
        Please analyze the following resume and extract key information in JSON format:
        
        Resume content:
        {resume_content}
        
        Extract the following information:
        {{
            "current_title": "current or most recent job title",
            "current_company": "current or most recent company",
            "experience_level": "entry|mid|senior|lead|executive",
            "skills": ["list", "of", "technical", "skills"],
            "industries": ["list", "of", "relevant", "industries"],
            "summary": "brief professional summary"
        }}
        
        Only return valid JSON without any additional text or formatting.
        """
        
        extracted_info = openai_service.generate_completion(extraction_prompt)
        
        try:
            # Parse the extracted information
            info = json.loads(extracted_info)
            
            # Update user profile with extracted information
            updates = {}
            if info.get('current_title'):
                updates['current_title'] = info['current_title']
            if info.get('current_company'):
                updates['current_company'] = info['current_company']
            if info.get('experience_level') and info['experience_level'] in dict(UserProfile.EXPERIENCE_LEVELS):
                updates['experience_level'] = info['experience_level']
            if info.get('skills') and isinstance(info['skills'], list):
                updates['skills'] = info['skills']
            if info.get('industries') and isinstance(info['industries'], list):
                updates['industries'] = info['industries']
            
            # Update profile
            for field, value in updates.items():
                setattr(user_profile, field, value)
            
            user_profile.save()
            
            # Generate new embedding with updated profile
            generate_user_profile_embedding_task.delay(user_profile_id)
            
            logger.info(f"Successfully processed resume for UserProfile {user_profile_id}")
            
        except json.JSONDecodeError:
            logger.error(f"Failed to parse extracted information as JSON for UserProfile {user_profile_id}")
            
    except UserProfile.DoesNotExist:
        logger.error(f"UserProfile with id {user_profile_id} not found for resume processing.")
    except Exception as e:
        logger.error(f"Error in process_resume_task for id {user_profile_id}: {e}", exc_info=True)


def extract_text_from_resume(file, file_path: str) -> str:
    """
    Extract text content from resume file based on file type.
    """
    import PyPDF2
    import docx
    
    try:
        file_extension = file_path.lower().split('.')[-1]
        
        if file_extension == 'pdf':
            reader = PyPDF2.PdfReader(file)
            text = ""
            for page in reader.pages:
                text += page.extract_text() + "\n"
            return text
            
        elif file_extension in ['doc', 'docx']:
            doc = docx.Document(file)
            text = ""
            for paragraph in doc.paragraphs:
                text += paragraph.text + "\n"
            return text
            
        else:
            logger.warning(f"Unsupported file format: {file_extension}")
            return ""
            
    except Exception as e:
        logger.error(f"Error extracting text from resume: {e}")
        return ""
