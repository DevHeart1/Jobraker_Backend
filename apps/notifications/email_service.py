"""
Email service for Jobraker Backend with template support.
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional, Any
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.conf import settings
from django.utils.html import strip_tags
from django.contrib.auth import get_user_model
from apps.jobs.models import Job, Application, JobAlert
from datetime import datetime

logger = logging.getLogger(__name__)
User = get_user_model()


class EmailService:
    """
    Comprehensive email service with template support and notification handling.
    """
    
    def __init__(self):
        self.from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@jobraker.com')
        self.company_name = getattr(settings, 'COMPANY_NAME', 'Jobraker')
        
    def send_email(
        self,
        subject: str,
        template_name: str,
        context: Dict[str, Any],
        recipient_list: List[str],
        from_email: Optional[str] = None,
        attachments: Optional[List[Dict[str, Any]]] = None
    ) -> bool:
        """
        Send email using Django's email backend with HTML template support.
        
        Args:
            subject: Email subject
            template_name: Template name without extension (e.g., 'job_alert')
            context: Template context variables
            recipient_list: List of recipient email addresses
            from_email: Optional custom from email
            attachments: Optional list of attachments
            
        Returns:
            True if email was sent successfully, False otherwise
        """
        try:
            # Add common context variables
            context.update({
                'company_name': self.company_name,
                'site_url': getattr(settings, 'SITE_URL', 'https://jobraker.com'),
                'support_email': getattr(settings, 'SUPPORT_EMAIL', 'support@jobraker.com'),
            })
            
            # Render HTML template
            html_content = render_to_string(f'emails/{template_name}.html', context)
            
            # Create plain text version
            text_content = strip_tags(html_content)
            
            # Create email message
            msg = EmailMultiAlternatives(
                subject=subject,
                body=text_content,
                from_email=from_email or self.from_email,
                to=recipient_list
            )
            
            # Attach HTML version
            msg.attach_alternative(html_content, "text/html")
            
            # Add attachments if provided
            if attachments:
                for attachment in attachments:
                    msg.attach(
                        attachment['filename'],
                        attachment['content'],
                        attachment['mimetype']
                    )
            
            # Send email
            msg.send()
            
            logger.info(f"Email sent successfully to {recipient_list}: {subject}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send email to {recipient_list}: {e}", exc_info=True)
            return False
    
    def send_job_alert_email(self, user: User, jobs: List[Job], alert: JobAlert) -> bool:
        """
        Send job alert email to user with matching jobs.
        """
        if not jobs:
            logger.info(f"No jobs to send in alert for user {user.email}")
            return True
        
        context = {
            'user': user,
            'jobs': jobs[:10],  # Limit to 10 jobs per email
            'alert': alert,
            'total_jobs': len(jobs),
            'view_more_url': f"{settings.SITE_URL}/jobs?alert_id={alert.id}",
        }
        
        subject = f"New Job Alert: {len(jobs)} matching jobs found"
        
        return self.send_email(
            subject=subject,
            template_name='job_alert',
            context=context,
            recipient_list=[user.email]
        )
    
    def send_application_status_update(self, application: Application, old_status: str) -> bool:
        """
        Send application status update email to user.
        """
        status_messages = {
            'submitted': 'Your application has been submitted successfully!',
            'under_review': 'Your application is now under review.',
            'interview_scheduled': 'Congratulations! An interview has been scheduled.',
            'interview_completed': 'Thank you for completing the interview.',
            'offer_extended': 'Great news! You have received a job offer.',
            'hired': 'Congratulations! You have been hired.',
            'rejected': 'Thank you for your interest. Unfortunately, we will not be moving forward.',
            'withdrawn': 'Your application has been withdrawn.',
        }
        
        context = {
            'user': application.user,
            'application': application,
            'job': application.job,
            'status_message': status_messages.get(application.status, 'Your application status has been updated.'),
            'old_status': old_status,
            'application_url': f"{settings.SITE_URL}/applications/{application.id}",
        }
        
        subject = f"Application Update: {application.job.title} at {application.job.company}"
        
        return self.send_email(
            subject=subject,
            template_name='application_status_update',
            context=context,
            recipient_list=[application.user.email]
        )
    
    def send_welcome_email(self, user: User) -> bool:
        """
        Send welcome email to new user.
        """
        context = {
            'user': user,
            'login_url': f"{settings.SITE_URL}/login",
            'profile_url': f"{settings.SITE_URL}/profile",
        }
        
        subject = f"Welcome to {self.company_name}!"
        
        return self.send_email(
            subject=subject,
            template_name='welcome',
            context=context,
            recipient_list=[user.email]
        )
    
    def send_password_reset_email(self, user: User, reset_url: str) -> bool:
        """
        Send password reset email to user.
        """
        context = {
            'user': user,
            'reset_url': reset_url,
        }
        
        subject = f"Password Reset - {self.company_name}"
        
        return self.send_email(
            subject=subject,
            template_name='password_reset',
            context=context,
            recipient_list=[user.email]
        )
    
    def send_job_recommendation_email(self, user: User, recommended_jobs: List[Dict[str, Any]]) -> bool:
        """
        Send job recommendation email to user.
        """
        if not recommended_jobs:
            return True
        
        context = {
            'user': user,
            'recommended_jobs': recommended_jobs[:5],  # Limit to top 5
            'total_recommendations': len(recommended_jobs),
            'recommendations_url': f"{settings.SITE_URL}/recommendations",
        }
        
        subject = f"New Job Recommendations - {len(recommended_jobs)} matches found"
        
        return self.send_email(
            subject=subject,
            template_name='job_recommendations',
            context=context,
            recipient_list=[user.email]
        )
    
    def send_application_follow_up_reminder(self, application: Application) -> bool:
        """
        Send follow-up reminder email for application.
        """
        context = {
            'user': application.user,
            'application': application,
            'job': application.job,
            'days_since_application': (
                application.created_at.date() - application.applied_at.date()
            ).days if application.applied_at else 0,
            'application_url': f"{settings.SITE_URL}/applications/{application.id}",
        }
        
        subject = f"Follow-up Reminder: {application.job.title} at {application.job.company}"
        
        return self.send_email(
            subject=subject,
            template_name='application_follow_up',
            context=context,
            recipient_list=[application.user.email]
        )
    
    def send_bulk_notification(
        self,
        users: List[User],
        subject: str,
        template_name: str,
        context: Dict[str, Any]
    ) -> Dict[str, int]:
        """
        Send bulk notification to multiple users.
        
        Returns:
            Dictionary with success/failure counts
        """
        results = {'success': 0, 'failed': 0}
        
        for user in users:
            user_context = context.copy()
            user_context['user'] = user
            
            success = self.send_email(
                subject=subject,
                template_name=template_name,
                context=user_context,
                recipient_list=[user.email]
            )
            
            if success:
                results['success'] += 1
            else:
                results['failed'] += 1
        
        logger.info(f"Bulk notification sent: {results}")
        return results
    
    def send_test_email(self, recipient_email: str) -> bool:
        """
        Send a test email to verify email service functionality.
        
        Args:
            recipient_email: Email address to send test email to
            
        Returns:
            True if email was sent successfully, False otherwise
        """
        try:
            context = {
                'user_email': recipient_email,
                'test_timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'system_status': 'operational'
            }
            
            return self.send_email(
                subject="Jobraker Email System Test",
                template_name="welcome",  # Using welcome template for test
                context=context,
                recipient_list=[recipient_email]
            )
        except Exception as e:
            logger.error(f"Failed to send test email to {recipient_email}: {e}")
            return False
    
    def _load_template(self, template_name: str, context: Dict[str, Any]) -> str:
        """
        Load and render an email template.
        
        Args:
            template_name: Template name (e.g., 'welcome.html')
            context: Template context variables
            
        Returns:
            Rendered HTML content
        """
        try:
            return render_to_string(f'emails/{template_name}', context)
        except Exception as e:
            logger.error(f"Template loading failed for {template_name}: {str(e)}")
            raise
