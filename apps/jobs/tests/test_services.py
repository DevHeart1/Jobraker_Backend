import unittest
import uuid  # For generating UUIDs for mock objects
from unittest.mock import MagicMock, PropertyMock, patch

# from apps.jobs.services import JobMatchService
# from apps.accounts.models import UserProfile # Mocked
# from apps.jobs.models import Job # Mocked
# from apps.common.services import VectorDBService # Mocked


# Mock models and services that JobMatchService depends on
class MockUserProfile:
    objects = MagicMock()

    def __init__(self, id, profile_embedding=None, skills_embedding=None):
        self.id = id
        self.profile_embedding = profile_embedding
        self.skills_embedding = skills_embedding
        # Add other fields if JobMatchService uses them directly


class MockJob:
    objects = MagicMock()

    def __init__(
        self, id, combined_embedding=None, job_embedding=None, status="active", **kwargs
    ):
        self.id = id
        self.combined_embedding = combined_embedding
        self.job_embedding = job_embedding  # Fallback
        self.status = status
        for key, value in kwargs.items():
            setattr(self, key, value)

    def __str__(self):
        return f"MockJob {self.id}"


class MockVectorDBService:
    search_similar_documents = MagicMock()

    def __init__(self):
        # Reset mock for each instance if necessary, or do it in setUp
        self.search_similar_documents.reset_mock()


