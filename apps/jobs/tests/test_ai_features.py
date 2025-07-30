"""
Tests for AI-powered features in the jobs app.
"""

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.jobs.models import Job
from apps.jobs.services import JobMatchService

User = get_user_model()


@pytest.mark.django_db
def test_find_similar_jobs_api(client: APIClient):
    """
    Test the /api/jobs/{id}/similar/ endpoint.
    """
    # Setup
    user = User.objects.create_user(email="testuser@example.com", password="password")
    client.force_authenticate(user=user)

    job1 = Job.objects.create(
        title="Software Engineer",
        description="Develops software",
        company="Tech Corp",
        combined_embedding=[0.1, 0.2, 0.3] * 512,  # Ensure correct dimension
    )
    job2 = Job.objects.create(
        title="Senior Software Engineer",
        description="Develops complex software",
        company="Tech Corp",
        combined_embedding=[0.11, 0.22, 0.33] * 512,
    )
    job3 = Job.objects.create(
        title="Product Manager",
        description="Manages products",
        company="Biz Inc.",
        combined_embedding=[0.7, 0.8, 0.9] * 512,
    )

    # Mock the service to avoid actual vector search
    class MockJobMatchService:
        def find_similar_jobs(self, job_id, top_n):
            if job_id == job1.id:
                return [{"job": job2, "score": 0.9}]
            return []

    import apps.jobs.views

    apps.jobs.views.JobMatchService = MockJobMatchService

    # Test
    response = client.get(f"/api/jobs/{job1.id}/similar/")

    # Assert
    assert response.status_code == 200
    assert len(response.data) == 1
    assert response.data[0]["title"] == "Senior Software Engineer"
