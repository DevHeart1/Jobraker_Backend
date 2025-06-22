from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase, APIClient
from django.contrib.auth import get_user_model
from apps.jobs.models import Job, RecommendedJob, UserProfile # Assuming UserProfile is needed for user setup
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
