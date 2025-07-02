"""
OpenAI API integration service for AI features.
"""

import openai
import logging
import json
import random
import time
from typing import List, Dict, Any, Optional, Union
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

# Import centralized metrics
from apps.common.metrics import (
    OPENAI_API_CALLS_TOTAL,
    OPENAI_API_CALL_DURATION_SECONDS,
    OPENAI_MODERATION_CHECKS_TOTAL,
    OPENAI_MODERATION_FLAGGED_TOTAL,
)


class OpenAIMockService:
    """
    Mock service for development when OpenAI API key is not available.
    """
    
    def generate_embedding(self, text: str, model: str = "text-embedding-3-small") -> List[float]:
        """Generate a mock embedding vector."""
        # Generate consistent mock embedding based on text hash
        import hashlib
        text_hash = hashlib.md5(text.encode()).hexdigest()
        random.seed(text_hash)
        return [random.uniform(-1, 1) for _ in range(1536)]  # OpenAI embedding dimension
    
    def generate_embeddings_batch(self, texts: List[str], model: str = "text-embedding-3-small") -> List[List[float]]:
        """Generate mock embeddings for multiple texts."""
        return [self.generate_embedding(text, model) for text in texts]
    
    def chat_completion(
        self,
        messages: List[Dict[str, str]],
        model: str = "gpt-4o-mini",
        max_tokens: Optional[int] = None,
        temperature: float = 0.7,
        system_prompt: Optional[str] = None,
    ) -> str:
        """Generate a mock chat response."""
        last_message = messages[-1]['content'] if messages else ""
        
        # Simple mock responses based on content
        if 'job' in last_message.lower():
            return "This is a mock response about job opportunities and career advice. In production, this would be powered by GPT-4o-mini."
        elif 'resume' in last_message.lower():
            return "This is a mock resume analysis. In production, this would provide detailed feedback on your resume."
        else:
            return "This is a mock AI assistant response. Configure OPENAI_API_KEY to enable real AI responses."
    
    def moderate_content(self, text: str) -> Dict[str, Any]:
        """Mock content moderation."""
        return {
            'flagged': False,
            'categories': {},
            'category_scores': {},
        }


