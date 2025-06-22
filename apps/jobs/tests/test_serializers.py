from django.test import TestCase
from django.contrib.auth import get_user_model
from apps.jobs.models import Job, RecommendedJob
from apps.jobs.serializers import RecommendedJobSerializer, JobListSerializer
import uuid

User = get_user_model()

class RecommendedJobSerializerTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(email='testuser@example.com', password='password123', first_name='Test', last_name='User')
        self.job = Job.objects.create(
            title="Software Engineer",
            company="Test Corp",
            description="A test job description.",
            location="Test City"
            # Add other required fields for Job model if any
        )
        self.recommendation_data = {
            'user': self.user,
            'job': self.job,
            'score': 0.85,
            'status': 'pending_review',
            'algorithm_version': 'v1_test'
        }
        self.recommendation = RecommendedJob.objects.create(**self.recommendation_data)
        self.serializer = RecommendedJobSerializer(instance=self.recommendation)

    def test_serializer_contains_expected_fields(self):
        """Test that the serializer includes all expected fields."""
        data = self.serializer.data
        expected_keys = ['id', 'job', 'score', 'status', 'algorithm_version', 'recommended_at', 'updated_at']
        self.assertEqual(set(data.keys()), set(expected_keys))

    def test_job_field_is_nested_joblistserializer(self):
        """Test that the 'job' field uses JobListSerializer for nested representation."""
        data = self.serializer.data
        # Check for a few key fields from JobListSerializer to confirm structure
        self.assertIn('id', data['job'])
        self.assertIn('title', data['job'])
        self.assertIn('company', data['job'])
        self.assertEqual(data['job']['title'], self.job.title)

    def test_score_field_content(self):
        """Test the content of the 'score' field."""
        data = self.serializer.data
        self.assertEqual(data['score'], self.recommendation_data['score'])

    def test_status_field_content(self):
        """Test the content of the 'status' field."""
        data = self.serializer.data
        self.assertEqual(data['status'], self.recommendation_data['status'])

    def test_algorithm_version_field_content(self):
        """Test the content of the 'algorithm_version' field."""
        data = self.serializer.data
        self.assertEqual(data['algorithm_version'], self.recommendation_data['algorithm_version'])

    def test_read_only_fields(self):
        """Test that certain fields are read-only."""
        # Attempt to create/update with read-only fields should ideally be tested
        # by trying to initialize serializer with data for these fields if it were writable.
        # For a ModelSerializer, read_only_fields are not included in validated_data for writes.
        # Here, we primarily confirm their presence in output and rely on DRF's handling.
        serializer = RecommendedJobSerializer(data={
            'user': self.user.id, # User is not typically set via serializer directly in this context
            'job': self.job.id,   # Job is not typically set via serializer directly
            'score': 0.99,
            'status': 'viewed', # Status might be updatable in some contexts, but here it's part of read_only_fields
            'algorithm_version': 'v2_test'
        })
        self.assertFalse(serializer.is_valid()) # Expect invalid as we are not providing required fields for create
                                               # and 'job' is read_only=True.

        # More directly, check if fields are marked as read_only in serializer.fields
        # This is a bit of an internal check.
        self.assertTrue(self.serializer.fields['id'].read_only)
        self.assertTrue(self.serializer.fields['job'].read_only)
        self.assertTrue(self.serializer.fields['score'].read_only)
        # self.assertTrue(self.serializer.fields['status'].read_only) # Status is NOT read_only if we want to update it
        self.assertTrue(self.serializer.fields['algorithm_version'].read_only)
        self.assertTrue(self.serializer.fields['recommended_at'].read_only)
        self.assertTrue(self.serializer.fields['updated_at'].read_only)

        # If status is meant to be updatable, its read_only status would be False.
        # The current serializer has 'status' in `fields` but not in `read_only_fields`,
        # implying it could be writable if the view supports it.
        # For a ListAPIView, the whole serializer acts as read-only.
        # Let's adjust the check for 'status' based on its intended use.
        # If the primary use is listing, then 'status' being part of the output is key.
        # If a PATCH operation were on this view, 'status' would be writable.
        # For now, assuming the serializer is for listing, so all listed fields are for output.
        # The `read_only_fields` in Meta correctly lists what's not writable.
        # The 'status' field *is* in `read_only_fields` as per current serializer Meta.
        self.assertTrue(self.serializer.fields['status'].read_only) # Confirming it's read-only as per Meta

    def test_timestamps_are_present_and_correct_format(self):
        """Test that timestamp fields are present and seem correctly formatted."""
        data = self.serializer.data
        self.assertIn('recommended_at', data)
        self.assertIn('updated_at', data)
        # Basic check for ISO-like format (DRF default)
        self.assertRegex(data['recommended_at'], r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+Z?')
        self.assertRegex(data['updated_at'], r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+Z?')

# To run these tests: python manage.py test apps.jobs.tests.test_serializers
