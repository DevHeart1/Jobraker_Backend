#!/usr/bin/env python
"""
Setup script for initializing and verifying background task processing.
"""

import os
import sys
import django
from pathlib import Path

# Add the project root to the Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'jobraker.settings.development')
django.setup()

def main():
    """Main setup function for background tasks."""
    print("🚀 Jobraker Background Task Setup")
    print("=" * 50)
    
    # Check system requirements
    check_system_requirements()
    
    # Initialize database
    print("\n📊 Initializing database...")
    initialize_database()
    
    # Test integrations
    print("\n🔗 Testing integrations...")
    test_integrations()
    
    # Setup periodic tasks
    print("\n⏰ Setting up periodic tasks...")
    setup_periodic_tasks()
    
    # Final verification
    print("\n✅ Running final verification...")
    run_verification()
    
    print("\n🎉 Background task setup completed!")
    print_next_steps()

def check_system_requirements():
    """Check if all required services are available."""
    print("Checking system requirements...")
    
    try:
        # Check Redis
        from django.core.cache import cache
        cache.set('setup_test', 'ok', timeout=60)
        result = cache.get('setup_test')
        if result == 'ok':
            print("  ✅ Redis: Connected")
        else:
            print("  ⚠️  Redis: Connection issues")
    except Exception as e:
        print(f"  ❌ Redis: {e}")
    
    try:
        # Check Celery
        from celery import current_app
        inspect = current_app.control.inspect()
        stats = inspect.stats()
        if stats:
            print(f"  ✅ Celery: {len(stats)} worker(s) active")
        else:
            print("  ⚠️  Celery: No workers detected")
    except Exception as e:
        print(f"  ❌ Celery: {e}")
    
    try:
        # Check Database
        from django.contrib.auth import get_user_model
        User = get_user_model()
        user_count = User.objects.count()
        print(f"  ✅ Database: Connected ({user_count} users)")
    except Exception as e:
        print(f"  ❌ Database: {e}")

def initialize_database():
    """Initialize database with required data."""
    try:
        from django.core.management import call_command
        
        # Run migrations
        print("  Running migrations...")
        call_command('migrate', verbosity=0)
        
        # Create superuser if needed
        from django.contrib.auth import get_user_model
        User = get_user_model()
        if not User.objects.filter(is_superuser=True).exists():
            print("  Creating admin user...")
            User.objects.create_superuser(
                email='admin@jobraker.com',
                password='admin123',
                first_name='Admin',
                last_name='User'
            )
        
        print("  ✅ Database initialized")
        
    except Exception as e:
        print(f"  ❌ Database initialization failed: {e}")

def test_integrations():
    """Test integration services."""
    services = [
        ('Adzuna API', 'apps.integrations.services.adzuna', 'AdzunaAPIClient'),
        ('Skyvern API', 'apps.integrations.services.skyvern', 'SkyvernAPIClient'),
        ('OpenAI Service', 'apps.integrations.services.openai', 'EmbeddingService'),
        ('Email Service', 'apps.notifications.email_service', 'EmailService'),
    ]
    
    for service_name, module_name, class_name in services:
        try:
            module = __import__(module_name, fromlist=[class_name])
            service_class = getattr(module, class_name)
            # Try to instantiate
            service_instance = service_class()
            print(f"  ✅ {service_name}: Available")
        except Exception as e:
            print(f"  ⚠️  {service_name}: {e}")

def setup_periodic_tasks():
    """Setup and verify periodic task configuration."""
    try:
        from celery import current_app
        
        # Check if beat schedule is configured
        beat_schedule = current_app.conf.beat_schedule
        
        critical_tasks = [
            'automated-daily-job-sync',
            'process-pending-applications',
            'batch-intelligent-job-matching',
            'process-daily-job-alerts'
        ]
        
        configured_tasks = list(beat_schedule.keys())
        print(f"  📅 Configured periodic tasks: {len(configured_tasks)}")
        
        for task_name in critical_tasks:
            if task_name in configured_tasks:
                print(f"    ✅ {task_name}")
            else:
                print(f"    ⚠️  {task_name} - Not configured")
        
        print(f"  ✅ Periodic tasks configured")
        
    except Exception as e:
        print(f"  ❌ Periodic task setup failed: {e}")

def run_verification():
    """Run final verification tests."""
    try:
        # Test task imports
        from apps.integrations.tasks import (
            fetch_adzuna_jobs,
            automated_daily_job_sync,
            intelligent_job_matching,
            submit_application_via_skyvern
        )
        from apps.notifications.tasks import (
            process_daily_job_alerts,
            send_welcome_email_task
        )
        
        print("  ✅ All critical tasks imported successfully")
        
        # Test a simple task
        from django.contrib.auth import get_user_model
        User = get_user_model()
        
        if User.objects.exists():
            first_user = User.objects.first()
            # Queue a simple task
            result = send_welcome_email_task.delay(first_user.id)
            print(f"  ✅ Test task queued: {result.id}")
        
    except Exception as e:
        print(f"  ❌ Verification failed: {e}")

def print_next_steps():
    """Print next steps for the user."""
    print("\n📋 Next Steps:")
    print("1. Start Celery worker:")
    print("   celery -A jobraker worker --loglevel=info")
    print("\n2. Start Celery beat scheduler:")
    print("   celery -A jobraker beat --loglevel=info")
    print("\n3. Test background tasks:")
    print("   python manage.py test_background_tasks --test-type=all")
    print("\n4. Monitor tasks:")
    print("   - Check logs for task execution")
    print("   - Use Django admin to monitor task results")
    print("   - Check /api/v1/notifications/health/ for system status")
    print("\n🔧 Configuration:")
    print("- Set REDIS_URL in environment variables")
    print("- Configure API keys (ADZUNA_API_KEY, SKYVERN_API_KEY, OPENAI_API_KEY)")
    print("- Set up SMTP for email notifications")

if __name__ == '__main__':
    main()
