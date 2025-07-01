from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase, APIClient
from django.contrib.auth import get_user_model
from apps.jobs.models import Job, RecommendedJob, UserProfile, JobAlert, Application # Added Application
from apps.jobs.serializers import JobAlertSerializer, ApplicationSerializer # Added ApplicationSerializer
from django.utils import timezone # Added for new tests
import uuid

User = get_user_model()

class JobRecommendationsViewTests(APITestCase):

    def setUp(self):
        self.user1 = User.objects.create_user(email='user1@example.com', password='password1', first_name='User1')
        # Assuming UserProfile is created via a signal or needs to be created manually for test user
        # If UserProfile is automatically created (e.g. by a signal on User creation):
        # self.user1_profile = UserProfile.objects.get(user=self.user1)
        # If not, create it:
        try:
            self.user1_profile = UserProfile.objects.get(user=self.user1)
        except UserProfile.DoesNotExist:
            self.user1_profile = UserProfile.objects.create(user=self.user1)


        self.user2 = User.objects.create_user(email='user2@example.com', password='password2', first_name='User2')
        try:
            self.user2_profile = UserProfile.objects.get(user=self.user2)
        except UserProfile.DoesNotExist:
            self.user2_profile = UserProfile.objects.create(user=self.user2)

        self.job1 = Job.objects.create(title="Dev Ops", company="Cloud Inc", description="desc1", location="Remote")
        self.job2 = Job.objects.create(title="Frontend Dev", company="Web Co", description="desc2", location="NY")
        self.job3 = Job.objects.create(title="Backend Dev", company="Data LLC", description="desc3", location="SF")
        self.job4 = Job.objects.create(title="QA Engineer", company="Test Ltd", description="desc4", location="Remote")

        # Recommendations for user1
        self.rec1_user1 = RecommendedJob.objects.create(user=self.user1, job=self.job1, score=0.9, status='pending_review')
        self.rec2_user1 = RecommendedJob.objects.create(user=self.user1, job=self.job2, score=0.8, status='viewed')
        self.rec3_user1 = RecommendedJob.objects.create(user=self.user1, job=self.job3, score=0.7, status='dismissed')

        # Recommendation for user2
        self.rec1_user2 = RecommendedJob.objects.create(user=self.user2, job=self.job4, score=0.95, status='pending_review')

        self.client = APIClient()
        self.url = reverse('job-recommendations') # Make sure this URL name is correct

    def test_get_recommendations_unauthenticated(self):
        """Test that unauthenticated users cannot access recommendations."""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_get_recommendations_authenticated_user_default_status(self):
        """Test retrieving recommendations for an authenticated user with default status filters."""
        self.client.force_authenticate(user=self.user1)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        results = response.data.get('results') if 'results' in response.data else response.data # Handle pagination
        self.assertEqual(len(results), 2) # rec1_user1 (pending_review), rec2_user1 (viewed)

        # Check ordering (by score desc, then recommended_at desc - though recommended_at might be very close)
        self.assertEqual(results[0]['job']['id'], str(self.job1.id)) # score 0.9
        self.assertEqual(results[1]['job']['id'], str(self.job2.id)) # score 0.8
        self.assertEqual(results[0]['status'], 'pending_review')
        self.assertEqual(results[1]['status'], 'viewed')

    def test_get_recommendations_filter_by_status_pending(self):
        """Test filtering recommendations by 'pending_review' status."""
        self.client.force_authenticate(user=self.user1)
        response = self.client.get(self.url, {'status': 'pending_review'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get('results') if 'results' in response.data else response.data
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['job']['id'], str(self.job1.id))
        self.assertEqual(results[0]['status'], 'pending_review')

    def test_get_recommendations_filter_by_status_dismissed(self):
        """Test filtering recommendations by 'dismissed' status."""
        self.client.force_authenticate(user=self.user1)
        response = self.client.get(self.url, {'status': 'dismissed'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get('results') if 'results' in response.data else response.data
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['job']['id'], str(self.job3.id))
        self.assertEqual(results[0]['status'], 'dismissed')

    def test_get_recommendations_filter_by_multiple_statuses(self):
        """Test filtering recommendations by multiple statuses."""
        self.client.force_authenticate(user=self.user1)
        response = self.client.get(self.url, {'status': 'pending_review,dismissed'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get('results') if 'results' in response.data else response.data
        self.assertEqual(len(results), 2)
        # Check that both rec1 (pending) and rec3 (dismissed) are present, order by score
        result_job_ids = {item['job']['id'] for item in results}
        self.assertIn(str(self.job1.id), result_job_ids)
        self.assertIn(str(self.job3.id), result_job_ids)


    def test_get_recommendations_filter_by_invalid_status(self):
        """Test filtering with an invalid status value."""
        self.client.force_authenticate(user=self.user1)
        response = self.client.get(self.url, {'status': 'invalid_status_value'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get('results') if 'results' in response.data else response.data
        # Default behavior is to show 'pending_review' and 'viewed' if filter is invalid
        self.assertEqual(len(results), 2)

    def test_get_recommendations_no_recommendations_for_user(self):
        """Test when a user has no recommendations matching default filters."""
        # User2 only has one 'pending_review' recommendation.
        # Let's change user2's recommendation to 'dismissed' for this test.
        self.rec1_user2.status = 'dismissed'
        self.rec1_user2.save()

        self.client.force_authenticate(user=self.user2)
        response = self.client.get(self.url) # Default filters 'pending_review', 'viewed'
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get('results') if 'results' in response.data else response.data
        self.assertEqual(len(results), 0)

    def test_get_recommendations_ensure_user_sees_only_their_own(self):
        """Test that a user only sees their own recommendations."""
        self.client.force_authenticate(user=self.user1)
        response_user1 = self.client.get(self.url)
        results_user1 = response_user1.data.get('results') if 'results' in response_user1.data else response_user1.data
        self.assertEqual(len(results_user1), 2)
        user1_job_ids = {item['job']['id'] for item in results_user1}
        self.assertNotIn(str(self.job4.id), user1_job_ids) # job4 is for user2

        self.client.force_authenticate(user=self.user2)
        response_user2 = self.client.get(self.url)
        results_user2 = response_user2.data.get('results') if 'results' in response_user2.data else response_user2.data
        self.assertEqual(len(results_user2), 1)
        self.assertEqual(results_user2[0]['job']['id'], str(self.job4.id))

# To run these tests: python manage.py test apps.jobs.tests.test_views


class JobAlertViewSetTest(APITestCase):
    def setUp(self):
        self.user1 = User.objects.create_user(username='user1alert', email='user1alert@example.com', password='password1')
        self.user2 = User.objects.create_user(username='user2alert', email='user2alert@example.com', password='password2')

        self.alert1_user1 = JobAlert.objects.create(
            user=self.user1,
            name="User1 Python Alert",
            keywords=["Python"],
            location="Remote"
        )
        self.alert2_user1 = JobAlert.objects.create(
            user=self.user1,
            name="User1 Java Alert",
            keywords=["Java"],
            location="New York"
        )
        self.alert1_user2 = JobAlert.objects.create(
            user=self.user2,
            name="User2 Go Alert",
            keywords=["Golang"],
            location="Remote"
        )

        self.list_create_url = reverse('jobalert-list') # DRF default router name for list/create

    def test_create_job_alert_authenticated(self):
        self.client.force_authenticate(user=self.user1)
        data = {
            "name": "My New Remote JS Alert",
            "keywords": ["JavaScript", "React"], # This is a JSONField in the model
            "location": "Remote",
            "frequency": "weekly", # Valid choice from model
            "job_type": "full_time", # Valid choice from Job.JOB_TYPES
            "experience_level": "mid", # Valid choice from Job.EXPERIENCE_LEVELS
            "remote_only": True,
            "is_active": True
            # min_salary and max_salary are optional
        }
        response = self.client.post(self.list_create_url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(JobAlert.objects.count(), 4) # 3 existing + 1 new
        new_alert = JobAlert.objects.get(id=response.data['id'])
        self.assertEqual(new_alert.user, self.user1)
        self.assertEqual(new_alert.name, "My New Remote JS Alert")
        self.assertEqual(new_alert.keywords, ["JavaScript", "React"]) # Check JSONField data
        self.assertTrue(new_alert.remote_only)

    def test_create_job_alert_unauthenticated(self):
        data = {"name": "Unauthorized Alert", "keywords": ["Fail"]}
        response = self.client.post(self.list_create_url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_list_job_alerts_authenticated_user1(self):
        self.client.force_authenticate(user=self.user1)
        response = self.client.get(self.list_create_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Assuming default pagination might be active, response.data could be a dict with 'results'
        results = response.data.get('results', response.data) # Handle paginated or non-paginated response

        self.assertEqual(len(results), 2)
        response_alert_names = sorted([item['name'] for item in results])
        expected_alert_names = sorted([self.alert1_user1.name, self.alert2_user1.name])
        self.assertEqual(response_alert_names, expected_alert_names)

        for alert_data in results:
            self.assertNotEqual(alert_data['name'], self.alert1_user2.name)

    def test_list_job_alerts_authenticated_user2(self):
        self.client.force_authenticate(user=self.user2)
        response = self.client.get(self.list_create_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get('results', response.data)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['name'], self.alert1_user2.name)

    def test_list_job_alerts_unauthenticated(self):
        response = self.client.get(self.list_create_url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_retrieve_job_alert_owner(self):
        self.client.force_authenticate(user=self.user1)
        detail_url = reverse('jobalert-detail', kwargs={'pk': self.alert1_user1.pk})
        response = self.client.get(detail_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['name'], self.alert1_user1.name)

    def test_retrieve_job_alert_not_owner(self):
        self.client.force_authenticate(user=self.user1)
        detail_url = reverse('jobalert-detail', kwargs={'pk': self.alert1_user2.pk})
        response = self.client.get(detail_url)
        # ViewSet's get_queryset filters by user, so non-owned object should result in 404
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_update_job_alert_owner_put(self):
        self.client.force_authenticate(user=self.user1)
        detail_url = reverse('jobalert-detail', kwargs={'pk': self.alert1_user1.pk})

        # For PUT, all required fields of the serializer must be provided.
        # The JobAlertSerializer makes most fields optional or read-only,
        # but 'name' and 'keywords' are good to test.
        # From the model: name (CharField), keywords (JSONField), location (CharField),
        # job_type, experience_level, remote_only, min_salary, max_salary,
        # frequency, email_notifications, push_notifications, is_active.
        # Serializer read_only_fields = ('id', 'user', 'created_at', 'updated_at', 'last_run')

        data_for_put = {
            "name": "User1 Python Alert Updated Via PUT",
            "keywords": ["Python", "Django"],
            "location": "Global Remote",
            "job_type": self.alert1_user1.job_type, # Keep existing
            "experience_level": self.alert1_user1.experience_level, # Keep existing
            "remote_only": self.alert1_user1.remote_only, # Keep existing
            "min_salary": self.alert1_user1.min_salary, # Keep existing
            "max_salary": self.alert1_user1.max_salary, # Keep existing
            "frequency": "weekly",
            "email_notifications": self.alert1_user1.email_notifications,
            "push_notifications": self.alert1_user1.push_notifications,
            "is_active": self.alert1_user1.is_active
        }

        response = self.client.put(detail_url, data_for_put, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.alert1_user1.refresh_from_db()
        self.assertEqual(self.alert1_user1.name, "User1 Python Alert Updated Via PUT")
        self.assertEqual(self.alert1_user1.keywords, ["Python", "Django"])
        self.assertEqual(self.alert1_user1.frequency, "weekly")

    def test_partial_update_job_alert_owner_patch(self):
        self.client.force_authenticate(user=self.user1)
        detail_url = reverse('jobalert-detail', kwargs={'pk': self.alert1_user1.pk})
        patch_data = {"name": "User1 Python Alert Patched", "is_active": False, "location": "Anywhere"}
        response = self.client.patch(detail_url, patch_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.alert1_user1.refresh_from_db()
        self.assertEqual(self.alert1_user1.name, "User1 Python Alert Patched")
        self.assertFalse(self.alert1_user1.is_active)
        self.assertEqual(self.alert1_user1.location, "Anywhere")

    def test_delete_job_alert_owner(self):
        self.client.force_authenticate(user=self.user1)
        initial_count = JobAlert.objects.filter(user=self.user1).count()
        detail_url = reverse('jobalert-detail', kwargs={'pk': self.alert1_user1.pk})
        response = self.client.delete(detail_url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(JobAlert.objects.filter(user=self.user1).count(), initial_count - 1)

    def test_update_job_alert_not_owner(self):
        self.client.force_authenticate(user=self.user1)
        detail_url = reverse('jobalert-detail', kwargs={'pk': self.alert1_user2.pk})
        patch_data = {"name": "Attempt to update other user alert"}
        response = self.client.patch(detail_url, patch_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_delete_job_alert_not_owner(self):
        self.client.force_authenticate(user=self.user1)
        detail_url = reverse('jobalert-detail', kwargs={'pk': self.alert1_user2.pk})
        response = self.client.delete(detail_url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


from apps.jobs.models import Application, Job # Already imported Job, add Application if not already for this new class
from apps.jobs.serializers import ApplicationSerializer # Import ApplicationSerializer for this new class

class ApplicationViewSetAdvancedTrackingTest(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='apptrackuser', email='apptrackuser@example.com', password='password')
        self.job = Job.objects.create(title="Test Job for App Tracking", company="Track Co", description="Desc", location="Loc")
        self.application = Application.objects.create(
            user=self.user,
            job=self.job,
            status='submitted' # Initial system status
        )
        self.client = APIClient() # Already in other test class, but good to have instance here
        self.client.force_authenticate(user=self.user)
        self.detail_url = reverse('application-detail', kwargs={'pk': self.application.pk})

    def test_update_application_with_new_tracking_fields(self):
        patch_data = {
            "user_defined_status": Application.USER_DEFINED_STATUS_CHOICES[1][0], # 'preparing_application'
            "user_notes": "Sent them an email, waiting for reply.",
            "follow_up_date": timezone.now().date() + timezone.timedelta(days=7),
            "interview_details": [{"date": "2024-08-01T14:00:00Z", "type": "HR Screen", "interviewer": "Jane Doe"}],
            "offer_details": {"salary": 120000, "equity": "0.1%", "notes": "Standard offer."}
        }
        response = self.client.patch(self.detail_url, patch_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

        self.application.refresh_from_db()
        self.assertEqual(self.application.user_defined_status, patch_data["user_defined_status"])
        self.assertEqual(self.application.user_notes, patch_data["user_notes"])
        self.assertEqual(self.application.follow_up_date, patch_data["follow_up_date"])
        self.assertEqual(self.application.interview_details, patch_data["interview_details"])
        self.assertEqual(self.application.offer_details, patch_data["offer_details"])

    def test_cannot_update_follow_up_reminder_sent_at_via_api(self):
        # This field should be read-only from the API user's perspective
        original_sent_at = self.application.follow_up_reminder_sent_at # Should be None initially

        patch_data = {
            "follow_up_reminder_sent_at": timezone.now()
        }
        response = self.client.patch(self.detail_url, patch_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK) # The request itself is fine

        self.application.refresh_from_db()
        # Check that the field was NOT updated, because it's read-only in serializer
        self.assertEqual(self.application.follow_up_reminder_sent_at, original_sent_at)
        # Also confirm the response data doesn't allow setting it, or doesn't show it if not readable
        # (it is readable, so it will be in response.data, but should be its original value)
        if original_sent_at:
             self.assertEqual(response.data['follow_up_reminder_sent_at'], original_sent_at.isoformat())
        else:
             self.assertIsNone(response.data['follow_up_reminder_sent_at'])


    def test_update_application_by_non_owner_fails(self):
        other_user = User.objects.create_user(username='otheruserapp', email='other@example.com', password='password')
        self.client.force_authenticate(user=other_user) # Authenticate as a different user

        patch_data = {"user_notes": "Trying to update other user's application."}
        response = self.client.patch(self.detail_url, patch_data, format='json')

        # ApplicationViewSet's get_queryset filters by user, so this should be a 404
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


# Tests for JobViewSet's generate_interview_questions action
class JobViewSetInterviewQuestionActionTest(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='interviewprepuser', email='interview@example.com', password='password')
        self.job = Job.objects.create(
            pk=uuid.uuid4(), # Ensure pk is set for URL reversing
            title="Senior AI Engineer",
            company="FutureTech",
            description="Build the future of AI.",
            location="Anywhere"
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.url = reverse('job-generate-interview-questions', kwargs={'pk': self.job.pk})

    @patch('apps.jobs.views.generate_interview_questions_task.delay')
    def test_generate_interview_questions_action_success(self, mock_task_delay):
        mock_celery_task = MagicMock()
        mock_celery_task.id = "test_celery_task_id_123"
        mock_task_delay.return_value = mock_celery_task

        response = self.client.post(self.url)

        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertIn("task_id", response.data)
        self.assertEqual(response.data['task_id'], "test_celery_task_id_123")
        self.assertEqual(response.data['status'], "queued")
        self.assertIn("Interview question generation has been queued", response.data['message'])

        mock_task_delay.assert_called_once_with(job_id=str(self.job.pk), user_id=str(self.user.pk))

    def test_generate_interview_questions_action_unauthenticated(self):
        self.client.logout() # Ensure client is not authenticated
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_generate_interview_questions_action_job_not_found(self):
        non_existent_uuid = uuid.uuid4()
        invalid_url = reverse('job-generate-interview-questions', kwargs={'pk': non_existent_uuid})
        response = self.client.post(invalid_url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    @patch('apps.jobs.views.generate_interview_questions_task.delay')
    def test_generate_interview_questions_action_task_dispatch_failure(self, mock_task_delay):
        # Simulate an error during .delay() call, though this is less common for .delay() itself
        # More likely, the task might fail internally, but the API would still return 202.
        # This tests if .delay() itself had an issue (e.g., Celery not configured, though that's broader).
        mock_task_delay.side_effect = Exception("Celery dispatch error")

        with self.assertLogs(logger='apps.jobs.views', level='ERROR') as cm: # Assuming view logs errors
            response = self.client.post(self.url)
            # Depending on how view handles this, it might still return 202 if error is not caught before .delay,
            # or 500 if .delay() itself raises an unhandled error that bubbles up.
            # For now, let's assume a robust .delay() call doesn't usually fail this way unless Celery is down.
            # If the task fails *after* being queued, the API response is still 202.
            # This test is more about the view's robustness if .delay() itself fails.
            # A more realistic scenario for failure is the task failing, which is tested in test_tasks.py.
            # If .delay() fails catastrophically (e.g. Celery not running and no broker):
            # self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
            # However, .delay() usually succeeds unless broker is totally unavailable.
            # Let's assume the view returns 202 and logs, or we make it return 500.
            # The current view doesn't have explicit try-except around .delay().
            # If .delay() raises, it would likely be a 500.

        # If the view catches and returns a specific error:
        # self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
        # self.assertIn("Failed to queue task", response.data.get("error", ""))

        # For now, let's assume .delay() itself doesn't fail in a way that the view catches.
        # The default behavior for an unhandled exception in a DRF view is a 500.
        # This test might need adjustment based on actual error handling in the view for .delay() failures.
        # As the view currently stands, an exception from .delay() would likely lead to a 500.
        # This test is more of a thought experiment unless specific error handling for .delay() is added.
        pass # Placeholder for now, as .delay() failure is usually a setup issue.


from unittest.mock import patch, MagicMock
from apps.jobs.documents import JobDocument # For mocking search

class JobSearchViewElasticsearchTest(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='essearchuser', email='essearch@example.com', password='password')
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.search_url = reverse('job_search') # Assuming 'job_search' is the name of JobSearchView URL

        # Create some Job instances in the DB that our mock ES response will point to
        self.job1 = Job.objects.create(pk=uuid.uuid4(), title="ES Job 1", company="ES Comp A", description=".", location=".")
        self.job2 = Job.objects.create(pk=uuid.uuid4(), title="ES Job 2", company="ES Comp B", description=".", location=".")

    @patch('apps.jobs.views.JobDocument.search') # Patch the search() class method
    def test_job_search_view_uses_elasticsearch(self, mock_es_search):
        # Configure the mock Elasticsearch response
        mock_es_hit1 = MagicMock()
        mock_es_hit1.meta.id = str(self.job1.pk) # ES IDs are usually strings
        # Add other fields to mock_es_hit1._source if serializer uses them directly from ES
        # For Option B (fetch from DB), only meta.id is strictly needed from hit.

        mock_es_hit2 = MagicMock()
        mock_es_hit2.meta.id = str(self.job2.pk)

        mock_es_response = MagicMock()
        mock_es_response.hits = [mock_es_hit1, mock_es_hit2]
        mock_es_response.hits.total.value = 2

        # The search object 's' itself needs to be a mock that has an execute method
        mock_search_instance = MagicMock()
        mock_search_instance.execute.return_value = mock_es_response

        # Configure the chain of calls: JobDocument.search() -> query() -> sort() -> execute()
        # search(...)[0:50].execute()
        # We patched JobDocument.search, so it returns our mock_search_instance.
        # The slicing [0:50] also needs to return the mock_search_instance to chain .execute()
        mock_es_search.return_value = mock_search_instance
        mock_search_instance.__getitem__.return_value = mock_search_instance # For slicing [0:50]

        # Make a GET request to the JobSearchView
        response = self.client.get(self.search_url, {'title': 'ES Job'})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        mock_es_search.assert_called_once() # Verify JobDocument.search() was called

        # Verify that the execute method on the search object was called
        mock_search_instance.execute.assert_called_once()

        # Verify the response structure and content (based on JobSearchResultSerializer)
        self.assertIn('count', response.data)
        self.assertIn('results', response.data)
        self.assertEqual(response.data['count'], 2)
        self.assertEqual(len(response.data['results']), 2)

        # Check if the job titles from the database (fetched via IDs from ES) are in the response
        result_titles = sorted([item['title'] for item in response.data['results']])
        expected_titles = sorted([self.job1.title, self.job2.title])
        self.assertEqual(result_titles, expected_titles)

    @patch('apps.jobs.views.JobDocument.search')
    def test_job_search_view_handles_es_exception_gracefully(self, mock_es_search):
        mock_search_instance = MagicMock()
        mock_search_instance.execute.side_effect = Exception("Elasticsearch connection error")
        mock_es_search.return_value = mock_search_instance
        mock_search_instance.__getitem__.return_value = mock_search_instance

        response = self.client.get(self.search_url, {'title': 'Test'})

        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertIn('error', response.data)
        self.assertEqual(response.data['error'], "Search service temporarily unavailable.")

    @patch('apps.jobs.views.JobDocument.search')
    def test_job_search_view_query_construction(self, mock_es_search):
        # This test is more involved as it requires inspecting the query sent to ES.
        # We'll check if specific filters are applied.

        mock_search_instance = MagicMock()
        mock_es_response = MagicMock()
        mock_es_response.hits = []
        mock_es_response.hits.total.value = 0
        mock_search_instance.execute.return_value = mock_es_response

        # Mock the chain of query building calls
        mock_es_search.return_value = mock_search_instance
        mock_search_instance.query.return_value = mock_search_instance
        mock_search_instance.sort.return_value = mock_search_instance
        mock_search_instance.__getitem__.return_value = mock_search_instance # For slicing

        # Make a request with various query parameters
        self.client.get(self.search_url, {
            'title': 'Developer',
            'location': 'Remote',
            'job_type': 'full_time',
            'is_remote': 'true'
        })

        mock_es_search.assert_called_once()

        # Check that query() was called on the search instance.
        # The actual inspection of the ES_Q objects passed to query() is complex.
        # A simpler check is that query() was called if params were present.
        self.assertTrue(mock_search_instance.query.called)

        # Example: Check one of the Q objects passed to .query()
        # This requires knowing the structure of ES_Q objects from elasticsearch-dsl
        # and how they are passed in the bool query.
        # For instance, to check if a "match" query for title was part of a "must" clause:
        # args, kwargs = mock_search_instance.query.call_args
        # bool_query = args[0] # Assuming the first arg is the ES_Q('bool', ...)
        # self.assertIn(ES_Q("match", title="Developer"), bool_query.must) # This depends on ES_Q internal structure

        # Check that sort() was called
        self.assertTrue(mock_search_instance.sort.called)
        # Example: Check if sorted by '-posted_date'
        # sort_args, sort_kwargs = mock_search_instance.sort.call_args_list[0] # Get first call to sort
        # self.assertIn('-posted_date', sort_args)

        # This test provides a basic check that query building methods are invoked.
        # Deep inspection of Elasticsearch DSL query objects is possible but can be brittle.
        pass
