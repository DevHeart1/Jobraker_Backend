"""
Management command to test and initialize background task processing.
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from django.contrib.auth import get_user_model
import logging

logger = logging.getLogger(__name__)
User = get_user_model()


class Command(BaseCommand):
    help = 'Test and initialize background task processing'

    def add_arguments(self, parser):
        parser.add_argument(
            '--test-type',
            type=str,
            default='all',
            choices=['all', 'jobs', 'ai', 'notifications', 'skyvern', 'health'],
            help='Type of background tasks to test'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be done without actually executing tasks'
        )

    def handle(self, *args, **options):
        test_type = options['test_type']
        dry_run = options['dry_run']
        
        self.stdout.write(
            self.style.SUCCESS(f'Testing background tasks: {test_type}')
        )
        
        if dry_run:
            self.stdout.write(
                self.style.WARNING('DRY RUN MODE - No tasks will be executed')
            )

        try:
            if test_type in ['all', 'jobs']:
                self.test_job_processing(dry_run)
            
            if test_type in ['all', 'ai']:
                self.test_ai_processing(dry_run)
            
            if test_type in ['all', 'notifications']:
                self.test_notification_processing(dry_run)
            
            if test_type in ['all', 'skyvern']:
                self.test_skyvern_processing(dry_run)
            
            if test_type in ['all', 'health']:
                self.test_health_checks()
            
            self.stdout.write(
                self.style.SUCCESS('Background task testing completed successfully!')
            )
            
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Error during testing: {str(e)}')
            )
            raise

    def test_job_processing(self, dry_run=False):
        """Test job fetching and processing tasks."""
        self.stdout.write('\n=== Testing Job Processing Tasks ===')
        
        try:
            from apps.integrations.tasks import (
                fetch_adzuna_jobs, 
                automated_daily_job_sync,
                cleanup_old_jobs,
                update_job_statistics
            )
            
            if not dry_run:
                # Test Adzuna job fetching
                self.stdout.write('Testing Adzuna job fetch...')
                result = fetch_adzuna_jobs.delay(['software'], max_days_old=1)
                self.stdout.write(f'Queued Adzuna task: {result.id}')
                
                # Test statistics update
                self.stdout.write('Testing job statistics update...')
                stats_result = update_job_statistics.delay()
                self.stdout.write(f'Queued statistics task: {stats_result.id}')
                
            else:
                self.stdout.write('Would test: Adzuna job fetch, statistics update')
                
            self.stdout.write(self.style.SUCCESS('✓ Job processing tasks available'))
            
        except ImportError as e:
            self.stdout.write(self.style.ERROR(f'✗ Missing job processing tasks: {e}'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'✗ Error testing job tasks: {e}'))

    def test_ai_processing(self, dry_run=False):
        """Test AI and embedding processing tasks."""
        self.stdout.write('\n=== Testing AI Processing Tasks ===')
        
        try:
            from apps.integrations.tasks import (
                generate_job_embeddings_and_ingest_for_rag,
                generate_user_profile_embeddings,
                intelligent_job_matching,
                batch_generate_job_embeddings,
                batch_generate_user_embeddings
            )
            
            if not dry_run:
                # Test batch embedding generation
                self.stdout.write('Testing batch embedding generation...')
                job_embeddings_result = batch_generate_job_embeddings.delay(limit=5)
                user_embeddings_result = batch_generate_user_embeddings.delay(limit=5)
                
                self.stdout.write(f'Queued job embeddings task: {job_embeddings_result.id}')
                self.stdout.write(f'Queued user embeddings task: {user_embeddings_result.id}')
                
                # Test intelligent job matching for first user
                first_user = User.objects.first()
                if first_user:
                    matching_result = intelligent_job_matching.delay(first_user.id)
                    self.stdout.write(f'Queued job matching task: {matching_result.id}')
                
            else:
                self.stdout.write('Would test: Embedding generation, job matching')
                
            self.stdout.write(self.style.SUCCESS('✓ AI processing tasks available'))
            
        except ImportError as e:
            self.stdout.write(self.style.ERROR(f'✗ Missing AI processing tasks: {e}'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'✗ Error testing AI tasks: {e}'))

    def test_notification_processing(self, dry_run=False):
        """Test notification and email processing tasks."""
        self.stdout.write('\n=== Testing Notification Processing Tasks ===')
        
        try:
            from apps.notifications.tasks import (
                process_daily_job_alerts,
                process_weekly_job_alerts,
                send_weekly_job_recommendations,
                send_application_follow_up_reminders,
                send_welcome_email_task
            )
            
            if not dry_run:
                # Test email processing
                self.stdout.write('Testing notification processing...')
                
                # Test welcome email for first user
                first_user = User.objects.first()
                if first_user:
                    welcome_result = send_welcome_email_task.delay(first_user.id)
                    self.stdout.write(f'Queued welcome email task: {welcome_result.id}')
                
                # Test alert processing (dry run style)
                alerts_result = process_daily_job_alerts.delay()
                self.stdout.write(f'Queued daily alerts task: {alerts_result.id}')
                
            else:
                self.stdout.write('Would test: Welcome emails, job alerts, recommendations')
                
            self.stdout.write(self.style.SUCCESS('✓ Notification processing tasks available'))
            
        except ImportError as e:
            self.stdout.write(self.style.ERROR(f'✗ Missing notification tasks: {e}'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'✗ Error testing notification tasks: {e}'))

    def test_skyvern_processing(self, dry_run=False):
        """Test Skyvern automation tasks."""
        self.stdout.write('\n=== Testing Skyvern Processing Tasks ===')
        
        try:
            from apps.integrations.tasks import (
                submit_application_via_skyvern,
                monitor_skyvern_task,
                process_pending_applications
            )
            
            if not dry_run:
                # Test pending applications processing
                self.stdout.write('Testing Skyvern application processing...')
                skyvern_result = process_pending_applications.delay()
                self.stdout.write(f'Queued Skyvern processing task: {skyvern_result.id}')
                
            else:
                self.stdout.write('Would test: Application automation, task monitoring')
                
            self.stdout.write(self.style.SUCCESS('✓ Skyvern processing tasks available'))
            
        except ImportError as e:
            self.stdout.write(self.style.ERROR(f'✗ Missing Skyvern tasks: {e}'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'✗ Error testing Skyvern tasks: {e}'))

    def test_health_checks(self):
        """Test system health checks."""
        self.stdout.write('\n=== Testing System Health ===')
        
        try:
            # Test Celery connectivity
            from celery import current_app
            
            inspect = current_app.control.inspect()
            stats = inspect.stats()
            
            if stats:
                worker_count = len(stats)
                self.stdout.write(f'✓ Celery workers available: {worker_count}')
                for worker_name in stats.keys():
                    self.stdout.write(f'  - {worker_name}')
            else:
                self.stdout.write(self.style.WARNING('⚠ No Celery workers detected'))
                self.stdout.write('  Start workers with: celery -A jobraker worker --loglevel=info')
            
            # Test Redis connectivity
            try:
                from django.core.cache import cache
                cache.set('health_test', 'ok', timeout=60)
                result = cache.get('health_test')
                if result == 'ok':
                    self.stdout.write('✓ Redis/Cache connectivity working')
                else:
                    self.stdout.write(self.style.WARNING('⚠ Redis/Cache connectivity issues'))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'✗ Redis/Cache error: {e}'))
            
            # Test database connectivity
            try:
                user_count = User.objects.count()
                self.stdout.write(f'✓ Database connectivity working ({user_count} users)')
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'✗ Database error: {e}'))
            
            # Test service imports
            services_to_test = [
                ('apps.integrations.services.adzuna', 'AdzunaAPIClient'),
                ('apps.integrations.services.skyvern', 'SkyvernAPIClient'),
                ('apps.integrations.services.openai', 'EmbeddingService'),
                ('apps.notifications.email_service', 'EmailService'),
            ]
            
            for module_name, class_name in services_to_test:
                try:
                    module = __import__(module_name, fromlist=[class_name])
                    service_class = getattr(module, class_name)
                    self.stdout.write(f'✓ {class_name} available')
                except ImportError as e:
                    self.stdout.write(self.style.ERROR(f'✗ {class_name} import error: {e}'))
                except Exception as e:
                    self.stdout.write(self.style.WARNING(f'⚠ {class_name} issue: {e}'))
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Health check error: {e}'))

    def show_task_summary(self):
        """Show summary of available background tasks."""
        self.stdout.write('\n=== Background Task Summary ===')
        
        task_categories = {
            'Job Processing': [
                'fetch_adzuna_jobs',
                'automated_daily_job_sync',
                'cleanup_old_jobs',
                'update_job_statistics'
            ],
            'AI Processing': [
                'generate_job_embeddings_and_ingest_for_rag',
                'generate_user_profile_embeddings',
                'intelligent_job_matching',
                'batch_generate_job_embeddings',
                'batch_generate_user_embeddings'
            ],
            'Notifications': [
                'process_daily_job_alerts',
                'process_weekly_job_alerts',
                'send_weekly_job_recommendations',
                'send_application_follow_up_reminders',
                'send_welcome_email_task'
            ],
            'Automation': [
                'submit_application_via_skyvern',
                'monitor_skyvern_task',
                'process_pending_applications'
            ]
        }
        
        for category, tasks in task_categories.items():
            self.stdout.write(f'\n{category}:')
            for task in tasks:
                self.stdout.write(f'  • {task}')
