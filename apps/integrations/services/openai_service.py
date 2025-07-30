"""
OpenAI GPT integration service for AI-powered job assistance.
"""

import json  # For parsing function call arguments
import logging
from typing import Any, Dict, List, Optional

import openai
from django.conf import settings
from django.contrib.auth import get_user_model

logger = logging.getLogger(__name__)
User = get_user_model()


class OpenAIService:
    """
    OpenAI service for embeddings, chat completions, and AI-powered features.
    """

    def __init__(self):
        self.api_key = getattr(settings, "OPENAI_API_KEY", "")
        self.model = getattr(settings, "OPENAI_MODEL", "gpt-4o-mini")
        self.embedding_model = getattr(
            settings, "OPENAI_EMBEDDING_MODEL", "text-embedding-3-small"
        )

        if self.api_key:
            openai.api_key = self.api_key
        else:
            logger.warning("OpenAI API key not configured - using mock responses")


class OpenAIJobAssistant(OpenAIService):
    """
    AI-powered job assistance using OpenAI GPT.
    Provides job advice, resume optimization, and career guidance.
    """

    def generate_chat_completion(self, messages: List[Dict[str, str]]) -> str:
        """
        Generate a chat completion using OpenAI API.

        Args:
            messages: List of messages in OpenAI format

        Returns:
            The AI assistant's response text
        """
        if not self.api_key:
            return "I'm sorry, but I'm not properly configured to provide responses right now. Please check the OpenAI API configuration."

        try:
            client = openai.OpenAI(api_key=self.api_key)

            response = client.chat.completions.create(
                model=self.model, messages=messages, max_tokens=1500, temperature=0.7
            )

            return response.choices[0].message.content

        except Exception as e:
            logger.error(f"Error generating chat completion: {e}")
            return "I'm sorry, but I encountered an error while processing your request. Please try again."

    def get_job_advice(
        self,
        user_id: int,
        advice_type: str,
        context: str = "",
        user_profile: Dict[str, Any] = None,
        # RAG specific
        query_for_rag: Optional[str] = None,
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
        if user_profile:  # Convert UserProfile object to dict if necessary
            if not isinstance(user_profile, dict):
                # Assuming user_profile might be a UserProfile model instance
                # This part needs to be robust based on what's actually passed.
                try:
                    user_profile_data = {
                        "experience_level": getattr(
                            user_profile, "experience_level", ""
                        ),
                        "skills": list(
                            getattr(user_profile, "skills", [])
                        ),  # Ensure skills are list
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
                query_for_rag=query_for_rag,
            )
            logger.info(
                f"Queued get_openai_job_advice_task with ID: {task.id} for user {user_id}"
            )
            return {"status": "queued", "task_id": task.id}
        except Exception as e:
            logger.error(
                f"Failed to queue get_openai_job_advice_task for user {user_id}: {e}"
            )
            return {"status": "error", "message": "Failed to queue advice task."}

    def chat_response(
        self,
        user_id: int,
        session_id: int,  # Added session_id
        message: str,
        conversation_history: List[Dict[str, str]] = None,
        user_profile: Dict[str, Any] = None,
    ) -> Dict[str, Any]:
        """
        Asynchronously generates AI chat response via Celery.
        Now requires session_id to be passed to the Celery task.
        The actual OpenAI call is made in the Celery task `get_openai_chat_response_task`.
        """
        from apps.integrations.tasks import get_openai_chat_response_task

        user_profile_data = None
        if user_profile:  # Convert UserProfile object to dict
            if not isinstance(user_profile, dict):
                try:
                    user_profile_data = {
                        "experience_level": getattr(
                            user_profile, "experience_level", ""
                        ),
                        "skills": list(getattr(user_profile, "skills", [])),
                    }
                except Exception as e:
                    logger.error(f"Error serializing user_profile for chat task: {e}")
                    user_profile_data = {}
            else:
                user_profile_data = user_profile

        # Moderation of user input before queuing the task
        if self._moderate_text(message):
            logger.warning(
                f"User message flagged by moderation (chat_response service method): '{message[:100]}...'"
            )
            return {
                "status": "error",
                "message": "Input violates content guidelines.",
                "error_code": "flagged_input",
            }

        try:
            task = get_openai_chat_response_task.delay(
                user_id=user_id,
                session_id=session_id,  # Pass session_id
                message=message,
                conversation_history=conversation_history,
                user_profile_data=user_profile_data,
            )
            logger.info(
                f"Queued get_openai_chat_response_task with ID: {task.id} for user {user_id}, session {session_id}"
            )

            # Check if we're in eager mode (for tests) and the task completed immediately
            from django.conf import settings

            if getattr(settings, "CELERY_TASK_ALWAYS_EAGER", False):
                if task.ready():
                    result = task.get()
                    if isinstance(result, dict) and result.get("status"):
                        return {
                            "status": "completed",
                            "task_id": task.id,
                            "response": result.get(
                                "content", "AI response will be here."
                            ),
                        }

            return {"status": "queued", "task_id": task.id}
        except Exception as e:
            logger.error(
                f"Failed to queue get_openai_chat_response_task for user {user_id}, session {session_id}: {e}"
            )
            return {"status": "error", "message": "Failed to queue chat task."}

    def generate_chat_response(self, messages: List[Dict[str, str]], user: User) -> str:
        """
        Generate a chat response for the user based on conversation history.

        Args:
            messages: List of previous messages in the conversation
            user: The user requesting the response

        Returns:
            AI assistant's response
        """
        if not self.api_key:
            return "I'm sorry, but I'm not properly configured to provide responses right now. Please check the OpenAI API configuration."

        try:
            # Build conversation context
            system_message = {
                "role": "system",
                "content": f"""You are a helpful job search assistant for {user.first_name or user.email}. 
                You help users with job searching, resume optimization, interview preparation, and career advice.
                
                Be friendly, professional, and provide actionable advice. If asked about specific jobs, 
                you can suggest they search on the platform. Keep responses concise but helpful.
                
                User context:
                - Name: {user.first_name} {user.last_name}
                - Email: {user.email}
                """,
            }

            # Convert messages to OpenAI format
            formatted_messages = [system_message]
            for msg in messages:
                formatted_messages.append(
                    {
                        "role": "user" if msg["sender"] == "user" else "assistant",
                        "content": msg["content"],
                    }
                )

            client = openai.OpenAI(api_key=self.api_key)

            response = client.chat.completions.create(
                model=self.model,
                messages=formatted_messages,
                max_tokens=800,
                temperature=0.7,
            )

            return response.choices[0].message.content.strip()

        except Exception as e:
            logger.error(f"Error generating chat response: {e}")
            return "I'm sorry, I encountered an error while processing your request. Please try again."

    def _moderate_text(self, text_to_moderate: str) -> bool:
        """
        Checks text against OpenAI's Moderation API.

        Args:
            text_to_moderate: The text string to moderate.

        Returns:
            True if the text is flagged as inappropriate, False otherwise or if an error occurs.
        """
        if (
            not self.api_key or not text_to_moderate
        ):  # Ensure api_key check is relevant for this instance
            return False

        try:
            # Ensure openai client is initialized if not done globally or per-instance
            if openai.api_key is None and self.api_key:
                openai.api_key = self.api_key

            response = openai.Moderation.create(input=text_to_moderate)
            result = response.results[0]
            if result.flagged:
                logger.warning(
                    f"OpenAI Moderation API flagged content: Categories: {[cat for cat, flagged in result.categories.items() if flagged]}"
                )
                return True
            return False
        except Exception as e:
            logger.error(f"OpenAI Moderation API call failed: {e}")
            return False  # Fail safe

    def analyze_resume(
        self,
        resume_text: str,
        target_job: str = "",
        user_profile: Dict[str, Any] = None,  # Should be user_profile_data from task
    ) -> Dict[str, Any]:
        """
        Asynchronously analyzes resume via Celery.
        The actual OpenAI call is made in the Celery task `analyze_openai_resume_task`.
        """
        from apps.integrations.tasks import analyze_openai_resume_task

        user_profile_data = None
        if user_profile:  # Convert UserProfile object to dict
            if not isinstance(user_profile, dict):
                try:
                    user_profile_data = {
                        "experience_level": getattr(
                            user_profile, "experience_level", ""
                        ),
                        "skills": list(getattr(user_profile, "skills", [])),
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
                user_profile_data=user_profile_data,
            )
            logger.info(f"Queued analyze_openai_resume_task with ID: {task.id}")
            return {"status": "queued", "task_id": task.id}
        except Exception as e:
            logger.error(f"Failed to queue analyze_openai_resume_task: {e}")
            return {
                "status": "error",
                "message": "Failed to queue resume analysis task.",
            }

    def _build_advice_prompt(
        self,
        advice_type: str,
        context: str,
        user_profile: Optional[Dict[str, Any]] = None,
        rag_context: str = "",
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
            "resume": "Provide specific resume optimization advice for a job seeker.",
            "interview": "Give interview preparation advice and tips.",
            "salary": "Provide salary negotiation advice and market insights.",
            "application": "Give job application strategy advice.",
            "skills": "Recommend skill development priorities for career growth.",
            "networking": "Provide networking advice for job search success.",
        }

        base_prompt_text = advice_base_prompts.get(
            advice_type, "Provide general career advice."
        )

        # Construct the full prompt
        full_prompt_parts = [base_prompt_text]
        if profile_context:
            full_prompt_parts.append(profile_context)
        if context:  # User's direct question/context
            full_prompt_parts.append(main_request)
        if rag_context:  # RAG context from vector DB
            full_prompt_parts.append(
                f"\nConsider the following relevant information:\n{rag_context}"
            )

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
            "resume": "Focus on quantifiable achievements, use action verbs, and tailor your resume to each job application. Include relevant keywords from the job description.",
            "interview": "Prepare specific examples using the STAR method (Situation, Task, Action, Result). Research the company thoroughly and prepare thoughtful questions.",
            "salary": "Research market rates using sites like Glassdoor and PayScale. Practice your negotiation conversation and focus on your value proposition.",
            "application": "Customize your application for each role, follow up appropriately, and maintain a tracking system for your applications.",
        }

        return {
            "advice_type": advice_type,
            "advice": mock_advice.get(
                advice_type,
                "General career advice: Stay consistent, network actively, and continuously improve your skills.",
            ),
            "model_used": "mock",
            "success": True,
        }

    def _get_mock_chat_response(self, message: str) -> Dict[str, Any]:
        """Return mock chat response when OpenAI is not available."""
        responses = [
            "I'd be happy to help you with your job search! What specific area would you like assistance with?",
            "That's a great question about job searching. Let me provide some guidance on that topic.",
            "Based on your question, here are some strategies that could help you in your job search.",
            "I understand your concern. Job searching can be challenging, but there are effective approaches we can discuss.",
        ]

        import random

        return {
            "response": random.choice(responses),
            "model_used": "mock",
            "success": True,
        }

    def _get_mock_resume_analysis(self) -> Dict[str, Any]:
        """Return mock resume analysis when OpenAI is not available."""
        return {
            "analysis": """
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
            "model_used": "mock",
            "success": True,
        }


class EmbeddingService:
    """
    Service for generating text embeddings using OpenAI.
    """

    def __init__(self):
        self.api_key = getattr(settings, "OPENAI_API_KEY", "")
        self.model = getattr(
            settings, "OPENAI_EMBEDDING_MODEL", "text-embedding-3-small"
        )

        if self.api_key:
            self.client = openai.OpenAI(api_key=self.api_key)
        else:
            self.client = None
            logger.warning(
                "OpenAI API key not configured. EmbeddingService will not work."
            )

    def generate_embeddings(self, texts: List[str]) -> Optional[List[List[float]]]:
        """
        Generates embeddings for a list of texts.

        Args:
            texts: A list of strings to embed.

        Returns:
            A list of embedding vectors, or None if the service is not configured or an error occurs.
        """
        if not self.client:
            logger.error(
                "Cannot generate embeddings: OpenAI client is not initialized."
            )
            return None

        if not texts:
            return []

        try:
            # Replace newlines, which can affect performance
            texts = [text.replace("\n", " ") for text in texts]

            response = self.client.embeddings.create(input=texts, model=self.model)

            embeddings = [item.embedding for item in response.data]
            logger.info(f"Successfully generated {len(embeddings)} embeddings.")
            return embeddings
        except openai.APIError as e:
            logger.error(f"OpenAI API error while generating embeddings: {e}")
        except Exception as e:
            logger.error(
                f"An unexpected error occurred while generating embeddings: {e}"
            )

        return None

    def generate_embedding(self, text: str) -> Optional[List[float]]:
        """
        Generates an embedding for a single text.

        Args:
            text: The string to embed.

        Returns:
            An embedding vector, or None if an error occurs.
        """
        embeddings = self.generate_embeddings([text])
        return embeddings[0] if embeddings else None
