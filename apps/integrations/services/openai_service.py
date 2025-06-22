"""
OpenAI GPT integration service for AI-powered job assistance.
"""

import openai
import logging
import json # For parsing function call arguments
from typing import Dict, List, Optional, Any
from django.conf import settings
from django.contrib.auth import get_user_model

logger = logging.getLogger(__name__)
User = get_user_model()


class OpenAIJobAssistant:
    """
    AI-powered job assistance using OpenAI GPT.
    Provides job advice, resume optimization, and career guidance.
    """
    
    def __init__(self):
        self.api_key = getattr(settings, 'OPENAI_API_KEY', '')
        self.model = getattr(settings, 'OPENAI_MODEL', 'gpt-4')
        
        if self.api_key:
            openai.api_key = self.api_key
        else:
            logger.warning("OpenAI API key not configured - using mock responses")
    
    def get_job_advice(
        self, 
        user_id: int, 
        advice_type: str, 
        context: str = "",
        user_profile: Dict[str, Any] = None,
        # RAG specific
        query_for_rag: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Asynchronously gets personalized job advice from AI via Celery.
        The actual OpenAI call is made in the Celery task `get_openai_job_advice_task`.
        
        Args:
            user_id: User requesting advice
            advice_type: Type of advice (resume, interview, salary, etc.)
            context: Additional context for the advice (e.g., specific question)
            user_profile: User profile data (object or dict) for personalization.
            query_for_rag: The specific text query to use for RAG context retrieval.
        
        Returns:
            A dictionary containing the task_id if successfully queued, or an error message.
        """
        from apps.integrations.tasks import get_openai_job_advice_task

        user_profile_data = None
        if user_profile: # Convert UserProfile object to dict if necessary
            if not isinstance(user_profile, dict):
                # Assuming user_profile might be a UserProfile model instance
                # This part needs to be robust based on what's actually passed.
                try:
                    user_profile_data = {
                        'experience_level': getattr(user_profile, 'experience_level', ''),
                        'skills': list(getattr(user_profile, 'skills', [])) # Ensure skills are list
                        # Add other relevant serializable fields
                    }
                except Exception as e:
                    logger.error(f"Error serializing user_profile for task: {e}")
                    # Fallback or handle error appropriately
                    user_profile_data = {}
            else:
                user_profile_data = user_profile

        try:
            task = get_openai_job_advice_task.delay(
                user_id=user_id,
                advice_type=advice_type,
                context=context,
                user_profile_data=user_profile_data,
                query_for_rag=query_for_rag
            )
            logger.info(f"Queued get_openai_job_advice_task with ID: {task.id} for user {user_id}")
            return {'status': 'queued', 'task_id': task.id}
        except Exception as e:
            logger.error(f"Failed to queue get_openai_job_advice_task for user {user_id}: {e}")
            return {'status': 'error', 'message': 'Failed to queue advice task.'}

    def chat_response(
        self, 
        user_id: int, 
        message: str, 
        conversation_history: List[Dict[str, str]] = None,
        user_profile: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Asynchronously generates AI chat response via Celery.
        The actual OpenAI call is made in the Celery task `get_openai_chat_response_task`.
        """
        from apps.integrations.tasks import get_openai_chat_response_task

        user_profile_data = None
        if user_profile: # Convert UserProfile object to dict
            if not isinstance(user_profile, dict):
                try:
                    user_profile_data = {
                        'experience_level': getattr(user_profile, 'experience_level', ''),
                        'skills': list(getattr(user_profile, 'skills', []))
                    }
                except Exception as e:
                    logger.error(f"Error serializing user_profile for chat task: {e}")
                    user_profile_data = {}
            else:
                user_profile_data = user_profile
        
        # Moderation of user input before queuing the task
        if self._moderate_text(message):
            logger.warning(f"User message flagged by moderation (chat_response service method): '{message[:100]}...'")
            return {
                'status': 'error',
                'message': "Input violates content guidelines.",
                'error_code': 'flagged_input'
            }

        try:
            task = get_openai_chat_response_task.delay(
                user_id=user_id,
                message=message,
                conversation_history=conversation_history,
                user_profile_data=user_profile_data
            )
            logger.info(f"Queued get_openai_chat_response_task with ID: {task.id} for user {user_id}")
            return {'status': 'queued', 'task_id': task.id}
        except Exception as e:
            logger.error(f"Failed to queue get_openai_chat_response_task for user {user_id}: {e}")
            return {'status': 'error', 'message': 'Failed to queue chat task.'}

    def _moderate_text(self, text_to_moderate: str) -> bool:
        """
        Checks text against OpenAI's Moderation API.

        Args:
            text_to_moderate: The text string to moderate.

        Returns:
            True if the text is flagged as inappropriate, False otherwise or if an error occurs.
        """
        if not self.api_key or not text_to_moderate: # Ensure api_key check is relevant for this instance
            return False

        try:
            # Ensure openai client is initialized if not done globally or per-instance
            if openai.api_key is None and self.api_key:
                 openai.api_key = self.api_key

            response = openai.Moderation.create(input=text_to_moderate)
            result = response.results[0]
            if result.flagged:
                logger.warning(f"OpenAI Moderation API flagged content: Categories: {[cat for cat, flagged in result.categories.items() if flagged]}")
                return True
            return False
        except Exception as e:
            logger.error(f"OpenAI Moderation API call failed: {e}")
            return False # Fail safe
    
    def analyze_resume(
        self, 
        resume_text: str, 
        target_job: str = "",
        user_profile: Dict[str, Any] = None # Should be user_profile_data from task
    ) -> Dict[str, Any]:
        """
        Asynchronously analyzes resume via Celery.
        The actual OpenAI call is made in the Celery task `analyze_openai_resume_task`.
        """
        from apps.integrations.tasks import analyze_openai_resume_task

        user_profile_data = None
        if user_profile: # Convert UserProfile object to dict
            if not isinstance(user_profile, dict):
                try:
                    user_profile_data = {
                        'experience_level': getattr(user_profile, 'experience_level', ''),
                        'skills': list(getattr(user_profile, 'skills', []))
                    }
                except Exception as e:
                    logger.error(f"Error serializing user_profile for resume task: {e}")
                    user_profile_data = {}
            else:
                user_profile_data = user_profile
        
        # Moderation of resume text before queuing (optional, can be lengthy)
        # For brevity, skipping direct moderation here but could be added.
        # if self._moderate_text(resume_text):
        #     return {'status': 'error', 'message': "Resume content violates guidelines."}

        try:
            task = analyze_openai_resume_task.delay(
                resume_text=resume_text,
                target_job=target_job,
                user_profile_data=user_profile_data
            )
            logger.info(f"Queued analyze_openai_resume_task with ID: {task.id}")
            return {'status': 'queued', 'task_id': task.id}
        except Exception as e:
            logger.error(f"Failed to queue analyze_openai_resume_task: {e}")
            return {'status': 'error', 'message': 'Failed to queue resume analysis task.'}
    
    def _build_advice_prompt(
        self, 
        advice_type: str, 
        context: str, 
        user_profile: Optional[Dict[str, Any]] = None,
        rag_context: str = ""
    ) -> str:
        """Build a personalized prompt for job advice."""
        profile_context = ""
        if user_profile:
            profile_context = f"""
            User Profile:
            - Experience Level: {user_profile.get('experience_level', 'Not specified')}
            - Skills: {', '.join(user_profile.get('skills', []))}
            - Desired Salary: ${user_profile.get('desired_salary_min', 'Not specified')} - ${user_profile.get('desired_salary_max', 'Not specified')}
            - Location: {user_profile.get('location', 'Not specified')}
            """
        
        main_request = f"Additional context or question from user: {context}"

        # Base prompts for different advice types
        advice_base_prompts = {
            'resume': "Provide specific resume optimization advice for a job seeker.",
            'interview': "Give interview preparation advice and tips.",
            'salary': "Provide salary negotiation advice and market insights.",
            'application': "Give job application strategy advice.",
            'skills': "Recommend skill development priorities for career growth.",
            'networking': "Provide networking advice for job search success."
        }
        
        base_prompt_text = advice_base_prompts.get(advice_type, "Provide general career advice.")

        # Construct the full prompt
        full_prompt_parts = [base_prompt_text]
        if profile_context:
            full_prompt_parts.append(profile_context)
        if context: # User's direct question/context
            full_prompt_parts.append(main_request)
        if rag_context: # RAG context from vector DB
            full_prompt_parts.append(f"\nConsider the following relevant information:\n{rag_context}")

        return "\n\n".join(full_prompt_parts)

    def _get_system_prompt(self, user_profile: Dict[str, Any] = None) -> str:
        """Get system prompt for chat conversations."""
        base_prompt = """You are a helpful AI job search assistant. You help users with:
        - Job search strategies and advice
        - Resume and cover letter optimization
        - Interview preparation
        - Salary negotiation
        - Career development planning
        - Skill development recommendations
        
        Provide practical, actionable advice tailored to each user's situation."""
        
        if user_profile:
            profile_info = f"""
            
            User Context:
            - Experience: {user_profile.get('experience_level', 'Not specified')}
            - Skills: {', '.join(user_profile.get('skills', []))}
            - Target Role: Looking for positions in their field
            """
            base_prompt += profile_info
        
        return base_prompt
    
    def _get_mock_advice(self, advice_type: str, context: str) -> Dict[str, Any]:
        """Return mock advice when OpenAI is not available."""
        mock_advice = {
            'resume': "Focus on quantifiable achievements, use action verbs, and tailor your resume to each job application. Include relevant keywords from the job description.",
            'interview': "Prepare specific examples using the STAR method (Situation, Task, Action, Result). Research the company thoroughly and prepare thoughtful questions.",
            'salary': "Research market rates using sites like Glassdoor and PayScale. Practice your negotiation conversation and focus on your value proposition.",
            'application': "Customize your application for each role, follow up appropriately, and maintain a tracking system for your applications."
        }
        
        return {
            'advice_type': advice_type,
            'advice': mock_advice.get(advice_type, "General career advice: Stay consistent, network actively, and continuously improve your skills."),
            'model_used': 'mock',
            'success': True
        }
    
    def _get_mock_chat_response(self, message: str) -> Dict[str, Any]:
        """Return mock chat response when OpenAI is not available."""
        responses = [
            "I'd be happy to help you with your job search! What specific area would you like assistance with?",
            "That's a great question about job searching. Let me provide some guidance on that topic.",
            "Based on your question, here are some strategies that could help you in your job search.",
            "I understand your concern. Job searching can be challenging, but there are effective approaches we can discuss."
        ]
        
        import random
        return {
            'response': random.choice(responses),
            'model_used': 'mock',
            'success': True
        }
    
    def _get_mock_resume_analysis(self) -> Dict[str, Any]:
        """Return mock resume analysis when OpenAI is not available."""
        return {
            'analysis': """
            Resume Analysis Summary:
            
            Strengths:
            - Clear professional experience section
            - Relevant technical skills listed
            - Education background appropriate for the field
            
            Areas for Improvement:
            - Add quantifiable achievements and metrics
            - Include more industry-specific keywords
            - Strengthen the professional summary section
            
            Recommendations:
            - Use action verbs to start bullet points
            - Tailor the resume for each specific job application
            - Consider adding a projects section to showcase practical skills
            """,
            'model_used': 'mock',
            'success': True
        }


# Utility functions for easy integration
def get_job_advice(user_id: int, advice_type: str, context: str = "") -> Dict[str, Any]:
    """Convenience function for getting job advice."""
    assistant = OpenAIJobAssistant()
    
    # Get user profile if available
    try:
        user = User.objects.get(id=user_id)
        user_profile = {
            'experience_level': getattr(user.profile, 'experience_level', ''),
            'skills': getattr(user.profile, 'skills', []),
            'desired_salary_min': getattr(user.profile, 'desired_salary_min', None),
            'desired_salary_max': getattr(user.profile, 'desired_salary_max', None),
            'location': getattr(user.profile, 'location', ''),
        } if hasattr(user, 'profile') else None
    except (User.DoesNotExist, AttributeError):
        user_profile = None
    
    return assistant.get_job_advice(user_id, advice_type, context, user_profile)


def get_chat_response(user_id: int, message: str, history: List[Dict[str, str]] = None) -> Dict[str, Any]:
    """Convenience function for chat responses."""
    assistant = OpenAIJobAssistant()
    return assistant.chat_response(user_id, message, history)


class EmbeddingService:
    """
    Service for generating text embeddings using OpenAI.
    """
    def __init__(self):
        self.api_key = getattr(settings, 'OPENAI_API_KEY', '')
        self.embedding_model = getattr(settings, 'OPENAI_EMBEDDING_MODEL', 'text-embedding-3-small')
        if self.api_key:
            openai.api_key = self.api_key
        else:
            logger.warning("OpenAI API key not configured for EmbeddingService - mock responses will be used.")

    def _generate_embeddings_mock(self, text_or_texts: List[str]) -> List[List[float]]:
        """Generates mock embeddings."""
        if isinstance(text_or_texts, str):
            num_embeddings = 1
        else:
            num_embeddings = len(text_or_texts)

        mock_embeddings = []
        for i in range(num_embeddings):
            # Dimensions for text-embedding-3-small can be 512, 1536, or 3072. Using 1536 as common.
            # For simplicity, generating a smaller mock vector.
            mock_embeddings.append([float(j % 100) / 100.0 for j in range(1536)])
        logger.info(f"Generated mock embeddings for {num_embeddings} text(s).")
        return mock_embeddings

    def generate_embeddings(self, texts: List[str], model: Optional[str] = None) -> Optional[List[List[float]]]:
        """
        Generate embeddings for a list of texts.

        Args:
            texts: A list of strings to embed.
            model: The OpenAI model to use for embeddings (e.g., 'text-embedding-3-small').
                   Defaults to self.embedding_model.

        Returns:
            A list of embeddings (each embedding is a list of floats), or None if an error occurs.
        """
        if not self.api_key:
            return self._generate_embeddings_mock(texts)

        try:
            model_to_use = model or self.embedding_model
            response = openai.Embedding.create(
                input=texts,
                model=model_to_use
            )
            embeddings = [item['embedding'] for item in response['data']]
            logger.info(f"Successfully generated {len(embeddings)} embeddings using {model_to_use}.")
            return embeddings
        except Exception as e:
            logger.error(f"OpenAI embedding generation failed: {e}")
            return None # Or self._generate_embeddings_mock(texts) as a fallback

    def generate_job_embeddings(self, job) -> Optional[Dict[str, List[float]]]:
        """
        Generates embeddings for a job's title and a combination of title + description.
        Placeholder for now, needs actual Job model fields.
        """
        if not job:
            return None

        texts_to_embed = []
        # Text for title embedding
        if hasattr(job, 'title') and job.title:
            texts_to_embed.append(job.title)
        else: # Need a placeholder if title is missing for consistent list length
            texts_to_embed.append("")

        # Text for combined embedding (title + description)
        combined_text = ""
        if hasattr(job, 'title') and job.title:
            combined_text += job.title
        if hasattr(job, 'description') and job.description:
            combined_text += (" " + job.description if combined_text else job.description)

        if combined_text:
            texts_to_embed.append(combined_text)
        else: # Placeholder if combined is empty
            texts_to_embed.append("")

        if not any(texts_to_embed): # If all are empty strings
            logger.warning(f"No text content found for job ID {getattr(job, 'id', 'N/A')} to generate embeddings.")
            return None

        embeddings_list = self.generate_embeddings(texts_to_embed)

        if embeddings_list and len(embeddings_list) == 2:
            results = {}
            if texts_to_embed[0]: # Only add if title text was present
                 results['title_embedding'] = embeddings_list[0]
            if texts_to_embed[1]: # Only add if combined text was present
                 results['combined_embedding'] = embeddings_list[1]
            return results
        return None

    def generate_user_profile_embeddings(self, user_profile) -> Optional[Dict[str, List[float]]]:
        """
        Generates embeddings for a user profile's key information and skills.
        Placeholder for now, needs actual UserProfile model fields.
        """
        if not user_profile:
            return None

        texts_to_embed = []
        profile_summary_parts = []
        if hasattr(user_profile, 'current_title') and user_profile.current_title:
            profile_summary_parts.append(user_profile.current_title)
        if hasattr(user_profile, 'bio') and user_profile.bio: # Assuming a bio field
            profile_summary_parts.append(user_profile.bio)
        if hasattr(user_profile, 'experience_summary') and user_profile.experience_summary: # Assuming field
            profile_summary_parts.append(user_profile.experience_summary)

        profile_text = ". ".join(filter(None, profile_summary_parts))
        texts_to_embed.append(profile_text if profile_text else "")

        skills_text = ""
        if hasattr(user_profile, 'skills') and isinstance(user_profile.skills, list):
            skills_text = ", ".join(user_profile.skills)
        texts_to_embed.append(skills_text if skills_text else "")

        if not any(texts_to_embed):
            logger.warning(f"No text content found for user profile ID {getattr(user_profile, 'id', 'N/A')} to generate embeddings.")
            return None

        embeddings_list = self.generate_embeddings(texts_to_embed)

        if embeddings_list and len(embeddings_list) == 2:
            results = {}
            if texts_to_embed[0]:
                results['profile_embedding'] = embeddings_list[0]
            if texts_to_embed[1]:
                results['skills_embedding'] = embeddings_list[1]
            return results
        return None


class OpenAIClient:
    """
    Client for specific OpenAI functionalities like analysis and generation,
    distinct from the chat assistant.
    """
    def __init__(self):
        self.api_key = getattr(settings, 'OPENAI_API_KEY', '')
        self.model = getattr(settings, 'OPENAI_MODEL', 'gpt-4') # Default to gpt-4, can be overridden
        if self.api_key:
            openai.api_key = self.api_key
        else:
            logger.warning("OpenAI API key not configured for OpenAIClient - mock responses will be used.")

    def _chat_completion_request(self, system_prompt: str, user_prompt: str, max_tokens: int = 500, temperature: float = 0.7) -> Optional[str]:
        """Helper for making ChatCompletion requests."""
        if not self.api_key:
            logger.warning(f"OpenAIClient: API key not found. Returning mock for: {user_prompt[:50]}...")
            return f"Mock response for: {user_prompt[:100]}"

        try:
            response = openai.ChatCompletion.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                max_tokens=max_tokens,
                temperature=temperature
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"OpenAIClient ChatCompletion error: {e}")
            return None # Or a mock error response

    def analyze_job_match(self, job_description: str, user_profile: str, user_skills: List[str]) -> Optional[Dict[str, Any]]:
        """
        Analyzes how well a user profile and skills match a job description.
        """
        system_prompt = "You are an expert job match analyst. Evaluate the compatibility between the user's profile/skills and the job description. Provide a match score (0-100), a summary of alignment, key strengths, and areas of mismatch or gaps."
        user_prompt = f"""
        Please analyze the match for the following job and user:

        Job Description:
        ---
        {job_description}
        ---

        User Profile Summary:
        ---
        {user_profile}
        ---

        User Skills: {', '.join(user_skills) if user_skills else 'None listed'}

        Provide your analysis in a structured format including:
        1. Overall Match Score (0-100):
        2. Alignment Summary:
        3. Key Strengths for this Role:
        4. Potential Gaps or Mismatches:
        5. Suggested Keywords from JD to Emphasize (if user has related experience):
        """

        if not self.api_key: # Mock response for analyze_job_match
            return {
                "match_score": 75,
                "alignment_summary": "Mock: Good overall alignment with some gaps.",
                "key_strengths": ["Mock: Skill A", "Mock: Experience B"],
                "potential_gaps": ["Mock: Skill C not prominent"],
                "suggested_keywords": ["Mock: Keyword X", "Mock: Keyword Y"],
                "model_used": "mock"
            }

        analysis_text = self._chat_completion_request(system_prompt, user_prompt, max_tokens=1000, temperature=0.5)

        if analysis_text:
            # Basic parsing attempt, could be made more robust
            # For now, returning raw text or a structured dict if simple parsing works
            # A more robust solution would involve asking the LLM for JSON output.
            try:
                score_line = next(line for line in analysis_text.split('\n') if "Overall Match Score" in line)
                score = int(score_line.split(':')[-1].strip().rstrip('%'))
            except (StopIteration, ValueError):
                score = 0 # Default if not found or not parsable

            return {
                "match_score": score,
                "full_analysis_text": analysis_text, # Keep raw text
                "model_used": self.model
            }
        return None


    def generate_cover_letter(self, job_title: str, company_name: str, job_description: str, user_profile: str, user_name: str, template: Optional[str] = None) -> Optional[str]:
        """
        Generates a cover letter for a specific job application.
        """
        system_prompt = "You are an expert cover letter writer. Craft a compelling, professional, and concise cover letter tailored to the job and user. If a template is provided, adapt it while ensuring relevance and personalization."

        user_prompt_parts = [
            f"Please write a cover letter for {user_name} applying for the role of {job_title} at {company_name}.",
            "Base the cover letter on the following information:",
            f"\nUser Profile Summary:\n---\n{user_profile}\n---",
            f"\nJob Description:\n---\n{job_description}\n---"
        ]
        if template:
            user_prompt_parts.append(f"\nAdapt this existing Cover Letter Template if relevant, otherwise create a new one:\n---\n{template}\n---")

        user_prompt_parts.append("\nThe cover letter should highlight the user's key strengths and experiences relevant to the job description. It should be enthusiastic and professional.")
        user_prompt = "\n".join(user_prompt_parts)

        if not self.api_key: # Mock response for generate_cover_letter
            return f"Dear Hiring Manager at {company_name},\n\nThis is a mock cover letter for {job_title}.\n\nSincerely,\n{user_name}"

        return self._chat_completion_request(system_prompt, user_prompt, max_tokens=1000, temperature=0.75)