class TestJobMatchService(unittest.TestCase):

    def setUp(self):
        # Patch UserProfile, Job, and VectorDBService where they are imported in apps.jobs.services
        self.patcher_user_profile = patch(
            "apps.jobs.services.UserProfile", new_callable=lambda: MockUserProfile
        )
        self.MockUserProfileModel = self.patcher_user_profile.start()
        self.MockUserProfileModel.objects = MagicMock()  # Mock the manager

        self.patcher_job = patch("apps.jobs.services.Job", new_callable=lambda: MockJob)
        self.MockJobModel = self.patcher_job.start()
        self.MockJobModel.objects = MagicMock()  # Mock the manager

        self.patcher_vdb_service = patch(
            "apps.jobs.services.VectorDBService",
            new_callable=lambda: MockVectorDBService,
        )
        self.MockVDBServiceClass = self.patcher_vdb_service.start()

        from apps.jobs.services import \
            JobMatchService  # Import service after patching

        self.job_match_service = JobMatchService()
        # Ensure the instance of VDBService used by JobMatchService is our MagicMock instance
        self.job_match_service.vector_db_service = self.MockVDBServiceClass()

    def tearDown(self):
        self.patcher_user_profile.stop()
        self.patcher_job.stop()
        self.patcher_vdb_service.stop()

    def test_find_matching_jobs_for_user_success(self):
        """Test successful job matching when user profile has embedding."""
        user_profile_id = uuid.uuid4()
        mock_embedding = [0.1] * 1536
        mock_profile = MockUserProfile(
            id=user_profile_id, profile_embedding=mock_embedding
        )
        self.MockUserProfileModel.objects.get.return_value = mock_profile

        mock_job_doc1_id = uuid.uuid4()
        mock_job_doc2_id = uuid.uuid4()
        mock_vdb_results = [
            {
                "source_id": str(mock_job_doc1_id),
                "similarity_score": 0.9,
                "text_content": "job1 desc",
                "source_type": "job_listing",
            },
            {
                "source_id": str(mock_job_doc2_id),
                "similarity_score": 0.8,
                "text_content": "job2 desc",
                "source_type": "job_listing",
            },
        ]
        self.job_match_service.vector_db_service.search_similar_documents.return_value = (
            mock_vdb_results
        )

        mock_job1 = MockJob(id=mock_job_doc1_id, title="Job 1")
        mock_job2 = MockJob(id=mock_job_doc2_id, title="Job 2")
        self.MockJobModel.objects.filter.return_value = [mock_job1, mock_job2]

        results = self.job_match_service.find_matching_jobs_for_user(user_profile_id)

        self.MockUserProfileModel.objects.get.assert_called_once_with(
            id=user_profile_id
        )
        self.job_match_service.vector_db_service.search_similar_documents.assert_called_once_with(
            query_embedding=mock_embedding,
            top_n=10,  # Default top_n
            filter_criteria={"source_type": "job_listing"},
        )
        self.MockJobModel.objects.filter.assert_called_once_with(
            id__in=[str(mock_job_doc1_id), str(mock_job_doc2_id)], status="active"
        )

        self.assertEqual(len(results), 2)
        self.assertEqual(
            results[0]["job"], mock_job1
        )  # Assuming order is preserved or re-sorted
        self.assertEqual(results[0]["score"], 0.9)
        self.assertEqual(results[1]["job"], mock_job2)
        self.assertEqual(results[1]["score"], 0.8)

    def test_find_matching_jobs_for_user_embedding_override(self):
        user_profile_id = uuid.uuid4()
        override_embedding = [0.25] * 1536
        self.job_match_service.vector_db_service.search_similar_documents.return_value = (
            []
        )  # No need to check further

        self.job_match_service.find_matching_jobs_for_user(
            user_profile_id, user_profile_embedding_override=override_embedding
        )

        self.MockUserProfileModel.objects.get.assert_not_called()  # Should not fetch profile if embedding is overridden
        self.job_match_service.vector_db_service.search_similar_documents.assert_called_once_with(
            query_embedding=override_embedding,
            top_n=10,
            filter_criteria={"source_type": "job_listing"},
        )

    def test_find_matching_jobs_for_user_no_profile_embedding_uses_skills(self):
        user_profile_id = uuid.uuid4()
        skills_embedding = [0.2] * 1536
        mock_profile = MockUserProfile(
            id=user_profile_id,
            profile_embedding=None,
            skills_embedding=skills_embedding,
        )
        self.MockUserProfileModel.objects.get.return_value = mock_profile
        self.job_match_service.vector_db_service.search_similar_documents.return_value = (
            []
        )

        self.job_match_service.find_matching_jobs_for_user(user_profile_id)
        self.job_match_service.vector_db_service.search_similar_documents.assert_called_once_with(
            query_embedding=skills_embedding,
            top_n=10,
            filter_criteria={"source_type": "job_listing"},
        )

    def test_find_matching_jobs_for_user_no_embeddings_at_all(self):
        user_profile_id = uuid.uuid4()
        mock_profile = MockUserProfile(
            id=user_profile_id, profile_embedding=None, skills_embedding=None
        )
        self.MockUserProfileModel.objects.get.return_value = mock_profile

        results = self.job_match_service.find_matching_jobs_for_user(user_profile_id)
        self.assertEqual(results, [])
        self.job_match_service.vector_db_service.search_similar_documents.assert_not_called()

    def test_find_matching_jobs_for_user_profile_not_found(self):
        user_profile_id = uuid.uuid4()
        self.MockUserProfileModel.objects.get.side_effect = (
            MockUserProfile.DoesNotExist
        )  # Mock DoesNotExist if it's custom or Django's

        results = self.job_match_service.find_matching_jobs_for_user(user_profile_id)
        self.assertEqual(results, [])
        self.job_match_service.vector_db_service.search_similar_documents.assert_not_called()

    def test_find_matching_jobs_no_vdb_results(self):
        user_profile_id = uuid.uuid4()
        mock_embedding = [0.1] * 1536
        mock_profile = MockUserProfile(
            id=user_profile_id, profile_embedding=mock_embedding
        )
        self.MockUserProfileModel.objects.get.return_value = mock_profile
        self.job_match_service.vector_db_service.search_similar_documents.return_value = (
            []
        )  # No docs found

        results = self.job_match_service.find_matching_jobs_for_user(user_profile_id)
        self.assertEqual(results, [])
        self.MockJobModel.objects.filter.assert_not_called()

    def test_find_matching_jobs_vdb_results_no_source_ids(self):
        user_profile_id = uuid.uuid4()
        mock_embedding = [0.1] * 1536
        mock_profile = MockUserProfile(
            id=user_profile_id, profile_embedding=mock_embedding
        )
        self.MockUserProfileModel.objects.get.return_value = mock_profile

        # VDB returns docs but one is missing source_id
        mock_vdb_results = [{"similarity_score": 0.7}]
        self.job_match_service.vector_db_service.search_similar_documents.return_value = (
            mock_vdb_results
        )

        results = self.job_match_service.find_matching_jobs_for_user(user_profile_id)
        self.assertEqual(results, [])
        self.MockJobModel.objects.filter.assert_not_called()

    def test_score_job_for_user_success(self):
        """Test direct scoring when both user and job have embeddings."""
        user_profile_id = uuid.uuid4()
        job_id = uuid.uuid4()
        user_emb = [0.1, 0.2, 0.3]  # Simplified for test
        job_emb = [0.4, 0.5, 0.6]

        mock_profile = MockUserProfile(id=user_profile_id, profile_embedding=user_emb)
        self.MockUserProfileModel.objects.get.return_value = mock_profile
        mock_job = MockJob(id=job_id, combined_embedding=job_emb)
        self.MockJobModel.objects.get.return_value = mock_job

        # Mock the helper directly for this unit test
        with patch.object(
            self.job_match_service, "_calculate_cosine_similarity", return_value=0.85
        ) as mock_calc:
            score = self.job_match_service.score_job_for_user(user_profile_id, job_id)

        mock_calc.assert_called_once_with(user_emb, job_emb)
        expected_scaled_score = round((0.85 + 1) / 2, 4)  # (raw_score + 1) / 2
        self.assertAlmostEqual(score, expected_scaled_score)

    def test_score_job_for_user_embedding_overrides(self):
        user_profile_id = uuid.uuid4()
        job_id = uuid.uuid4()
        user_override_emb = [0.11] * 1536
        job_override_emb = [0.22] * 1536

        with patch.object(
            self.job_match_service, "_calculate_cosine_similarity", return_value=0.7
        ) as mock_calc:
            score = self.job_match_service.score_job_for_user(
                user_profile_id,
                job_id,
                user_profile_embedding_override=user_override_emb,
                job_embedding_override=job_override_emb,
            )

        self.MockUserProfileModel.objects.get.assert_not_called()
        self.MockJobModel.objects.get.assert_not_called()
        mock_calc.assert_called_once_with(user_override_emb, job_override_emb)
        expected_scaled_score = round((0.7 + 1) / 2, 4)
        self.assertAlmostEqual(score, expected_scaled_score)

    def test_score_job_for_user_missing_user_embedding(self):
        user_profile_id = uuid.uuid4()
        job_id = uuid.uuid4()
        mock_profile = MockUserProfile(
            id=user_profile_id, profile_embedding=None, skills_embedding=None
        )
        self.MockUserProfileModel.objects.get.return_value = mock_profile
        mock_job = MockJob(
            id=job_id, combined_embedding=[0.1] * 1536
        )  # Job has embedding
        self.MockJobModel.objects.get.return_value = mock_job

        score = self.job_match_service.score_job_for_user(user_profile_id, job_id)
        self.assertIsNone(score)

    def test_score_job_for_user_missing_job_embedding(self):
        user_profile_id = uuid.uuid4()
        job_id = uuid.uuid4()
        mock_profile = MockUserProfile(
            id=user_profile_id, profile_embedding=[0.1] * 1536
        )
        self.MockUserProfileModel.objects.get.return_value = mock_profile
        mock_job = MockJob(
            id=job_id, combined_embedding=None, job_embedding=None
        )  # Job has no embedding
        self.MockJobModel.objects.get.return_value = mock_job

        score = self.job_match_service.score_job_for_user(user_profile_id, job_id)
        self.assertIsNone(score)

    def test_calculate_cosine_similarity_valid_normalized(self):
        # Assumes normalized vectors where dot product is cosine similarity
        vec_a = [0.6, 0.8]  # Magnitude 1 (0.36 + 0.64 = 1)
        vec_b = [0.8, 0.6]  # Magnitude 1
        # Dot product: (0.6*0.8) + (0.8*0.6) = 0.48 + 0.48 = 0.96
        expected_similarity = 0.96
        similarity = self.job_match_service._calculate_cosine_similarity(vec_a, vec_b)
        self.assertAlmostEqual(similarity, expected_similarity, places=7)

    def test_calculate_cosine_similarity_identical_normalized(self):
        vec_a = [0.6, 0.8]
        vec_b = [0.6, 0.8]
        expected_similarity = 1.0  # (0.36 + 0.64)
        similarity = self.job_match_service._calculate_cosine_similarity(vec_a, vec_b)
        self.assertAlmostEqual(similarity, expected_similarity, places=7)

    def test_calculate_cosine_similarity_orthogonal_normalized(self):
        vec_a = [1.0, 0.0]
        vec_b = [0.0, 1.0]
        expected_similarity = 0.0
        similarity = self.job_match_service._calculate_cosine_similarity(vec_a, vec_b)
        self.assertAlmostEqual(similarity, expected_similarity, places=7)

    def test_calculate_cosine_similarity_opposite_normalized(self):
        vec_a = [0.6, 0.8]
        vec_b = [-0.6, -0.8]
        expected_similarity = -1.0
        similarity = self.job_match_service._calculate_cosine_similarity(vec_a, vec_b)
        self.assertAlmostEqual(similarity, expected_similarity, places=7)

    def test_calculate_cosine_similarity_invalid_input(self):
        self.assertIsNone(
            self.job_match_service._calculate_cosine_similarity(None, [1.0])
        )
        self.assertIsNone(
            self.job_match_service._calculate_cosine_similarity([1.0], None)
        )
        self.assertIsNone(self.job_match_service._calculate_cosine_similarity([], []))
        self.assertIsNone(
            self.job_match_service._calculate_cosine_similarity([1.0, 2.0], [1.0])
        )


if __name__ == "__main__":
    unittest.main()
