"""
Tests for the communication system.
"""

import json
from unittest.mock import MagicMock, patch

from channels.db import database_sync_to_async
from channels.testing import WebsocketCommunicator
from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, TransactionTestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.chat.consumers import ChatConsumer
from apps.chat.models import ChatMessage, ChatSession
from apps.jobs.models import Application, Job, JobAlert
from apps.notifications.email_service import EmailService
from apps.notifications.tasks import (send_application_status_update_task,
                                      send_job_alert_email_task,
                                      send_welcome_email_task)
from jobraker.asgi import application

User = get_user_model()


class EmailServiceTestCase(TestCase):
    """Test cases for EmailService."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="test@example.com", password="testpass123"
        )
        self.email_service = EmailService()

    def test_send_welcome_email(self):
        """Test sending welcome email."""
        # Clear any existing emails
        mail.outbox = []

        success = self.email_service.send_welcome_email(self.user)

        self.assertTrue(success)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Welcome to Jobraker", mail.outbox[0].subject)
        self.assertIn(self.user.email, mail.outbox[0].to)

    def test_send_job_recommendation_email(self):
        """Test sending job recommendation email."""
        mail.outbox = []

        recommendations = [
            {
                "id": 1,
                "title": "Python Developer",
                "company": "Tech Corp",
                "location": "San Francisco",
                "salary_min": 100000,
                "salary_max": 150000,
                "job_type": "full-time",
                "description": "Great job opportunity",
                "similarity_score": 92.5,
            }
        ]

        success = self.email_service.send_job_recommendation_email(
            self.user, recommendations
        )

        self.assertTrue(success)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Job Recommendations", mail.outbox[0].subject)
        self.assertIn("Python Developer", mail.outbox[0].body)

    def test_send_application_status_update(self):
        """Test sending application status update email."""
        mail.outbox = []

        job = Job.objects.create(
            title="Test Job",
            company="Test Company",
            description="Test description",
            is_active=True,
        )

        application = Application.objects.create(
            user=self.user, job=job, status="submitted"
        )

        success = self.email_service.send_application_status_update(
            application, "draft"
        )

        self.assertTrue(success)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Application Update", mail.outbox[0].subject)
        self.assertIn("Test Job", mail.outbox[0].body)


class EmailTaskTestCase(TestCase):
    """Test cases for email Celery tasks."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="test@example.com", password="testpass123"
        )

    @patch("apps.notifications.tasks.EmailService.send_welcome_email")
    def test_send_welcome_email_task(self, mock_send_email):
        """Test welcome email task."""
        mock_send_email.return_value = True

        result = send_welcome_email_task(self.user.id)

        mock_send_email.assert_called_once_with(user=self.user)

    @patch("apps.notifications.tasks.EmailService.send_job_alert_email")
    def test_send_job_alert_email_task(self, mock_send_email):
        """Test job alert email task."""
        mock_send_email.return_value = True

        alert = JobAlert.objects.create(
            user=self.user,
            title="Python Developer",
            location="San Francisco",
            is_active=True,
        )

        result = send_job_alert_email_task(alert.id)

        # Task should complete without error
        self.assertIsNone(result)


