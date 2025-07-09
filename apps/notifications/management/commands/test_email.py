"""
Management command to test the email system.
"""

from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from apps.notifications.email_service import EmailService
from apps.notifications.tasks import (
    send_welcome_email_task,
    send_job_recommendations_task,
    process_daily_job_alerts
)

User = get_user_model()


class Command(BaseCommand):
    help = 'Test email functionality'

    def add_arguments(self, parser):
        parser.add_argument(
            '--test-type',
            type=str,
            choices=['welcome', 'recommendations', 'job-alerts', 'all'],
            default='all',
            help='Type of email test to run'
        )
        parser.add_argument(
            '--user-email',
            type=str,
            help='Email address of test user'
        )

    def handle(self, *args, **options):
        test_type = options['test_type']
        user_email = options.get('user_email')
        
        # Get or create test user
        if user_email:
            try:
                user = User.objects.get(email=user_email)
            except User.DoesNotExist:
                self.stdout.write(
                    self.style.ERROR(f'User with email {user_email} not found')
                )
                return
        else:
            user = User.objects.first()
            if not user:
                self.stdout.write(
                    self.style.ERROR('No users found in database')
                )
                return
        
        email_service = EmailService()
        
        if test_type in ['welcome', 'all']:
            self.stdout.write('Testing welcome email...')
            success = email_service.send_welcome_email(user)
            if success:
                self.stdout.write(
                    self.style.SUCCESS('Welcome email sent successfully')
                )
            else:
                self.stdout.write(
                    self.style.ERROR('Failed to send welcome email')
                )
        
        if test_type in ['recommendations', 'all']:
            self.stdout.write('Testing job recommendations email...')
            # Mock recommendations data
            mock_recommendations = [
                {
                    'id': 1,
                    'title': 'Senior Python Developer',
                    'company': 'Tech Corp',
                    'location': 'San Francisco, CA',
                    'salary_min': 120000,
                    'salary_max': 150000,
                    'job_type': 'full-time',
                    'description': 'Join our team as a Senior Python Developer...',
                    'similarity_score': 92.5
                },
                {
                    'id': 2,
                    'title': 'Full Stack Engineer',
                    'company': 'StartupXYZ',
                    'location': 'New York, NY',
                    'salary_min': 100000,
                    'salary_max': 130000,
                    'job_type': 'full-time',
                    'description': 'We are looking for a Full Stack Engineer...',
                    'similarity_score': 88.2
                }
            ]
            
            success = email_service.send_job_recommendation_email(
                user=user,
                recommended_jobs=mock_recommendations
            )
            if success:
                self.stdout.write(
                    self.style.SUCCESS('Job recommendations email sent successfully')
                )
            else:
                self.stdout.write(
                    self.style.ERROR('Failed to send job recommendations email')
                )
        
        if test_type in ['job-alerts', 'all']:
            self.stdout.write('Testing job alerts processing...')
            try:
                process_daily_job_alerts.delay()
                self.stdout.write(
                    self.style.SUCCESS('Job alerts processing task queued')
                )
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f'Failed to queue job alerts task: {e}')
                )
        
        self.stdout.write(
            self.style.SUCCESS('Email testing completed')
        )
