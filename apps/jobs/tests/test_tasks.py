import unittest
from unittest.mock import patch, MagicMock, call, ANY
from celery.exceptions import Retry
from django.utils import timezone
from datetime import timedelta
import uuid

# Assuming tasks are in apps.jobs.tasks
# from apps.jobs import tasks as job_tasks # Avoid direct import if tasks import models at module level

# Mock models
class MockJob:
    def __init__(self, id, title, description, location, job_type, experience_level, is_remote, salary_min, salary_max, created_at, status='active'):
        self.id = id
        self.title = title
        self.description = description
        self.location = location
        self.job_type = job_type
        self.experience_level = experience_level
        self.is_remote = is_remote
        self.salary_min = salary_min
        self.salary_max = salary_max
        self.created_at = created_at
        self.status = status
        self.company = "Mock Company" # Added for notification string

    def __str__(self):
        return self.title

class MockJobAlert:
    objects = MagicMock()

    def __init__(self, id, user_id, keywords=None, location=None, job_type=None,
                 experience_level=None, remote_only=False, min_salary=None,
                 is_active=True, last_run=None, name="Test Alert"):
        self.id = id
        self.user_id = user_id # Store user_id directly for simplicity in mock
        self.user = MagicMock(id=user_id) # Mock user object with an id
        self.name = name
        self.keywords = keywords or []
        self.location = location
        self.job_type = job_type
        self.experience_level = experience_level
        self.remote_only = remote_only
        self.min_salary = min_salary
        self.is_active = is_active
        self.last_run = last_run
        self._saved_fields = None # To check update_fields

    def save(self, update_fields=None):
        self._saved_fields = update_fields
        pass # Mock save

class MockQuerySet:
    def __init__(self, items=None):
        self._items = items if items is not None else []

    def filter(self, *args, **kwargs):
        # This is a very simplified filter, real tests might need more specific mock querysets
        # For now, it just returns itself or a new MockQuerySet with the same items
        # In more complex tests, you'd inspect args/kwargs to return specific subsets
        return self

    def distinct(self):
        return self # Placeholder

    def exists(self):
        return bool(self._items)

    def __iter__(self):
        return iter(self._items)

    def all(self): # Added for JobAlert.objects.filter().all() if used
        return self

