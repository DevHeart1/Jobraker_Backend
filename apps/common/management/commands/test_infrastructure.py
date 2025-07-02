"""
Django management command to test core infrastructure setup.
"""

from django.core.management.base import BaseCommand
from django.core.management.color import make_style
from django.conf import settings
import sys


class Command(BaseCommand):
    help = 'Test core infrastructure setup and configuration'

    def __init__(self):
        super().__init__()
        self.style = make_style()

    def add_arguments(self, parser):
        parser.add_argument(
            '--check-apis',
            action='store_true',
            help='Test external API connections',
        )
        parser.add_argument(
            '--check-celery',
            action='store_true',
            help='Test Celery configuration',
        )
        parser.add_argument(
            '--check-db',
            action='store_true',
            help='Test database and pgvector setup',
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('🚀 Testing Jobraker Backend Infrastructure'))
        self.stdout.write('')

        # Check basic Django setup
        self.check_django_config()
        
        if options['check_db']:
            self.check_database()
        
        if options['check_celery']:
            self.check_celery()
            
        if options['check_apis']:
            self.check_external_apis()
        
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('✅ Infrastructure test complete!'))

    def check_django_config(self):
        """Check basic Django configuration."""
        self.stdout.write('📋 Checking Django Configuration...')
        
        # Check SECRET_KEY
        if settings.SECRET_KEY and settings.SECRET_KEY != 'django-insecure-change-me-in-production':
            self.stdout.write(self.style.SUCCESS('  ✅ SECRET_KEY configured'))
        else:
            self.stdout.write(self.style.WARNING('  ⚠️ SECRET_KEY using default value'))
        
        # Check DEBUG mode
        if settings.DEBUG:
            self.stdout.write(self.style.WARNING('  ⚠️ DEBUG mode is enabled'))
        else:
            self.stdout.write(self.style.SUCCESS('  ✅ DEBUG mode is disabled'))
        
        # Check installed apps
        required_apps = ['apps.accounts', 'apps.jobs', 'apps.chat', 'apps.integrations', 'apps.common']
        for app in required_apps:
            if app in settings.INSTALLED_APPS:
                self.stdout.write(self.style.SUCCESS(f'  ✅ {app} installed'))
            else:
                self.stdout.write(self.style.ERROR(f'  ❌ {app} missing'))

    def check_database(self):
        """Check database connection and pgvector."""
        self.stdout.write('🗄️ Checking Database Configuration...')
        
        try:
            from django.db import connection
            with connection.cursor() as cursor:
                cursor.execute("SELECT version()")
                version = cursor.fetchone()[0]
                self.stdout.write(self.style.SUCCESS(f'  ✅ PostgreSQL connected: {version[:50]}...'))
                
                # Check for pgvector extension
                try:
                    cursor.execute("SELECT * FROM pg_extension WHERE extname = 'vector'")
                    if cursor.fetchone():
                        self.stdout.write(self.style.SUCCESS('  ✅ pgvector extension installed'))
                    else:
                        self.stdout.write(self.style.WARNING('  ⚠️ pgvector extension not found'))
                        self.stdout.write('     Run: CREATE EXTENSION vector; in your database')
                except Exception as e:
                    self.stdout.write(self.style.WARNING(f'  ⚠️ Could not check pgvector: {e}'))
                    
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'  ❌ Database connection failed: {e}'))

    def check_celery(self):
        """Check Celery configuration."""
        self.stdout.write('⚙️ Checking Celery Configuration...')
        
        try:
            from jobraker.celery import app
            
            # Check if Celery app is configured
            self.stdout.write(self.style.SUCCESS('  ✅ Celery app imported successfully'))
            
            # Check broker connection
            try:
                inspect = app.control.inspect()
                stats = inspect.stats()
                if stats:
                    self.stdout.write(self.style.SUCCESS('  ✅ Celery workers are active'))
                else:
                    self.stdout.write(self.style.WARNING('  ⚠️ No Celery workers found'))
                    self.stdout.write('     Start worker: celery -A jobraker worker -l info')
            except Exception as e:
                self.stdout.write(self.style.WARNING(f'  ⚠️ Could not connect to Celery broker: {e}'))
                self.stdout.write('     Make sure Redis is running')
                
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'  ❌ Celery configuration error: {e}'))

    def check_external_apis(self):
        """Check external API configurations."""
        self.stdout.write('🌐 Checking External API Configuration...')
        
        # Check OpenAI API
        openai_key = getattr(settings, 'OPENAI_API_KEY', '')
        if openai_key:
            self.stdout.write(self.style.SUCCESS('  ✅ OpenAI API key configured'))
            
            # Try a simple API test
            try:
                from apps.integrations.services.openai import OpenAIClient
                client = OpenAIClient()
                # Don't actually call the API in test, just check if it initializes
                self.stdout.write(self.style.SUCCESS('  ✅ OpenAI client initialized'))
            except Exception as e:
                self.stdout.write(self.style.WARNING(f'  ⚠️ OpenAI client error: {e}'))
        else:
            self.stdout.write(self.style.WARNING('  ⚠️ OpenAI API key not configured'))
        
        # Check Adzuna API
        adzuna_id = getattr(settings, 'ADZUNA_APP_ID', '')
        adzuna_key = getattr(settings, 'ADZUNA_API_KEY', '')
        if adzuna_id and adzuna_key:
            self.stdout.write(self.style.SUCCESS('  ✅ Adzuna API credentials configured'))
        else:
            self.stdout.write(self.style.WARNING('  ⚠️ Adzuna API credentials not configured'))
        
        # Check Skyvern API
        skyvern_key = getattr(settings, 'SKYVERN_API_KEY', '')
        if skyvern_key:
            self.stdout.write(self.style.SUCCESS('  ✅ Skyvern API key configured'))
        else:
            self.stdout.write(self.style.WARNING('  ⚠️ Skyvern API key not configured'))
