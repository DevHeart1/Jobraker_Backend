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
        self.patcher_notification = patch('apps.jobs.tasks.logger.info') # Keep for other log checks if any
        self.mock_notification_logger = self.patcher_notification.start()

        self.patcher_send_mail = patch('apps.jobs.tasks.send_mail') # Mock send_mail
        self.mock_send_mail = self.patcher_send_mail.start()

        self.patcher_settings = patch('apps.jobs.tasks.settings')
        self.mock_settings = self.patcher_settings.start()
        self.mock_settings.DEFAULT_FROM_EMAIL = 'noreply@jobraker.com'
        self.mock_settings.SITE_URL = 'http://testserver'


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
        self.patcher_send_mail.stop()
        self.patcher_settings.stop()

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
        self.assertEqual(result['notifications_sent'], 1) # Updated to check 'notifications_sent'

        # Check that send_mail was called
        self.mock_send_mail.assert_called_once()
        args, kwargs = self.mock_send_mail.call_args
        self.assertEqual(kwargs['subject'], f"New Job Matches for Your Alert: {alert1.name}")
        self.assertIn(job1.title, kwargs['message'])
        self.assertIn(f"/jobs/{job1.id}/", kwargs['message']) # Check for job URL part
        self.assertEqual(kwargs['from_email'], self.mock_settings.DEFAULT_FROM_EMAIL)
        self.assertEqual(kwargs['recipient_list'], [alert1.user.email]) # Assuming MockJobAlert.user has an email attribute

        self.assertEqual(alert1.last_run, self.mock_now)
        self.mock_send_mail.reset_mock() # Reset for other tests

    def test_process_job_alerts_task_respects_frequency(self):
        # Alert 1: Daily, ran 12 hours ago -> should not run
        alert1_user = MagicMock(email='user1@example.com', first_name='User1')
        alert1 = MockJobAlert(id=1, user_id=1, name="Daily Alert", frequency='daily', last_run=self.mock_now - timedelta(hours=12))
        alert1.user = alert1_user # Attach mock user with email

        # Alert 2: Weekly, ran 8 days ago -> should run
        alert2_user = MagicMock(email='user2@example.com', first_name='User2')
        alert2 = MockJobAlert(id=2, user_id=2, name="Weekly Alert", frequency='weekly', last_run=self.mock_now - timedelta(days=8), keywords=["TestJob"])
        alert2.user = alert2_user

        # Alert 3: Daily, never ran -> should run
        alert3_user = MagicMock(email='user3@example.com', first_name='User3')
        alert3 = MockJobAlert(id=3, user_id=3, name="New Daily Alert", frequency='daily', last_run=None, keywords=["AnotherJob"])
        alert3.user = alert3_user

        # Alert 4: Monthly, ran 15 days ago -> should not run
        alert4_user = MagicMock(email='user4@example.com', first_name='User4')
        alert4 = MockJobAlert(id=4, user_id=4, name="Monthly Alert", frequency='monthly', last_run=self.mock_now - timedelta(days=15))
        alert4.user = alert4_user

        self.MockJobAlertModel.objects.filter.return_value = MockQuerySet([alert1, alert2, alert3, alert4])

        # Simulate jobs for alerts that should run
        job_for_alert2 = MockJob(id=uuid.uuid4(), title="TestJob Title", created_at=self.mock_now - timedelta(hours=1))
        job_for_alert3 = MockJob(id=uuid.uuid4(), title="AnotherJob Title", created_at=self.mock_now - timedelta(hours=1))

        # This mock needs to be more dynamic or called multiple times if Job.objects.filter is inside the loop for each alert.
        # For simplicity, assume it's called once and returns all possible jobs, and the task filters them.
        # Or, more accurately, mock its side_effect if called per alert.

        # Let's make the Job.objects.filter mock return jobs based on alert.
        def job_filter_side_effect(*args, **kwargs):
            # This is a simplified check. A real one would inspect the Q objects in args[0]
            # to see if they match the alert's criteria.
            # For this test, we'll "know" which alert is being processed by iterating call_count or by specific Q filters.
            # This is hard to do without deep Q object inspection.
            # Alternative: Set up specific MockQuerySet instances for each expected call.

            # Simplified: If the filter is for alert2's keywords, return job_for_alert2.
            # This relies on the keyword filter being specific enough.
            # This part is tricky to mock perfectly without more complex side_effect logic.
            # Let's assume the first call to Job.objects.filter is for alert2 (which runs)
            # and the second is for alert3 (which runs).

            # Call 1 (alert2)
            if self.MockJobModel.objects.filter.call_count == 1: # First time it's called (for alert2)
                return MockQuerySet([job_for_alert2])
            # Call 2 (alert3)
            elif self.MockJobModel.objects.filter.call_count == 2: # Second time (for alert3)
                 return MockQuerySet([job_for_alert3])
            return MockQuerySet([]) # Default no jobs

        self.MockJobModel.objects.filter.side_effect = job_filter_side_effect

        result = job_tasks.process_job_alerts_task()

        self.assertEqual(result['alerts_skipped_frequency'], 2) # alert1 and alert4 skipped
        self.assertEqual(result['alerts_processed'], 2)      # alert2 and alert3 processed
        self.assertEqual(result['notifications_sent'], 2)    # One email for alert2, one for alert3

        # Check send_mail calls
        self.assertEqual(self.mock_send_mail.call_count, 2)

        # Check call for alert2
        call_args_alert2 = self.mock_send_mail.call_args_list[0]
        self.assertEqual(call_args_alert2[1]['subject'], f"New Job Matches for Your Alert: {alert2.name}")
        self.assertIn(job_for_alert2.title, call_args_alert2[1]['message'])
        self.assertEqual(call_args_alert2[1]['recipient_list'], [alert2.user.email])

        # Check call for alert3
        call_args_alert3 = self.mock_send_mail.call_args_list[1]
        self.assertEqual(call_args_alert3[1]['subject'], f"New Job Matches for Your Alert: {alert3.name}")
        self.assertIn(job_for_alert3.title, call_args_alert3[1]['message'])
        self.assertEqual(call_args_alert3[1]['recipient_list'], [alert3.user.email])

        self.assertEqual(alert1.last_run, self.mock_now - timedelta(hours=12)) # Not updated
        self.assertEqual(alert2.last_run, self.mock_now) # Updated
        self.assertEqual(alert3.last_run, self.mock_now) # Updated
        self.assertEqual(alert4.last_run, self.mock_now - timedelta(days=15)) # Not updated

        self.mock_send_mail.reset_mock()
        self.MockJobModel.objects.filter.side_effect = None # Reset side effect

    def test_process_job_alerts_task_keyword_matching(self):
        # Mock user for the alert
        alert_user = MagicMock(email='keyworduser@example.com', first_name='Keyword')
        alert1 = MockJobAlert(id=1, user_id=1, keywords=["Urgent", "Backend"], last_run=None)
        alert1.user = alert_user # Attach mock user
        self.MockJobAlertModel.objects.filter.return_value = MockQuerySet([alert1])

        # Job matches "Backend" in title, "Urgent" in description
        job1 = MockJob(id=uuid.uuid4(), title="Senior Backend Engineer", description="This is an Urgent requirement.", location="Anywhere", job_type="full_time", experience_level="senior", is_remote=True, salary_min=100000, salary_max=150000, created_at=self.mock_now - timedelta(minutes=30))
        # Job matches only "Backend"
        job2 = MockJob(id=uuid.uuid4(), title="Backend Developer", description="Standard role.", location="Anywhere", job_type="full_time", experience_level="senior", is_remote=True, salary_min=100000, salary_max=150000, created_at=self.mock_now - timedelta(minutes=30))

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


