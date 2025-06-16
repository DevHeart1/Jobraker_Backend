"""
OpenAI GPT integration service for AI-powered job assistance.
"""

import openai
import logging
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
        user_profile: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Get personalized job advice from AI.
        
        Args:
            user_id: User requesting advice
            advice_type: Type of advice (resume, interview, salary, etc.)
            context: Additional context for the advice
            user_profile: User profile data for personalization
        
        Returns:
            Dictionary containing AI-generated advice
        """
        if not self.api_key:
            return self._get_mock_advice(advice_type, context)
        
        try:
            prompt = self._build_advice_prompt(advice_type, context, user_profile)
            
            response = openai.ChatCompletion.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert career advisor and job search specialist. Provide helpful, actionable advice tailored to the user's situation."
                    },
                    {
                        "role": "user", 
                        "content": prompt
                    }
                ],
                max_tokens=1000,
                temperature=0.7
            )
            
            advice_text = response.choices[0].message.content.strip()
            
            return {
                'advice_type': advice_type,
                'advice': advice_text,
                'model_used': self.model,
                'success': True
            }
            
        except Exception as e:
            logger.error(f"OpenAI API error: {e}")
            return self._get_mock_advice(advice_type, context)
    
    def chat_response(
        self, 
        user_id: int, 
        message: str, 
        conversation_history: List[Dict[str, str]] = None,
        user_profile: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Generate AI chat response for job-related conversations.
        
        Args:
            user_id: User ID for personalization
            message: User's message
            conversation_history: Previous conversation messages
            user_profile: User profile for context
        
        Returns:
            Dictionary containing AI response
        """
        if not self.api_key:
            return self._get_mock_chat_response(message)
        
        try:
            messages = [
                {
                    "role": "system",
                    "content": self._get_system_prompt(user_profile)
                }
            ]
            
            # Add conversation history
            if conversation_history:
                messages.extend(conversation_history[-10:])  # Last 10 messages
            
            # Add current message
            messages.append({
                "role": "user",
                "content": message
            })
            
            response = openai.ChatCompletion.create(
                model=self.model,
                messages=messages,
                max_tokens=800,
                temperature=0.7
            )
            
            ai_response = response.choices[0].message.content.strip()
            
            return {
                'response': ai_response,
                'model_used': self.model,
                'success': True
            }
            
        except Exception as e:
            logger.error(f"OpenAI chat error: {e}")
            return self._get_mock_chat_response(message)
    
    def analyze_resume(
        self, 
        resume_text: str, 
        target_job: str = "",
        user_profile: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Analyze resume and provide optimization suggestions.
        
        Args:
            resume_text: Text content of the resume
            target_job: Target job title or description
            user_profile: User profile for context
        
        Returns:
            Dictionary containing analysis and suggestions
        """
        if not self.api_key:
            return self._get_mock_resume_analysis()
        
        try:
            prompt = f"""
            Please analyze this resume and provide specific improvement suggestions:
            
            Resume Content:
            {resume_text}
            
            Target Job: {target_job or "General software engineering roles"}
            
            Please provide:
            1. Overall assessment and strengths
            2. Specific areas for improvement
            3. Missing skills or experience to highlight
            4. Formatting and structure suggestions
            5. Keywords to include for ATS optimization
            """
            
            response = openai.ChatCompletion.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert resume reviewer and career coach. Provide detailed, actionable feedback to help improve job application success."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                max_tokens=1200,
                temperature=0.7
            )
            
            analysis = response.choices[0].message.content.strip()
            
            return {
                'analysis': analysis,
                'target_job': target_job,
                'model_used': self.model,
                'success': True
            }
            
        except Exception as e:
            logger.error(f"OpenAI resume analysis error: {e}")
            return self._get_mock_resume_analysis()
    
    def _build_advice_prompt(
        self, 
        advice_type: str, 
        context: str, 
        user_profile: Dict[str, Any] = None
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
        
        advice_prompts = {
            'resume': f"Provide specific resume optimization advice for a job seeker. {profile_context} Additional context: {context}",
            'interview': f"Give interview preparation advice and tips. {profile_context} Additional context: {context}",
            'salary': f"Provide salary negotiation advice and market insights. {profile_context} Additional context: {context}",
            'application': f"Give job application strategy advice. {profile_context} Additional context: {context}",
            'skills': f"Recommend skill development priorities for career growth. {profile_context} Additional context: {context}",
            'networking': f"Provide networking advice for job search success. {profile_context} Additional context: {context}"
        }
        
        return advice_prompts.get(advice_type, f"Provide general career advice. {profile_context} Additional context: {context}")
    
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