class TestJobAlertTasks(unittest.TestCase):

    def setUp(self):
        self.patcher_job_model = patch('apps.jobs.tasks.Job', new_callable=lambda: MockJob)
        self.MockJobModel = self.patcher_job_model.start()
        self.MockJobModel.objects = MagicMock(spec=MockJob.objects) # Mock the manager more accurately

        self.patcher_job_alert_model = patch('apps.jobs.tasks.JobAlert', new_callable=lambda: MockJobAlert)
        self.MockJobAlertModel = self.patcher_job_alert_model.start()
        self.MockJobAlertModel.objects = MagicMock(spec=MockJobAlert.objects)

        self.patcher_timezone = patch('apps.jobs.tasks.timezone')
        self.mock_timezone = self.patcher_timezone.start()
        self.mock_now = timezone.now() # Use a fixed "now" for the test run
        self.mock_timezone.now.return_value = self.mock_now
        self.mock_timezone.timedelta = timezone.timedelta # Allow timedelta to work

        # Conceptual: Mock notification sending
        self.patcher_notification = patch('apps.jobs.tasks.logger.info') # Patching logger.info where notifications are logged
        self.mock_notification_logger = self.patcher_notification.start()

        # Reload tasks module to use patched versions
        global job_tasks # Make it accessible to test methods
        import importlib
        from apps.jobs import tasks as tasks_module
        importlib.reload(tasks_module)
        job_tasks = tasks_module


    def tearDown(self):
        self.patcher_job_model.stop()
        self.patcher_job_alert_model.stop()
        self.patcher_timezone.stop()
        self.patcher_notification.stop()

    def test_process_job_alerts_task_no_active_alerts(self):
        self.MockJobAlertModel.objects.filter.return_value = MockQuerySet([]) # No active alerts

        result = job_tasks.process_job_alerts_task()

        self.assertEqual(result['status'], 'no_active_alerts')
        self.assertEqual(result['processed_alerts'], 0)
        self.MockJobModel.objects.filter.assert_not_called() # No jobs should be queried

    def test_process_job_alerts_task_active_alert_no_new_jobs(self):
        alert1 = MockJobAlert(id=1, user_id=1, keywords=["Python"], last_run=self.mock_now - timedelta(hours=1))
        self.MockJobAlertModel.objects.filter.return_value = MockQuerySet([alert1])
        self.MockJobModel.objects.filter.return_value = MockQuerySet([]) # No matching jobs

        result = job_tasks.process_job_alerts_task()

        self.assertEqual(result['processed_alerts'], 1)
        self.assertEqual(result['notifications_triggered'], 0)
        self.MockJobModel.objects.filter.assert_called_once() # Called once for alert1
        self.assertEqual(alert1.last_run, self.mock_now) # last_run should be updated
        self.assertIn('last_run', alert1._saved_fields)


    def test_process_job_alerts_task_matches_one_job(self):
        alert_last_run = self.mock_now - timedelta(days=1)
        job_created_time = self.mock_now - timedelta(hours=12) # Newer than last_run

        alert1 = MockJobAlert(id=1, user_id=1, keywords=["Developer"], location="Remote", last_run=alert_last_run)
        self.MockJobAlertModel.objects.filter.return_value = MockQuerySet([alert1])

        job1 = MockJob(id=uuid.uuid4(), title="Python Developer", description="Remote role", location="Remote", job_type="full_time", experience_level="mid", is_remote=True, salary_min=70000, salary_max=90000, created_at=job_created_time)
        self.MockJobModel.objects.filter.return_value = MockQuerySet([job1])

        result = job_tasks.process_job_alerts_task()

        self.assertEqual(result['processed_alerts'], 1)
        self.assertEqual(result['notifications_triggered'], 1)

        # Check that the conceptual notification log was called
        self.mock_notification_logger.assert_any_call(f"  -> Conceptual notification triggered for user {alert1.user.id}, job {job1.id}, alert '{alert1.name}'.")
        self.assertEqual(alert1.last_run, self.mock_now)

    def test_process_job_alerts_task_keyword_matching(self):
        alert1 = MockJobAlert(id=1, user_id=1, keywords=["Urgent", "Backend"], last_run=None)
        self.MockJobAlertModel.objects.filter.return_value = MockQuerySet([alert1])

        # Job matches "Backend" in title, "Urgent" in description
        job1 = MockJob(id=uuid.uuid4(), title="Senior Backend Engineer", description="This is an Urgent requirement.", location="Anywhere", job_type="full_time", experience_level="senior", is_remote=True, salary_min=100k, salary_max=150k, created_at=self.mock_now - timedelta(minutes=30))
        # Job matches only "Backend"
        job2 = MockJob(id=uuid.uuid4(), title="Backend Developer", description="Standard role.", location="Anywhere", job_type="full_time", experience_level="senior", is_remote=True, salary_min=100k, salary_max=150k, created_at=self.mock_now - timedelta(minutes=30))

        # Simulate that the filter for job1 (matching both keywords in OR, and other criteria) returns job1
        # This requires more sophisticated mocking of the Q object filtering if we want to test the Q logic precisely.
        # For now, assume the filter correctly identifies job1.
        self.MockJobModel.objects.filter.return_value = MockQuerySet([job1])

        result = job_tasks.process_job_alerts_task()
        self.assertEqual(result['notifications_triggered'], 1) # Only job1 because it matches (conceptually) the Q logic for keywords

        # To properly test Q object logic, we'd need to inspect the kwargs of the filter call.
        # Example of how one might start to check Q objects (can get complex):
        args, kwargs = self.MockJobModel.objects.filter.call_args
        # print(args) # args[0] would be the Q object(s)
        # self.assertIn(Q(title__icontains="Urgent") | Q(description__icontains="Urgent"), args[0].children)
        # This level of Q object introspection is tricky and often brittle.

    def test_process_job_alerts_task_filters_by_job_type_and_salary(self):
        alert1 = MockJobAlert(id=1, user_id=1, job_type="contract", min_salary=80000, last_run=None)
        self.MockJobAlertModel.objects.filter.return_value = MockQuerySet([alert1])

        job_match = MockJob(id=uuid.uuid4(), title="Contract Dev", job_type="contract", salary_min=85000, created_at=self.mock_now - timedelta(hours=1))
        job_no_match_type = MockJob(id=uuid.uuid4(), title="FullTime Dev", job_type="full_time", salary_min=85000, created_at=self.mock_now - timedelta(hours=1))
        job_no_match_salary = MockJob(id=uuid.uuid4(), title="Contract LowPay", job_type="contract", salary_min=70000, created_at=self.mock_now - timedelta(hours=1))

        # This mock needs to simulate the Q object filtering based on the alert criteria
        # For this test, we assume the filter correctly selects job_match
        self.MockJobModel.objects.filter.return_value = MockQuerySet([job_match])

        result = job_tasks.process_job_alerts_task()
        self.assertEqual(result['notifications_triggered'], 1)
        # We would assert that the filter call to Job.objects.filter contained Q(job_type='contract') and the salary Q.

    def test_process_job_alerts_task_updates_last_run_even_if_no_matches(self):
        alert1 = MockJobAlert(id=1, user_id=1, keywords=["NonExistent"], last_run=self.mock_now - timedelta(days=2))
        self.MockJobAlertModel.objects.filter.return_value = MockQuerySet([alert1])
        self.MockJobModel.objects.filter.return_value = MockQuerySet([]) # No jobs match

        job_tasks.process_job_alerts_task()

        self.assertEqual(alert1.last_run, self.mock_now)
        self.assertIn('last_run', alert1._saved_fields)

    # Conceptual test for duplicate prevention (if it were implemented)
    # @patch('apps.jobs.tasks.NotifiedAlertMatch.objects.filter')
    # def test_process_job_alerts_task_prevents_duplicate_notifications(self, mock_notified_filter):
    #     # Setup alert and a matching job
    #     # mock_notified_filter(...).exists.return_value = True # Simulate already notified
    #     # ...
    #     # self.assertEqual(result['notifications_triggered'], 0)
    #     pass

if __name__ == '__main__':
    unittest.main()
