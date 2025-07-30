from unittest.mock import MagicMock, patch

import pytest
from django.contrib.auth import get_user_model

from apps.accounts.models import UserProfile
from apps.integrations.tasks import submit_skyvern_application_task
from apps.jobs.models import Job, Application as JobApplication

User = get_user_model()


@pytest.fixture
def user_with_profile():
    """Fixture for a user with a complete profile and resume."""
    user = User.objects.create_user(
        email="test@example.com",
        password="password123",
        first_name="Test",
        last_name="User",
    )
    profile = UserProfile.objects.create(
        user=user,
        phone_number="1234567890",
        # Mock the resume file
    )
    # Mock the file field URL
    profile.resume.url = "/media/resumes/test_resume.pdf"
    profile.save()
    return user


@pytest.fixture
def sample_job():
    """Fixture for a sample job."""
    return Job.objects.create(
        title="Software Engineer",
        description="A great job.",
        company_name="Tech Corp",
        location="Remote",
        application_url="https://apply.example.com/job123",
    )


@pytest.fixture
def job_application(user_with_profile, sample_job):
    """Fixture for a job application instance."""
    return JobApplication.objects.create(
        user=user_with_profile, job=sample_job, status="pending"
    )


@pytest.mark.django_db
@patch("apps.integrations.tasks.SkyvernService")
def test_submit_job_application_with_skyvern_success(
    mock_skyvern_service, user_with_profile, sample_job, job_application
):
    """Test successful submission of a job application via Skyvern."""
    # Mock SkyvernService response
    mock_instance = mock_skyvern_service.return_value
    mock_instance.submit_application.return_value = {
        "success": True,
        "application_id": "skyvern-12345",
    }

    # Mock the monitoring task so it doesn't actually get called
    with patch(
        "apps.integrations.tasks.monitor_skyvern_application_status.delay"
    ) as mock_monitor:
        result = submit_job_application_with_skyvern(
            user_id=str(user_with_profile.id),
            job_id=str(sample_job.id),
            application_id=str(job_application.id),
        )

    # Assertions
    assert result["status"] == "success"
    assert result["skyvern_id"] == "skyvern-12345"

    # Check application status in DB
    job_application.refresh_from_db()
    assert job_application.status == "submitted"
    assert job_application.external_application_id == "skyvern-12345"

    # Check that the monitoring task was called
    mock_monitor.assert_called_once_with(application_id=str(job_application.id))


@pytest.mark.django_db
@patch("apps.integrations.tasks.SkyvernService")
def test_submit_job_application_with_skyvern_failure(
    mock_skyvern_service, user_with_profile, sample_job, job_application
):
    """Test failed submission of a job application via Skyvern."""
    # Mock SkyvernService response for failure
    mock_instance = mock_skyvern_service.return_value
    mock_instance.submit_application.return_value = {
        "success": False,
        "error": "Invalid resume format",
    }

    result = submit_job_application_with_skyvern(
        user_id=str(user_with_profile.id),
        job_id=str(sample_job.id),
        application_id=str(job_application.id),
    )

    # Assertions
    assert result["status"] == "error"
    assert result["reason"] == "Invalid resume format"

    # Check application status in DB
    job_application.refresh_from_db()
    assert job_application.status == "failed"
    assert "Invalid resume format" in job_application.notes


@pytest.mark.django_db
@patch("apps.integrations.tasks.SkyvernService")
def test_monitor_skyvern_application_status_completed(
    mock_skyvern_service, job_application
):
    """Test monitoring a Skyvern application that has completed."""
    job_application.status = "submitted"
    job_application.external_application_id = "skyvern-12345"
    job_application.save()

    # Mock SkyvernService response
    mock_instance = mock_skyvern_service.return_value
    mock_instance.get_application_status.return_value = {
        "success": True,
        "status": "completed",
    }

    result = monitor_skyvern_application_status(application_id=str(job_application.id))

    # Assertions
    assert result["status"] == "updated"
    assert result["new_status"] == "applied"

    job_application.refresh_from_db()
    assert job_application.status == "applied"


@pytest.mark.django_db
@patch("apps.integrations.tasks.SkyvernService")
@patch("apps.integrations.tasks.monitor_skyvern_application_status.retry")
def test_monitor_skyvern_application_status_in_progress(
    mock_retry, mock_skyvern_service, job_application
):
    """Test monitoring a Skyvern application that is still in progress."""
    job_application.status = "submitted"
    job_application.external_application_id = "skyvern-12345"
    job_application.save()

    # Mock SkyvernService response
    mock_instance = mock_skyvern_service.return_value
    mock_instance.get_application_status.return_value = {
        "success": True,
        "status": "in_progress",
    }

    # The task should raise a retry exception
    mock_retry.side_effect = Exception("Task Retry")  # To stop execution after call

    with pytest.raises(Exception, match="Task Retry"):
        monitor_skyvern_application_status(application_id=str(job_application.id))

    # Assert that retry was called
    mock_retry.assert_called_once()

    # Status in DB should not have changed
    job_application.refresh_from_db()
    assert job_application.status == "submitted"