class OpenAIClient:
    """
    Client for interacting with OpenAI API.
    Handles embeddings, chat completions, and content generation.
    """
    
    def __init__(self):
        self.api_key = getattr(settings, 'OPENAI_API_KEY', '')
        self.use_mock = not self.api_key or getattr(settings, 'USE_OPENAI_MOCK', False)
        
        if self.api_key and not self.use_mock:
            openai.api_key = self.api_key
            logger.info("OpenAI API client initialized with real API key")
        else:
            logger.warning("OpenAI API key not configured - using mock responses")
            self.mock_service = OpenAIMockService()
    
    def _validate_api_key(self):
        """Validate that API key is configured."""
        if self.use_mock:
            return  # Allow mock operation
        if not self.api_key:
            raise ValueError("OpenAI API key not configured")
    
    def generate_embedding(self, text: str, model: str = "text-embedding-3-small") -> List[float]:
        """
        Generate embedding for text using OpenAI API.
        
        Args:
            text: Text to generate embedding for
            model: OpenAI embedding model to use
        
        Returns:
            List of float values representing the embedding
        """
        self._validate_api_key()
        
        # Clean and truncate text if needed
        cleaned_text = text.strip().replace('\n', ' ')[:8000]  # OpenAI token limit
        
        # Check cache first
        cache_key = f"openai_embedding_{hash(cleaned_text)}_{model}"
        cached_embedding = cache.get(cache_key)
        if cached_embedding:
            return cached_embedding
        
        try:
            response = openai.embeddings.create(
                model=model,
                input=cleaned_text,
            )
            
            embedding = response.data[0].embedding
            
            # Cache for 24 hours
            cache.set(cache_key, embedding, 86400)
            
            return embedding
            
        except Exception as e:
            logger.error(f"Error generating embedding: {e}")
            raise
    
    def generate_embeddings_batch(
        self, 
        texts: List[str], 
        model: str = "text-embedding-3-small"
    ) -> List[List[float]]:
        """
        Generate embeddings for multiple texts in batch.
        
        Args:
            texts: List of texts to generate embeddings for
            model: OpenAI embedding model to use
        
        Returns:
            List of embeddings corresponding to input texts
        """
        self._validate_api_key()
        
        # Clean texts
        cleaned_texts = [text.strip().replace('\n', ' ')[:8000] for text in texts]
        
        try:
            response = openai.embeddings.create(
                model=model,
                input=cleaned_texts,
            )
            
            return [item.embedding for item in response.data]
            
        except Exception as e:
            logger.error(f"Error generating batch embeddings: {e}")
            raise
    
    def chat_completion(
        self,
        messages: List[Dict[str, str]],
        model: str = "gpt-4o-mini",
        max_tokens: Optional[int] = None,
        temperature: float = 0.7,
        system_prompt: Optional[str] = None,
    ) -> str:
        """
        Generate chat completion using OpenAI API.
        
        Args:
            messages: List of message objects with 'role' and 'content'
            model: OpenAI model to use
            max_tokens: Maximum tokens in response
            temperature: Sampling temperature
            system_prompt: Optional system prompt to prepend
        
        Returns:
            Generated response text
        """
        self._validate_api_key()
        
        # Prepare messages
        formatted_messages = []
        
        if system_prompt:
            formatted_messages.append({
                "role": "system",
                "content": system_prompt
            })
        
        formatted_messages.extend(messages)
        
        try:
            response = openai.chat.completions.create(
                model=model,
                messages=formatted_messages,
                max_tokens=max_tokens,
                temperature=temperature,
            )
            
            return response.choices[0].message.content
            
        except Exception as e:
            logger.error(f"Error generating chat completion: {e}")
            raise
    
    def analyze_job_match(
        self,
        job_description: str,
        user_profile: str,
        user_skills: List[str],
    ) -> Dict[str, Any]:
        """
        Analyze how well a user matches a job using AI.
        
        Args:
            job_description: Job description text
            user_profile: User profile/resume text
            user_skills: List of user skills
        
        Returns:
            Dictionary with match analysis
        """
        system_prompt = """
        You are an expert job matching AI. Analyze how well a candidate matches a job posting.
        
        Provide a response in the following JSON format:
        {
            "match_score": 0.85,
            "match_reasons": [
                "Strong technical skills alignment",
                "Relevant experience in similar role"
            ],
            "missing_skills": [
                "Docker",
                "Kubernetes"
            ],
            "suggestions": [
                "Highlight your Python experience more prominently",
                "Consider learning containerization technologies"
            ]
        }
        
        The match_score should be between 0.0 and 1.0.
        """
        
        user_message = f"""
        Job Description:
        {job_description[:2000]}
        
        User Profile:
        {user_profile[:1000]}
        
        User Skills:
        {', '.join(user_skills)}
        
        Please analyze the match between this user and job.
        """
        
        try:
            response = self.chat_completion(
                messages=[{"role": "user", "content": user_message}],
                system_prompt=system_prompt,
                temperature=0.3,  # Lower temperature for more consistent analysis
            )
            
            # Parse JSON response
            analysis = json.loads(response)
            
            # Validate structure
            required_keys = ['match_score', 'match_reasons', 'missing_skills', 'suggestions']
            if not all(key in analysis for key in required_keys):
                raise ValueError("Invalid analysis response structure")
            
            # Ensure match_score is in valid range
            analysis['match_score'] = max(0.0, min(1.0, float(analysis['match_score'])))
            
            return analysis
            
        except (json.JSONDecodeError, ValueError) as e:
            logger.error(f"Error parsing job match analysis: {e}")
            # Return default analysis
            return {
                "match_score": 0.5,
                "match_reasons": ["Unable to analyze match"],
                "missing_skills": [],
                "suggestions": ["Please review the job requirements manually"]
            }
    
    def generate_cover_letter(
        self,
        job_title: str,
        company_name: str,
        job_description: str,
        user_profile: str,
        user_name: str,
        template: Optional[str] = None,
    ) -> str:
        """
        Generate a personalized cover letter.
        
        Args:
            job_title: Title of the job
            company_name: Name of the company
            job_description: Job description
            user_profile: User profile/experience
            user_name: User's full name
            template: Optional cover letter template
        
        Returns:
            Generated cover letter text
        """
        system_prompt = """
        You are a professional career counselor helping write cover letters.
        Create a compelling, personalized cover letter that:
        1. Shows genuine interest in the specific role and company
        2. Highlights relevant experience and skills
        3. Demonstrates value the candidate can bring
        4. Maintains a professional yet personal tone
        5. Is concise (2-3 paragraphs)
        
        Do not include placeholder text or generic statements.
        """
        
        user_message = f"""
        Please write a cover letter for:
        
        Job Title: {job_title}
        Company: {company_name}
        Candidate: {user_name}
        
        Job Description:
        {job_description[:1500]}
        
        Candidate Profile:
        {user_profile[:1000]}
        
        {"Base it on this template structure: " + template if template else ""}
        """
        
        try:
            cover_letter = self.chat_completion(
                messages=[{"role": "user", "content": user_message}],
                system_prompt=system_prompt,
                temperature=0.8,  # Higher temperature for creativity
                max_tokens=500,
            )
            
            return cover_letter
            
        except Exception as e:
            logger.error(f"Error generating cover letter: {e}")
            return f"Dear {company_name} Hiring Manager,\n\nI am writing to express my interest in the {job_title} position. Please find my resume attached for your review.\n\nSincerely,\n{user_name}"
    
    def generate_job_suggestions(
        self,
        user_profile: str,
        user_skills: List[str],
        preferences: Dict[str, Any],
    ) -> List[str]:
        """
        Generate job search suggestions based on user profile.
        
        Args:
            user_profile: User's professional profile
            user_skills: List of user skills
            preferences: User preferences (location, salary, etc.)
        
        Returns:
            List of job search suggestions
        """
        system_prompt = """
        You are a career advisor providing job search suggestions.
        Based on the user's profile, skills, and preferences, suggest:
        1. Specific job titles to search for
        2. Companies that might be a good fit
        3. Skills to highlight or develop
        4. Industries to consider
        
        Provide 5-8 specific, actionable suggestions.
        """
        
        user_message = f"""
        User Profile:
        {user_profile[:1000]}
        
        Skills:
        {', '.join(user_skills)}
        
        Preferences:
        {json.dumps(preferences, indent=2)[:500]}
        
        Please provide job search suggestions.
        """
        
        try:
            response = self.chat_completion(
                messages=[{"role": "user", "content": user_message}],
                system_prompt=system_prompt,
                temperature=0.8,
            )
            
            # Split response into suggestions
            suggestions = [
                suggestion.strip()
                for suggestion in response.split('\n')
                if suggestion.strip() and not suggestion.strip().startswith('#')
            ]
            
            return suggestions[:8]  # Limit to 8 suggestions
            
        except Exception as e:
            logger.error(f"Error generating job suggestions: {e}")
            return ["Search for roles matching your current experience level"]

    def generate_interview_questions(
        self,
        job_title: str,
        job_description: str,
        num_questions: int = 10,
        question_types: Optional[List[str]] = None,
        user_profile_summary: Optional[str] = None # Optional for future personalization
    ) -> List[Dict[str, str]]:
        """
        Generates interview questions for a given job title and description using OpenAI.

        Args:
            job_title: The title of the job.
            job_description: The description of the job.
            num_questions: The desired number of questions.
            question_types: Optional list of question types to generate (e.g., "technical", "behavioral").
            user_profile_summary: Optional summary of the user's profile for personalized questions.

        Returns:
            A list of dictionaries, where each dictionary has "type" and "question" keys.
            Returns an empty list if generation fails or an error occurs.
        """
        self._validate_api_key()

        prompt_lines = [
            "You are an expert interviewer and career coach.",
            f"Generate {num_questions} insightful interview questions for a candidate applying for the role of '{job_title}'.",
            "Base the questions primarily on the following job description:",
            "--- JOB DESCRIPTION START ---",
            job_description[:3000], # Truncate to avoid excessive length
            "--- JOB DESCRIPTION END ---",
        ]

        if question_types:
            types_str = ", ".join(question_types)
            prompt_lines.append(f"Please include a mix of question types, focusing on: {types_str}.")
        else:
            prompt_lines.append("Please include a mix of question types, such as behavioral, technical (if applicable to the role), situational, and questions to assess cultural fit.")

        if user_profile_summary:
            prompt_lines.extend([
                "\nOptionally, consider the following candidate profile summary to tailor some questions:",
                "--- CANDIDATE PROFILE START ---",
                user_profile_summary[:1000],
                "--- CANDIDATE PROFILE END ---"
            ])

        prompt_lines.extend([
            "\nReturn your response as a JSON list of objects. Each object should have exactly two keys: 'type' (a string describing the question category, e.g., 'Behavioral', 'Technical', 'Situational', 'Role-specific', 'Cultural Fit') and 'question' (the interview question itself).",
            "Ensure the JSON is well-formed.",
            "Example format: [{\"type\": \"Behavioral\", \"question\": \"Describe a challenging project you worked on.\"}, ...]"
        ])

        system_prompt = "\n".join(prompt_lines)
        user_message_content = f"Please generate the {num_questions} interview questions for the job title '{job_title}' as per the detailed instructions provided in the system prompt."

        try:
            # Using the existing chat_completion method from this class
            response_text = self.chat_completion(
                messages=[{"role": "user", "content": user_message_content}],
                system_prompt=system_prompt, # The detailed instructions are now the system prompt
                model="gpt-4o-mini", # Or a more capable model if needed for better JSON generation
                temperature=0.6, # Moderate temperature for some creativity but structured output
                max_tokens=1500  # Adjust based on expected number of questions and detail
            )

            # Attempt to parse the JSON response
            # The LLM might sometimes return text before or after the JSON block.
            # Try to extract JSON part.
            json_start_index = response_text.find('[')
            json_end_index = response_text.rfind(']')

            if json_start_index != -1 and json_end_index != -1 and json_end_index > json_start_index:
                json_str = response_text[json_start_index : json_end_index+1]
                try:
                    questions = json.loads(json_str)
                    if isinstance(questions, list) and all(isinstance(q, dict) and 'type' in q and 'question' in q for q in questions):
                        return questions
                    else:
                        logger.warning(f"OpenAI response for interview questions was valid JSON but not in the expected format: {json_str}")
                        # Fallback: Try to parse as one question if it's a simple string response not matching JSON list
                        return [{"type": "general", "question": response_text.strip()}] if len(response_text.strip()) > 10 else []


                except json.JSONDecodeError as je:
                    logger.error(f"Failed to decode JSON response from OpenAI for interview questions: {je}. Response was: {json_str}")
                    # Fallback: Try to return the raw response as a single question if it looks like one
                    return [{"type": "general", "question": response_text.strip()}] if len(response_text.strip()) > 10 else []
            else:
                logger.warning(f"Could not find JSON list in OpenAI response for interview questions: {response_text}")
                return [{"type": "general", "question": response_text.strip()}] if len(response_text.strip()) > 10 else []


        except Exception as e:
            logger.error(f"Error generating interview questions via OpenAI: {e}")
            return []