class ChatWebSocketTestCase(TransactionTestCase):
    """Test cases for WebSocket chat functionality."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="test@example.com", password="testpass123"
        )
        self.session = ChatSession.objects.create(user=self.user)

    async def test_chat_consumer_connect(self):
        """Test WebSocket connection to chat consumer."""
        communicator = WebsocketCommunicator(
            ChatConsumer.as_asgi(), f"/ws/chat/{self.session.id}/"
        )

        # Set user in scope
        communicator.scope["user"] = self.user

        connected, subprotocol = await communicator.connect()
        self.assertTrue(connected)

        # Test receiving connection established message
        response = await communicator.receive_json_from()
        self.assertEqual(response["type"], "connection_established")

        await communicator.disconnect()

    async def test_chat_message_send(self):
        """Test sending chat message through WebSocket."""
        communicator = WebsocketCommunicator(
            ChatConsumer.as_asgi(), f"/ws/chat/{self.session.id}/"
        )

        communicator.scope["user"] = self.user

        connected, subprotocol = await communicator.connect()
        self.assertTrue(connected)

        # Skip connection message
        await communicator.receive_json_from()

        # Send test message
        await communicator.send_json_to(
            {"type": "message", "message": "Hello, assistant!"}
        )

        # Should receive user message back
        response = await communicator.receive_json_from()
        self.assertEqual(response["type"], "message")
        self.assertEqual(response["message"]["content"], "Hello, assistant!")
        self.assertEqual(response["message"]["sender"], "user")

        await communicator.disconnect()


class ChatAPITestCase(APITestCase):
    """Test cases for Chat API endpoints."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="test@example.com", password="testpass123"
        )
        self.client.force_authenticate(user=self.user)

    def test_create_chat_session(self):
        """Test creating a new chat session."""
        url = reverse("chatsession-list")
        response = self.client.post(url, {})

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(ChatSession.objects.filter(user=self.user).exists())

    def test_send_chat_message(self):
        """Test sending a message through API."""
        session = ChatSession.objects.create(user=self.user)
        url = reverse("chatsession-messages", kwargs={"session_id": session.id})

        data = {"content": "Hello, can you help me with job searching?"}

        response = self.client.post(url, data)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(
            ChatMessage.objects.filter(
                session=session, content=data["content"]
            ).exists()
        )

    def test_get_chat_messages(self):
        """Test retrieving chat messages."""
        session = ChatSession.objects.create(user=self.user)

        # Create some messages
        ChatMessage.objects.create(session=session, content="Hello!", role="user")
        ChatMessage.objects.create(
            session=session, content="Hi there! How can I help you?", role="assistant"
        )

        url = reverse("chat:message-list", kwargs={"session_id": session.id})
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)


class NotificationSignalTestCase(TestCase):
    """Test cases for notification signals."""

    def test_welcome_email_signal(self):
        """Test that welcome email is triggered on user creation."""
        with patch("apps.notifications.signals.send_welcome_email_task") as mock_task:
            mock_task.delay = MagicMock()

            user = User.objects.create_user(
                email="newuser@example.com", password="testpass123"
            )

            mock_task.delay.assert_called_once_with(user.id)

    def test_application_status_update_signal(self):
        """Test that status update email is triggered on application status change."""
        job = Job.objects.create(
            title="Test Job",
            company="Test Company",
            description="Test description",
            is_active=True,
        )

        user = User.objects.create_user(
            email="test@example.com", password="testpass123"
        )

        application = Application.objects.create(user=user, job=job, status="submitted")

        with patch(
            "apps.notifications.signals.send_application_status_update_task"
        ) as mock_task:
            mock_task.delay = MagicMock()

            # Update status
            application.status = "under_review"
            application.save()

            mock_task.delay.assert_called_once_with(application.id, "submitted")


class EmailTemplateTestCase(TestCase):
    """Test cases for email templates."""

    def test_welcome_email_template(self):
        """Test welcome email template rendering."""
        from django.template.loader import render_to_string

        user = User.objects.create_user(
            email="test@example.com", first_name="John", last_name="Doe"
        )

        context = {
            "user": user,
            "company_name": "Jobraker",
            "site_url": "https://jobraker.com",
            "support_email": "support@jobraker.com",
            "profile_url": "https://jobraker.com/profile",
        }

        html_content = render_to_string("emails/welcome.html", context)

        self.assertIn("Welcome to Jobraker", html_content)
        self.assertIn("John", html_content)
        self.assertIn("Complete Profile", html_content)

    def test_job_alert_email_template(self):
        """Test job alert email template rendering."""
        from django.template.loader import render_to_string

        user = User.objects.create_user(email="test@example.com", first_name="John")

        alert = JobAlert.objects.create(
            user=user,
            title="Python Developer",
            location="San Francisco",
            is_active=True,
        )

        job = Job.objects.create(
            title="Senior Python Developer",
            company="Tech Corp",
            description="Great opportunity",
            location="San Francisco, CA",
            salary_min=120000,
            salary_max=150000,
            job_type="full-time",
            is_active=True,
        )

        context = {
            "user": user,
            "alert": alert,
            "jobs": [job],
            "total_jobs": 1,
            "company_name": "Jobraker",
            "site_url": "https://jobraker.com",
            "support_email": "support@jobraker.com",
            "view_more_url": "https://jobraker.com/jobs",
        }

        html_content = render_to_string("emails/job_alert.html", context)

        self.assertIn("New Job Alert", html_content)
        self.assertIn("Senior Python Developer", html_content)
        self.assertIn("Tech Corp", html_content)
        self.assertIn("San Francisco", html_content)


