import hashlib
import hmac
import json
from unittest.mock import MagicMock, patch

from django.test import Client, TestCase, override_settings
from django.urls import reverse

# from apps.jobs.models import Application # Will be mocked
# from apps.integrations.views import WebhookView # To test methods directly if needed, or via client


# Mock Application model for tests
class MockApplicationInstance:
    def __init__(self, id, skyvern_task_id, status="pending"):
        self.id = id
        self.skyvern_task_id = skyvern_task_id
        self.status = status
        self.skyvern_response_data = {}
        self.applied_at = None
        self._save_update_fields = None  # To capture update_fields

    def save(self, update_fields=None):
        self._save_update_fields = update_fields  # Store for assertion
        pass


class MockApplicationManager:
    def get(self, skyvern_task_id=None, id=None):  # Allow get by id or skyvern_task_id
        if hasattr(self, "_get_return_value"):
            if isinstance(self._get_return_value, Exception):
                raise self._get_return_value
            return self._get_return_value
        raise Exception(
            "MockApplicationManager.get not configured"
        )  # Should be DoesNotExist

    def __init__(self):
        self._get_return_value = None
        # Define DoesNotExist as an exception class specific to this mock manager
        self.DoesNotExist = type("DoesNotExist", (Exception,), {})


@override_settings(SKYVERN_WEBHOOK_SECRET="testsecret")  # Set a default test secret
@patch(
    "apps.integrations.views.Application", new_callable=MagicMock
)  # Patch Application model in views
@patch("apps.integrations.views.logging.getLogger")  # Patch logger
class TestSkyvernWebhookView(TestCase):

    def setUp(self):
        self.client = Client()
        self.webhook_url = reverse(
            "webhook_receiver", kwargs={"service": "skyvern"}
        )  # Assuming URL name

        # Configure the mock Application model's manager
        self.MockApplicationModel = self.get_patched_application_model_class()
        self.mock_app_manager = MockApplicationManager()
        self.MockApplicationModel.objects = self.mock_app_manager
        self.MockApplicationModel.DoesNotExist = self.mock_app_manager.DoesNotExist

    def get_patched_application_model_class(self):
        # This is a bit of a workaround to get the actual patched class instance
        # if the patch decorator is on the class.
        # Alternatively, patch 'apps.jobs.models.Application' directly in each test method
        # or ensure the class-level patch object is correctly retrieved.
        # For simplicity, let's assume the class-level patch directly gives us the mock.
        # The patch on the class TestSkyvernWebhookView should make Application a MagicMock.
        # We need to access it via the module where it's patched.
        from apps.integrations import views  # views imports Application

        return views.Application

    def _generate_signature(self, payload_body_bytes, secret):
        return hmac.new(
            secret.encode("utf-8"), payload_body_bytes, hashlib.sha256
        ).hexdigest()

    @patch("apps.integrations.views.timezone.now")
    def test_webhook_valid_payload_completed(
        self, mock_timezone_now, mock_logger_getLogger, MockApplicationCls
    ):
        mock_logger = mock_logger_getLogger.return_value
        mock_now = "mocked_datetime_for_applied_at"
        mock_timezone_now.return_value = mock_now

        task_id = "sky_task_completed_123"
        app_id = "app_uuid_123"
        mock_app_instance = MockApplicationInstance(
            id=app_id, skyvern_task_id=task_id, status="submitting_via_skyvern"
        )
        self.mock_app_manager._get_return_value = mock_app_instance

        payload = {
            "task_id": task_id,
            "status": "COMPLETED",
            "data": {"confirmation_id": "conf_abc", "submitted_on": "2023-01-01"},
        }
        payload_bytes = json.dumps(payload).encode("utf-8")
        signature = self._generate_signature(payload_bytes, "testsecret")

        response = self.client.post(
            self.webhook_url,
            data=payload_bytes,
            content_type="application/json",
            HTTP_X_SKYVERN_SIGNATURE=signature,  # Example header
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json().get("application_updated"))
        self.assertEqual(mock_app_instance.status, "submitted")
        self.assertEqual(mock_app_instance.applied_at, mock_now)
        self.assertEqual(
            mock_app_instance.skyvern_response_data,
            {"confirmation_id": "conf_abc", "submitted_on": "2023-01-01"},
        )
        self.assertIn("applied_at", mock_app_instance._save_update_fields)
        self.assertIn("skyvern_response_data", mock_app_instance._save_update_fields)
        self.assertIn("status", mock_app_instance._save_update_fields)

    def test_webhook_invalid_signature(self, mock_logger_getLogger, MockApplicationCls):
        mock_logger = mock_logger_getLogger.return_value
        payload = {"task_id": "task1", "status": "COMPLETED"}
        payload_bytes = json.dumps(payload).encode("utf-8")
        # No or incorrect signature
        response = self.client.post(
            self.webhook_url,
            data=payload_bytes,
            content_type="application/json",
            HTTP_X_SKYVERN_SIGNATURE="wrong_signature",
        )
        self.assertEqual(response.status_code, 403)  # Forbidden
        self.assertIn("Invalid signature", response.json().get("error", "").lower())

    @override_settings(SKYVERN_WEBHOOK_SECRET=None)  # Test case where secret is not set
    def test_webhook_no_secret_configured_should_fail_verification(
        self, mock_logger_getLogger, MockApplicationCls
    ):
        mock_logger = mock_logger_getLogger.return_value
        # The _verify_skyvern_webhook_signature in views.py was changed to FAIL if secret is not set.
        # Previous dev-friendly version allowed it. This test assumes the secure version.
        payload = {"task_id": "task1", "status": "COMPLETED"}
        payload_bytes = json.dumps(payload).encode("utf-8")
        response = self.client.post(
            self.webhook_url,
            data=payload_bytes,
            content_type="application/json",
            HTTP_X_SKYVERN_SIGNATURE="any_sig",
        )
        self.assertEqual(
            response.status_code, 403
        )  # Should be forbidden as verification fails without secret
        # Check logs for specific message about missing secret
        # This requires inspecting mock_logger calls, which can be added if needed.

    def test_webhook_malformed_json(self, mock_logger_getLogger, MockApplicationCls):
        mock_logger = mock_logger_getLogger.return_value
        malformed_json_bytes = b"{'task_id': '123', not_json}"
        signature = self._generate_signature(malformed_json_bytes, "testsecret")
        response = self.client.post(
            self.webhook_url,
            data=malformed_json_bytes,
            content_type="application/json",
            HTTP_X_SKYVERN_SIGNATURE=signature,
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("invalid json", response.json().get("error", "").lower())

    def test_webhook_missing_task_id(self, mock_logger_getLogger, MockApplicationCls):
        mock_logger = mock_logger_getLogger.return_value
        payload = {"status": "COMPLETED"}  # Missing task_id
        payload_bytes = json.dumps(payload).encode("utf-8")
        signature = self._generate_signature(payload_bytes, "testsecret")
        response = self.client.post(
            self.webhook_url,
            data=payload_bytes,
            content_type="application/json",
            HTTP_X_SKYVERN_SIGNATURE=signature,
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn(
            "missing task_id or status", response.json().get("error", "").lower()
        )

    def test_webhook_application_not_found(
        self, mock_logger_getLogger, MockApplicationCls
    ):
        mock_logger = mock_logger_getLogger.return_value
        self.mock_app_manager._get_return_value = (
            self.MockApplicationModel.DoesNotExist("Not found")
        )  # Raise DoesNotExist

        payload = {"task_id": "unknown_task_id", "status": "COMPLETED"}
        payload_bytes = json.dumps(payload).encode("utf-8")
        signature = self._generate_signature(payload_bytes, "testsecret")
        response = self.client.post(
            self.webhook_url,
            data=payload_bytes,
            content_type="application/json",
            HTTP_X_SKYVERN_SIGNATURE=signature,
        )

        self.assertEqual(
            response.status_code, 200
        )  # As per current logic, acknowledge even if app not found
        self.assertIn(
            "webhook received for unknown task_id",
            response.json().get("message", "").lower(),
        )

    def test_webhook_status_failed_updates_application(
        self, mock_logger_getLogger, MockApplicationCls
    ):
        mock_logger = mock_logger_getLogger.return_value
        task_id = "sky_task_failed_456"
        app_id = "app_uuid_456"
        mock_app_instance = MockApplicationInstance(
            id=app_id, skyvern_task_id=task_id, status="submitting_via_skyvern"
        )
        self.mock_app_manager._get_return_value = mock_app_instance

        error_payload = {"error_code": "E123", "message": "Something went wrong"}
        payload = {
            "task_id": task_id,
            "status": "FAILED",
            "error_details": error_payload,
        }
        payload_bytes = json.dumps(payload).encode("utf-8")
        signature = self._generate_signature(payload_bytes, "testsecret")

        response = self.client.post(
            self.webhook_url,
            data=payload_bytes,
            content_type="application/json",
            HTTP_X_SKYVERN_SIGNATURE=signature,
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json().get("application_updated"))
        self.assertEqual(mock_app_instance.status, "skyvern_submission_failed")
        self.assertEqual(mock_app_instance.skyvern_response_data, error_payload)

    def test_webhook_status_skyvern_canceled(
        self, mock_logger_getLogger, MockApplicationCls
    ):
        mock_logger = mock_logger_getLogger.return_value
        task_id = "sky_task_canceled_123"
        app_id = "app_uuid_canceled_123"
        mock_app_instance = MockApplicationInstance(id=app_id, skyvern_task_id=task_id)
        self.mock_app_manager._get_return_value = mock_app_instance

        payload_data = {"reason": "User initiated cancellation"}
        payload = {"task_id": task_id, "status": "CANCELED", "data": payload_data}
        payload_bytes = json.dumps(payload).encode("utf-8")
        signature = self._generate_signature(payload_bytes, "testsecret")

        response = self.client.post(
            self.webhook_url,
            data=payload_bytes,
            content_type="application/json",
            HTTP_X_SKYVERN_SIGNATURE=signature,
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json().get("application_updated"))
        self.assertEqual(mock_app_instance.status, "skyvern_canceled")
        self.assertEqual(
            mock_app_instance.skyvern_response_data,
            {"status_reason": "canceled", "details": payload_data},
        )

    def test_webhook_status_skyvern_requires_attention(
        self, mock_logger_getLogger, MockApplicationCls
    ):
        mock_logger = mock_logger_getLogger.return_value
        task_id = "sky_task_attention_123"
        app_id = "app_uuid_attention_123"
        mock_app_instance = MockApplicationInstance(id=app_id, skyvern_task_id=task_id)
        self.mock_app_manager._get_return_value = mock_app_instance

        payload_data = {"message": "CAPTCHA required"}
        payload = {
            "task_id": task_id,
            "status": "REQUIRES_ATTENTION",
            "data": payload_data,
        }
        payload_bytes = json.dumps(payload).encode("utf-8")
        signature = self._generate_signature(payload_bytes, "testsecret")

        response = self.client.post(
            self.webhook_url,
            data=payload_bytes,
            content_type="application/json",
            HTTP_X_SKYVERN_SIGNATURE=signature,
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json().get("application_updated"))
        self.assertEqual(mock_app_instance.status, "skyvern_requires_attention")
        self.assertEqual(mock_app_instance.skyvern_response_data, payload_data)

    def test_webhook_status_skyvern_pending_updates_if_needed(
        self, mock_logger_getLogger, MockApplicationCls
    ):
        mock_logger = mock_logger_getLogger.return_value
        task_id = "sky_task_pending_123"
        app_id = "app_uuid_pending_123"
        # Start with an initial 'pending' status to see if it changes to 'submitting_via_skyvern'
        mock_app_instance = MockApplicationInstance(
            id=app_id, skyvern_task_id=task_id, status="pending"
        )
        self.mock_app_manager._get_return_value = mock_app_instance

        payload = {"task_id": task_id, "status": "PENDING"}
        payload_bytes = json.dumps(payload).encode("utf-8")
        signature = self._generate_signature(payload_bytes, "testsecret")

        response = self.client.post(
            self.webhook_url,
            data=payload_bytes,
            content_type="application/json",
            HTTP_X_SKYVERN_SIGNATURE=signature,
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json().get("application_updated"))  # Status changed
        self.assertEqual(mock_app_instance.status, "submitting_via_skyvern")

    def test_webhook_status_skyvern_running_no_change_if_already_submitting(
        self, mock_logger_getLogger, MockApplicationCls
    ):
        mock_logger = mock_logger_getLogger.return_value
        task_id = "sky_task_running_123"
        app_id = "app_uuid_running_123"
        # Start with 'submitting_via_skyvern'
        mock_app_instance = MockApplicationInstance(
            id=app_id, skyvern_task_id=task_id, status="submitting_via_skyvern"
        )
        self.mock_app_manager._get_return_value = mock_app_instance

        payload = {"task_id": task_id, "status": "RUNNING"}
        payload_bytes = json.dumps(payload).encode("utf-8")
        signature = self._generate_signature(payload_bytes, "testsecret")

        response = self.client.post(
            self.webhook_url,
            data=payload_bytes,
            content_type="application/json",
            HTTP_X_SKYVERN_SIGNATURE=signature,
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            response.json().get("application_updated")
        )  # Status did not change
        self.assertEqual(mock_app_instance.status, "submitting_via_skyvern")

    # Add more tests for other statuses like CANCELED, REQUIRES_ATTENTION, PENDING/RUNNING if different logic applies
    # Add test for MultipleObjectsReturned if that's a concern.
    def test_webhook_multiple_applications_returned(
        self, mock_logger_getLogger, MockApplicationCls
    ):
        mock_logger = mock_logger_getLogger.return_value
        # Configure the mock manager to raise MultipleObjectsReturned
        self.MockApplicationModel.MultipleObjectsReturned = type(
            "MultipleObjectsReturned", (Exception,), {}
        )
        self.mock_app_manager._get_return_value = (
            self.MockApplicationModel.MultipleObjectsReturned("Multiple found")
        )

        payload = {"task_id": "multi_task_id", "status": "COMPLETED"}
        payload_bytes = json.dumps(payload).encode("utf-8")
        signature = self._generate_signature(payload_bytes, "testsecret")
        response = self.client.post(
            self.webhook_url,
            data=payload_bytes,
            content_type="application/json",
            HTTP_X_SKYVERN_SIGNATURE=signature,
        )

        self.assertEqual(response.status_code, 500)
        self.assertIn(
            "multiple applications for task_id",
            response.json().get("error", "").lower(),
        )


# Note: To run these tests, Django's test runner (`python manage.py test apps.integrations`) would be used.
# The `if __name__ == '__main__': unittest.main()` is for standalone execution if structure allows.
# The `reverse` function needs Django's URL configuration to be loaded.
# Ensure `SKYVERN_WEBHOOK_SECRET` is in test settings or overridden.
# The patch for Application model needs to be correct for where `views.py` imports it.
# Example: @patch('apps.integrations.views.Application', new_callable=MagicMock) on the class.
# The logger patch might also need to be specific to 'apps.integrations.views.logger'.
# Using Django's TestCase handles settings and URL reversing more naturally.
