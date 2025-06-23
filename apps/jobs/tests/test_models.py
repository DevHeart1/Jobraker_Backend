from django.test import TestCase
from django.contrib.auth import get_user_model
from apps.jobs.models import JobAlert, Job # Job is needed for JobTypeChoices if used directly

User = get_user_model()

class JobAlertModelTest(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            username='testuseralert',
            email='testuseralert@example.com',
            password='password123'
        )
        self.alert = JobAlert.objects.create(
            user=self.user,
            name="Test Python Alert",
            keywords=["Python", "Developer"],
            location="Remote",
            frequency=JobAlert.FREQUENCY_CHOICES.DAILY, # Accessing choices as defined in existing model
            is_active=True
        )

    def test_job_alert_creation(self):
        self.assertIsInstance(self.alert, JobAlert)
        self.assertEqual(self.alert.name, "Test Python Alert")
        self.assertEqual(self.alert.user.email, 'testuseralert@example.com')
        self.assertEqual(self.alert.keywords, ["Python", "Developer"])
        self.assertTrue(self.alert.is_active)
        self.assertEqual(self.alert.frequency, 'daily')

    def test_job_alert_str_representation(self):
        self.assertEqual(str(self.alert), "Test Python Alert for testuseralert@example.com")

        unnamed_alert = JobAlert.objects.create(user=self.user)
        # Assuming email is preferred, if not username. User model might not have get_full_name without customization.
        # The model's __str__ uses: f"{self.name or 'Unnamed Alert'} for {self.user.email or self.user.username}"
        self.assertEqual(str(unnamed_alert), f"Unnamed Alert for {self.user.email}")

    def test_job_alert_default_values(self):
        alert_with_defaults = JobAlert.objects.create(user=self.user, name="Defaults Test")
        self.assertTrue(alert_with_defaults.is_active)
        self.assertEqual(alert_with_defaults.frequency, JobAlert.FREQUENCY_CHOICES.DAILY) # Default is 'daily'
        self.assertEqual(alert_with_defaults.keywords, []) # Default for JSONField is list

    # The can_send_notification method was my proposal, it's not on the existing model.
    # That logic is now within the task. So, no model method test for that.

    # Test choices if needed, though Django handles this well.
    def test_frequency_choices(self):
        # Ensure the choices used in the model are what we expect
        # Example: Check if 'daily' is a valid choice value
        valid_frequency_values = [choice[0] for choice in JobAlert.FREQUENCY_CHOICES]
        self.assertIn('daily', valid_frequency_values)
        self.assertIn('weekly', valid_frequency_values)
        self.assertIn('monthly', valid_frequency_values)
        self.assertIn('immediate', valid_frequency_values)

    def test_job_type_choices_on_job_model(self): # JobAlert uses Job.JOB_TYPES
        valid_job_type_values = [choice[0] for choice in Job.JOB_TYPES]
        self.assertIn('full_time', valid_job_type_values)
        # Add more checks if necessary


from apps.jobs.models import Application # Import Application model
from django.utils import timezone

class ApplicationModelAdvancedTrackingTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testappuser', email='testappuser@example.com', password='password')
        self.job = Job.objects.create(title="Test Job for App", company="Test Co", description="Desc", location="Loc")
        self.application = Application.objects.create(user=self.user, job=self.job)

    def test_application_new_fields_defaults(self):
        self.assertIsNone(self.application.user_defined_status)
        self.assertEqual(self.application.user_notes, "")
        self.assertEqual(self.application.interview_details, []) # Default is list
        self.assertEqual(self.application.offer_details, {})   # Default is dict
        self.assertIsNone(self.application.follow_up_reminder_sent_at)
        # follow_up_date is already in the model, defaults to None/null
        self.assertIsNone(self.application.follow_up_date)

    def test_application_user_defined_status_choices(self):
        self.application.user_defined_status = 'interviewing' # Example valid choice from plan
        # This test assumes 'interviewing' will be a valid choice.
        # A more robust test would iterate Application.USER_DEFINED_STATUS_CHOICES
        # For now, this is a placeholder, actual choices need to be used.
        # Let's use one of the actual choices I defined:
        self.application.user_defined_status = Application.USER_DEFINED_STATUS_CHOICES[4][0] # 'initial_interview'
        self.application.save()
        self.application.refresh_from_db()
        self.assertEqual(self.application.user_defined_status, 'initial_interview')

    def test_application_json_fields(self):
        interview_data = [{"date": "2024-01-01T10:00:00Z", "type": "phone screen", "notes": "Good call."}]
        offer_data = {"salary": 100000, "bonus": 5000, "start_date": "2024-02-01"}

        self.application.interview_details = interview_data
        self.application.offer_details = offer_data
        self.application.save()
        self.application.refresh_from_db()

        self.assertEqual(self.application.interview_details, interview_data)
        self.assertEqual(self.application.offer_details, offer_data)

    def test_application_date_fields(self):
        now = timezone.now()
        self.application.follow_up_date = now.date()
        self.application.follow_up_reminder_sent_at = now
        self.application.save()
        self.application.refresh_from_db()

        self.assertEqual(self.application.follow_up_date, now.date())
        # Comparing datetimes can be tricky due to microseconds. Assert they are close.
        self.assertAlmostEqual(self.application.follow_up_reminder_sent_at, now, delta=timezone.timedelta(seconds=1))
