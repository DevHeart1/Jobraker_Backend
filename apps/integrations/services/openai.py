"""
OpenAI API integration service for AI features.
"""

import openai
import logging
import json
from typing import List, Dict, Any, Optional, Union
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)


class OpenAIClient:
    """
    Client for interacting with OpenAI API.
    Handles embeddings, chat completions, and content generation.
    """
    
    def __init__(self):
        self.api_key = getattr(settings, 'OPENAI_API_KEY', '')
        if self.api_key:
            openai.api_key = self.api_key
        else:
            logger.warning("OpenAI API key not configured")
    
    def _validate_api_key(self):
        """Validate that API key is configured."""
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


class EmbeddingService:
    """
    Service for managing embeddings and semantic search.
    """

    def __init__(self, client: Optional[OpenAIClient] = None):
        self.client = client or OpenAIClient()

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
