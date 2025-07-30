from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

User = get_user_model()


class UserRegistrationTest(APITestCase):
    def setUp(self):
        self.register_url = reverse("register")
        self.user_data = {
            "email": "test@example.com",
            "first_name": "Test",
            "last_name": "User",
            "password": "testpassword123",
            "password_confirm": "testpassword123",
        }

    def test_user_registration_success(self):
        """
        Ensure a new user can be registered successfully.
        """
        response = self.client.post(self.register_url, self.user_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(User.objects.count(), 1)
        self.assertEqual(User.objects.get().email, "test@example.com")
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)

    def test_user_registration_email_exists(self):
        """
        Ensure registration fails if the email already exists.
        """
        # Create a user with the same email first
        User.objects.create_user(
            email="test@example.com",
            password="anotherpassword",
        )

        response = self.client.post(self.register_url, self.user_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(User.objects.count(), 1)
        self.assertIn("email", response.data)