class CelerySchedulingTestCase(TestCase):
    """Test cases for Celery scheduled tasks."""

    def test_celery_beat_configuration(self):
        """Test that Celery beat tasks are properly configured."""
        from jobraker.celery import app

        # Check that scheduled tasks are configured
        beat_schedule = app.conf.beat_schedule

        # Check for email-related tasks
        self.assertIn("process-daily-job-alerts", beat_schedule)
        self.assertIn("process-weekly-job-alerts", beat_schedule)
        self.assertIn("send-weekly-job-recommendations", beat_schedule)
        self.assertIn("send-application-follow-up-reminders-enhanced", beat_schedule)

        # Check task configurations
        daily_alerts = beat_schedule["process-daily-job-alerts"]
        self.assertEqual(
            daily_alerts["task"], "apps.notifications.tasks.process_daily_job_alerts"
        )

        weekly_alerts = beat_schedule["process-weekly-job-alerts"]
        self.assertEqual(
            weekly_alerts["task"], "apps.notifications.tasks.process_weekly_job_alerts"
        )


class CommunicationSystemIntegrationTestCase(TestCase):
    """Integration tests for the complete communication system."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="test@example.com", password="testpass123"
        )

    def test_complete_user_workflow(self):
        """Test complete user workflow with notifications."""
        # User registration should trigger welcome email
        with patch(
            "apps.notifications.signals.send_welcome_email_task"
        ) as mock_welcome:
            mock_welcome.delay = MagicMock()

            new_user = User.objects.create_user(
                email="newuser@example.com", password="testpass123"
            )

            mock_welcome.delay.assert_called_once_with(new_user.id)

        # Job application should trigger status update
        job = Job.objects.create(
            title="Test Job",
            company="Test Company",
            description="Test description",
            is_active=True,
        )

        application = Application.objects.create(
            user=self.user, job=job, status="submitted"
        )

        with patch(
            "apps.notifications.signals.send_application_status_update_task"
        ) as mock_update:
            mock_update.delay = MagicMock()

            # Update application status
            application.status = "under_review"
            application.save()

            mock_update.delay.assert_called_once_with(application.id, "submitted")

        # Job alert should trigger email
        alert = JobAlert.objects.create(
            user=self.user, title="Python Developer", is_active=True
        )

        with patch(
            "apps.notifications.tasks.EmailService.send_job_alert_email"
        ) as mock_alert:
            mock_alert.return_value = True

            from apps.notifications.tasks import send_job_alert_email_task

            send_job_alert_email_task(alert.id)

            mock_alert.assert_called_once()

    def test_email_service_error_handling(self):
        """Test email service error handling."""
        email_service = EmailService()

        # Test with invalid user
        with patch("apps.notifications.email_service.logger") as mock_logger:
            success = email_service.send_welcome_email(None)

            self.assertFalse(success)
            mock_logger.error.assert_called()

    def test_bulk_email_sending(self):
        """Test bulk email sending functionality."""
        # Create multiple users
        users = []
        for i in range(3):
            user = User.objects.create_user(
                email=f"user{i}@example.com", password="testpass123"
            )
            users.append(user)

        email_service = EmailService()

        results = email_service.send_bulk_notification(
            users=users,
            subject="Test Bulk Email",
            template_name="welcome",
            context={"company_name": "Jobraker"},
        )

        self.assertEqual(results["success"], 3)
        self.assertEqual(results["failed"], 0)
        self.assertEqual(len(mail.outbox), 3)
