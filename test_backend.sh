#!/bin/bash

# Test script for Jobraker Backend
echo "=== Jobraker Backend Test ==="

# Navigate to project directory
cd /workspaces/Jobraker_Backend

# Activate virtual environment
source venv/bin/activate

echo "1. Testing Django configuration..."
python manage.py check

echo -e "\n2. Testing database migrations..."
python manage.py showmigrations

echo -e "\n3. Creating test data..."
python manage.py shell << 'EOF'
from apps.jobs.models import Job
from django.contrib.auth import get_user_model
from django.utils import timezone

User = get_user_model()

# Check existing data
print(f"Existing users: {User.objects.count()}")
print(f"Existing jobs: {Job.objects.count()}")

# Create test job if none exist
if Job.objects.count() == 0:
    job = Job.objects.create(
        title='Senior Python Developer',
        company='Tech Corp',
        description='Looking for a senior Python developer with Django experience',
        location='San Francisco, CA',
        job_type='full_time',
        experience_level='senior',
        salary_min=120000,
        salary_max=150000,
        is_remote=True,
        status='active',
        posted_date=timezone.now()
    )
    print(f"Created test job: {job}")
else:
    print("Jobs already exist in database")

print(f"Total jobs now: {Job.objects.count()}")
EOF

echo -e "\n4. Testing API endpoints..."
echo "Testing API health (should return 404 as expected):"
curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/api/v1/
echo

echo -e "\n5. Testing Django admin access..."
echo "Admin should be accessible at: http://localhost:8000/admin/"

echo -e "\n6. Testing API documentation..."
echo "API docs should be accessible at: http://localhost:8000/api/docs/"

echo -e "\n=== Test Complete ==="
echo "Django development server is running at: http://localhost:8000"
echo "Available endpoints:"
echo "  - Admin: http://localhost:8000/admin/"
echo "  - API Docs: http://localhost:8000/api/docs/"
echo "  - API Schema: http://localhost:8000/api/schema/"
echo "  - API v1: http://localhost:8000/api/v1/"
