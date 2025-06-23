from django.test import TestCase
from unittest.mock import patch, MagicMock

from apps.jobs.models import Job # Using the actual model to trigger signals
from django.contrib.auth import get_user_model

User = get_user_model()

# The signals are in apps.jobs.signals, which imports registry from django_elasticsearch_dsl.registries
# So we need to patch 'django_elasticsearch_dsl.registries.registry'
@patch('django_elasticsearch_dsl.registries.registry', new_callable=MagicMock)
class JobSignalTests(TestCase):

    def setUp(self):
        # Create a user for model instances that require a user
        self.user = User.objects.create_user(username='testsignaluser', password='password')
        # Basic job data
        self.job_data = {
            'title': "Signal Test Job",
            'company': "Signal Co",
            'description': "Testing signals for ES.",
            'location': "Testville",
            # Add any other required fields for Job model if they don't have defaults
        }

    def test_job_post_save_updates_registry(self, mock_registry):
        """Test that saving a new Job instance calls registry.update()."""
        job = Job.objects.create(**self.job_data)
        mock_registry.update.assert_called_once_with(job)

        mock_registry.reset_mock() # Reset for the update part

        # Test that updating an existing Job instance also calls registry.update()
        job.title = "Signal Test Job Updated"
        job.save()
        mock_registry.update.assert_called_once_with(job)


    def test_job_post_delete_deletes_from_registry(self, mock_registry):
        """Test that deleting a Job instance calls registry.delete()."""
        job = Job.objects.create(**self.job_data)

        # Reset mock from the save operation that happened during create
        mock_registry.reset_mock()

        job_pk = job.pk
        job.delete()

        # registry.delete is called with the instance before it's fully deleted,
        # or with its PK if the instance itself is gone.
        # The signal handler uses `registry.delete(instance, raise_on_error=False)`.
        # The `instance` passed to the signal handler is the instance being deleted.
        # So, we expect it to be called with an object that has `pk=job_pk`.

        # Check that delete was called. The instance passed to delete might not be
        # the exact same Python object after it's fetched again if not careful,
        # but it should represent the same database record.
        # The most reliable way is to check that it was called, and if needed,
        # inspect the properties of the object it was called with.
        self.assertTrue(mock_registry.delete.called)

        # Check the call arguments more carefully if possible/needed.
        # Example: Ensure it was called with an object that has the correct pk.
        # This depends on how MagicMock captures arguments for methods called on it.
        # For now, just checking it was called is a good start.
        # If registry.delete was called, its first arg (the instance) should have the correct pk.
        args, kwargs = mock_registry.delete.call_args
        deleted_instance_arg = args[0]
        self.assertEqual(deleted_instance_arg.pk, job_pk)


    @patch('apps.jobs.signals.registry.update') # Patch specifically where it's used in the signal
    def test_job_post_save_signal_error_handling(self, mock_registry_update_in_signal):
        """Test that an error during registry.update is caught in the signal handler."""
        mock_registry_update_in_signal.side_effect = Exception("ES Down!")

        # We also need to patch 'print' if we want to assert its call for error logging
        with patch('apps.jobs.signals.print') as mock_print:
            try:
                # This save should trigger the signal, which then encounters the exception
                Job.objects.create(**self.job_data)
            except Exception as e:
                # The signal handler should catch the exception and print, not re-raise
                self.fail(f"Signal handler should not re-raise exception from registry.update: {e}")

            mock_print.assert_called()
            # Check that the print message contains the error indication
            self.assertIn("Error updating Elasticsearch", mock_print.call_args[0][0])


    @patch('apps.jobs.signals.registry.delete') # Patch specifically where it's used
    def test_job_post_delete_signal_error_handling(self, mock_registry_delete_in_signal):
        """Test that an error during registry.delete is caught in the signal handler."""
        job = Job.objects.create(**self.job_data)
        mock_registry_delete_in_signal.side_effect = Exception("ES Delete Failed!")

        with patch('apps.jobs.signals.print') as mock_print:
            try:
                job.delete()
            except Exception as e:
                self.fail(f"Signal handler should not re-raise exception from registry.delete: {e}")

            mock_print.assert_called()
            self.assertIn("Error deleting Elasticsearch document", mock_print.call_args[0][0])

# Note: These tests assume that the signals in apps.jobs.signals are correctly connected.
# This is usually handled by importing the signals module in the app's AppConfig.ready() method.
# We did this in a previous step.