class EmbeddingService:
    """
    Service for managing embeddings and semantic search.
    """

    def __init__(self, client: Optional[OpenAIClient] = None):
        self.client = client or OpenAIClient()
        self.embedding_model = getattr(settings, 'OPENAI_EMBEDDING_MODEL', 'text-embedding-3-small')

    def generate_embeddings(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for a list of texts.
        
        Args:
            texts: List of texts to generate embeddings for
        
        Returns:
            List of embeddings
        """
        if not texts:
            return []
        
        try:
            return self.client.generate_embeddings_batch(texts, model=self.embedding_model)
        except Exception as e:
            logger.error(f"Error generating embeddings: {e}")
            return []

    def generate_job_embeddings(self, job) -> Dict[str, List[float]]:
        """
        Generate embeddings for a job posting.
        
        Args:
            job: Job model instance
        
        Returns:
            Dictionary with different embedding types
        """
        try:
            # Generate embeddings for different job components
            title_embedding = self.client.generate_embedding(job.title)
            
            # Combine title and description for comprehensive embedding
            combined_text = f"{job.title}. {job.description[:1000]}"
            if job.required_skills:
                combined_text += f" Required skills: {', '.join(job.required_skills)}"
            
            combined_embedding = self.client.generate_embedding(combined_text)
            
            return {
                'title_embedding': title_embedding,
                'combined_embedding': combined_embedding,
            }
            
        except Exception as e:
            logger.error(f"Error generating job embeddings for job {job.id}: {e}")
            return {}
    
    def generate_user_profile_embeddings(self, user_profile) -> Dict[str, List[float]]:
        """
        Generate embeddings for user profile.
        
        Args:
            user_profile: UserProfile model instance
        
        Returns:
            Dictionary with profile embeddings
        """
        try:
            # Create profile text
            profile_text = f"{user_profile.current_title or ''} "
            profile_text += f"Experience: {user_profile.experience_level}. "
            
            if user_profile.skills:
                profile_text += f"Skills: {', '.join(user_profile.skills)}. "
            
            if user_profile.industries:
                profile_text += f"Industries: {', '.join(user_profile.industries)}."
            
            profile_embedding = self.client.generate_embedding(profile_text)
            
            # Skills-only embedding
            skills_text = ', '.join(user_profile.skills) if user_profile.skills else ""
            skills_embedding = self.client.generate_embedding(skills_text) if skills_text else []
            
            return {
                'profile_embedding': profile_embedding,
                'skills_embedding': skills_embedding,
            }
            
        except Exception as e:
            logger.error(f"Error generating profile embeddings for user {user_profile.user.id}: {e}")
            return {}
    
    def calculate_similarity_score(
        self,
        embedding1: List[float],
        embedding2: List[float]
    ) -> float:
        """
        Calculate cosine similarity between two embeddings.
        
        Args:
            embedding1: First embedding vector
            embedding2: Second embedding vector
        
        Returns:
            Similarity score between 0 and 1
        """
        try:
            import numpy as np
            
            # Convert to numpy arrays
            vec1 = np.array(embedding1)
            vec2 = np.array(embedding2)
            
            # Calculate cosine similarity
            dot_product = np.dot(vec1, vec2)
            norm1 = np.linalg.norm(vec1)
            norm2 = np.linalg.norm(vec2)
            
            if norm1 == 0 or norm2 == 0:
                return 0.0
            
            similarity = dot_product / (norm1 * norm2)
            
            # Convert to 0-1 range (cosine similarity is -1 to 1)
            return (similarity + 1) / 2
            
        except Exception as e:
            logger.error(f"Error calculating similarity: {e}")
            return 0.0