from apps.jobs.models import Application as ActualApplication # Use actual model for setup
from apps.jobs.models import Job as ActualJob
from django.contrib.auth import get_user_model as actual_get_user_model

ActualUser = actual_get_user_model()

class TestApplicationReminderTasks(unittest.TestCase):
    def setUp(self):
        # We are testing the actual task which imports models directly.
        # So, we need to use the real database for setup, or patch the models within the task's scope.
        # Patching models within the task's scope is cleaner if we want to avoid DB hits during most tests.
        # However, for query logic tests, sometimes using the test DB is easier.
        # For this, let's try to use the real models for setup and patch external calls like send_mail and timezone.now.

        self.patcher_timezone_task = patch('apps.jobs.tasks.timezone') # Patch timezone used in the task
        self.mock_timezone_task = self.patcher_timezone_task.start()
        self.mock_now_task = timezone.now() # Fixed "now" for this test run
        self.mock_timezone_task.now.return_value = self.mock_now_task
        self.mock_timezone_task.timedelta = timezone.timedelta # Allow timedelta to work

        self.patcher_send_mail_task = patch('apps.jobs.tasks.send_mail')
        self.mock_send_mail_task = self.patcher_send_mail_task.start()

        self.patcher_settings_task = patch('apps.jobs.tasks.settings')
        self.mock_settings_task = self.patcher_settings_task.start()
        self.mock_settings_task.DEFAULT_FROM_EMAIL = 'reminders@jobraker.com'
        # self.mock_settings_task.SITE_URL = 'http://testserver' # If URLs in email are tested

        # Reload tasks module to use patched versions if it was imported at module level
        # and not within the task function itself.
        # The task `send_application_follow_up_reminders` imports models and Django utils inside.
        global job_tasks
        import importlib
        from apps.jobs import tasks as tasks_module
        importlib.reload(tasks_module) # Reload to ensure patches on timezone/send_mail are seen if imported at top of tasks.py
        job_tasks = tasks_module


        # Create actual DB objects for testing queries
        self.user1 = ActualUser.objects.create_user(email='reminder1@example.com', password='password', first_name='Reminder1')
        self.user2 = ActualUser.objects.create_user(email='reminder2@example.com', password='password', first_name='Reminder2')
        self.user_no_email = ActualUser.objects.create_user(email='noemail@example.com', password='password')


        self.job1 = ActualJob.objects.create(title="Job A", company="Comp A", description=".", location=".")
        self.job2 = ActualJob.objects.create(title="Job B", company="Comp B", description=".", location=".")
        self.job3 = ActualJob.objects.create(title="Job C", company="Comp C", description=".", location=".")
        self.job4 = ActualJob.objects.create(title="Job D", company="Comp D", description=".", location=".")


        # App 1: Due today, never reminded
        self.app1 = ActualApplication.objects.create(
            user=self.user1, job=self.job1, follow_up_date=self.mock_now_task.date()
        )
        # App 2: Due yesterday, never reminded
        self.app2 = ActualApplication.objects.create(
            user=self.user2, job=self.job2, follow_up_date=self.mock_now_task.date() - timedelta(days=1)
        )
        # App 3: Due today, already reminded for today's follow_up_date
        self.app3 = ActualApplication.objects.create(
            user=self.user1, job=self.job3, follow_up_date=self.mock_now_task.date(),
            follow_up_reminder_sent_at=self.mock_now_task - timedelta(hours=1) # Reminded recently
        )
        # App 4: Due tomorrow -> should not be reminded
        self.app4 = ActualApplication.objects.create(
            user=self.user2, job=self.job4, follow_up_date=self.mock_now_task.date() + timedelta(days=1)
        )
        # App 5: Due yesterday, but reminder sent AFTER follow_up_date (e.g. date was moved back) -> should not remind
        self.app5 = ActualApplication.objects.create(
            user=self.user1,
            # For this test, let's make it a different application by not enforcing unique_together here for simplicity,
            # or ensure it's a different job. Let's use a new job.
            job=ActualJob.objects.create(title="Job E", company="Comp E"),
            follow_up_date=self.mock_now_task.date() - timedelta(days=1),
            follow_up_reminder_sent_at=self.mock_now_task.date() # Reminder sent "today" for yesterday's date
        )
         # App 6: Due today, user has no email
        self.app6 = ActualApplication.objects.create(
            user=self.user_no_email, job=self.job2, follow_up_date=self.mock_now_task.date()
        )
        # App 7: Due in past, reminder sent, but follow_up_date was moved even further to the past (before reminder) -> should not remind again
        self.app7 = ActualApplication.objects.create(
            user=self.user2, job=self.job3,
            follow_up_date=self.mock_now_task.date() - timedelta(days=5),
            follow_up_reminder_sent_at=self.mock_now_task - timedelta(days=3) # Reminder sent after the follow_up_date
        )
        # App 8: Due today, reminder sent, but follow_up_date was moved to today (same as reminder) -> should not remind
        self.app8 = ActualApplication.objects.create(
            user=self.user1, job=self.job4,
            follow_up_date=self.mock_now_task.date() - timedelta(days=2), # Original follow up date
        )
        self.app8.follow_up_reminder_sent_at = self.mock_now_task - timedelta(days=2) # Reminder sent
        self.app8.follow_up_date = self.mock_now_task.date() # User moved follow_up_date to today
        self.app8.save() # This should be reminded (Q(follow_up_reminder_sent_at__lt=F('follow_up_date')))

    def tearDown(self):
        self.patcher_timezone_task.stop()
        self.patcher_send_mail_task.stop()
        self.patcher_settings_task.stop()
        # Clean up database
        ActualApplication.objects.all().delete()
        ActualJob.objects.all().delete()
        ActualUser.objects.all().delete()


    def test_send_reminders_correct_applications(self):
        # Expected to send for app1 (due today, never reminded)
        # Expected to send for app2 (due yesterday, never reminded)
        # Expected to send for app8 (due today, reminder was for older follow_up_date)
        # Not for app3 (reminded for today)
        # Not for app4 (due tomorrow)
        # Not for app5 (reminder sent at/after follow_up_date)
        # Not for app6 (no email)
        # Not for app7 (reminder sent at/after follow_up_date)

        result = job_tasks.send_application_follow_up_reminders()

        self.assertEqual(result['sent_count'], 3)
        self.assertEqual(self.mock_send_mail_task.call_count, 3)

        # Check app1
        self.app1.refresh_from_db()
        self.assertIsNotNone(self.app1.follow_up_reminder_sent_at)
        self.assertAlmostEqual(self.app1.follow_up_reminder_sent_at, self.mock_now_task, delta=timedelta(seconds=5))

        # Check app2
        self.app2.refresh_from_db()
        self.assertIsNotNone(self.app2.follow_up_reminder_sent_at)

        # Check app8
        self.app8.refresh_from_db()
        self.assertIsNotNone(self.app8.follow_up_reminder_sent_at)
        # Ensure the new reminder time is later than the old one
        self.assertTrue(self.app8.follow_up_reminder_sent_at > self.mock_now_task - timedelta(days=2))


        # Check app3 (should not have been updated beyond initial reminder)
        self.app3.refresh_from_db()
        self.assertAlmostEqual(self.app3.follow_up_reminder_sent_at, self.mock_now_task - timedelta(hours=1), delta=timedelta(seconds=5))

        # Check app6 (no email, reminder_sent_at should not be set by this task run)
        self.app6.refresh_from_db()
        self.assertIsNone(self.app6.follow_up_reminder_sent_at)

        # Verify email content for one of them (e.g., app1)
        # Need to find the correct call from call_args_list
        found_app1_email = False
        for call_args in self.mock_send_mail_task.call_args_list:
            args, kwargs = call_args
            if self.user1.email in kwargs['recipient_list'] and self.app1.job.title in kwargs['subject']:
                self.assertEqual(kwargs['subject'], f"Reminder: Follow up on your application for '{self.app1.job.title}'")
                self.assertIn(f"Hello {self.user1.first_name}", kwargs['message'])
                self.assertIn(self.app1.job.title, kwargs['message'])
                self.assertIn(self.app1.job.company, kwargs['message'])
                self.assertEqual(kwargs['from_email'], self.mock_settings_task.DEFAULT_FROM_EMAIL)
                found_app1_email = True
                break
        self.assertTrue(found_app1_email, "Email for app1 was not sent or arguments were incorrect.")

    def test_no_reminders_due(self):
        # Set all follow_up_dates to the future or reminders already sent appropriately
        ActualApplication.objects.all().update(follow_up_date=self.mock_now_task.date() + timedelta(days=5))

        result = job_tasks.send_application_follow_up_reminders()
        self.assertEqual(result['status'], 'no_reminders_due')
        self.assertEqual(result['sent_count'], 0)
        self.mock_send_mail_task.assert_not_called()

    def test_user_with_no_email_is_skipped(self):
        # Ensure only app6 (user_no_email) is due
        ActualApplication.objects.all().delete() # Clear other apps for this specific test
        app_no_email = ActualApplication.objects.create(
            user=self.user_no_email, job=self.job1, follow_up_date=self.mock_now_task.date()
        )

        result = job_tasks.send_application_follow_up_reminders()
        self.assertEqual(result['sent_count'], 0)
        self.assertEqual(result['processed_count'], 1) # Processed one app
        self.mock_send_mail_task.assert_not_called()
        app_no_email.refresh_from_db()
        self.assertIsNone(app_no_email.follow_up_reminder_sent_at) # Should not be updated
