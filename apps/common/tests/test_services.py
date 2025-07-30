import unittest
from typing import Any, Dict, List, Optional
from unittest.mock import ANY
from unittest.mock import MagicMock
from unittest.mock import MagicMock as SkyvernMagicMock
from unittest.mock import call
from unittest.mock import call as skyvern_call
from unittest.mock import patch
from unittest.mock import patch as skyvern_patch

import requests

# Assuming VectorDBService is in apps.common.services
# from apps.common.services import VectorDBService
# Assuming VectorDocument model is in apps.common.models
# from apps.common.models import VectorDocument

# Mocking pgvector.django distance functions if they are imported in the service
# We'll patch them where they are used.

# Define a Mock for the VectorDocument model and its manager
class MockVectorDocument:
    objects = MagicMock()

    def __init__(self, text_content="", embedding=None, source_type="", source_id=None, metadata=None, **kwargs):
        self.id = kwargs.get('id', None)
        self.text_content = text_content
        self.embedding = embedding or []
        self.source_type = source_type
        self.source_id = source_id
        self.metadata = metadata or {}
        self.distance = None # For annotated distance in search results

    def save(self, *args, **kwargs):
        pass # Mock save

    def __str__(self):
        return f"MockVectorDocument({self.source_type}:{self.source_id})"


class TestVectorDBService(unittest.TestCase):

    def setUp(self):
        # Patch the VectorDocument model where it's imported by the service
        self.patcher_model = patch('apps.common.services.VectorDocument', new_callable=lambda: MockVectorDocument)
        self.MockModelClass = self.patcher_model.start()

        # Reset mocks for each test to ensure clean state
        self.MockModelClass.objects.reset_mock()
        self.MockModelClass.objects.update_or_create = MagicMock()
        self.MockModelClass.objects.create = MagicMock()
        self.MockModelClass.objects.filter = MagicMock()
        self.MockModelClass.objects.all = MagicMock()

        from apps.common.services import \
            VectorDBService  # Import service after model is patched
        self.service = VectorDBService()
        self.service.document_model = self.MockModelClass # Explicitly set the mocked model

    def tearDown(self):
        self.patcher_model.stop()

    def test_add_documents_success_with_source_id_update_or_create(self):
        """Test adding documents successfully using update_or_create."""
        mock_instance = MockVectorDocument()
        self.MockModelClass.objects.update_or_create.return_value = (mock_instance, True) # (obj, created)

        texts = ["text1", "text2"]
        embeddings = [[0.1]*1536, [0.2]*1536]
        source_types = ["typeA", "typeA"]
        source_ids = ["id1", "id2"]
        metadatas = [{"key": "val1"}, {"key": "val2"}]

        result = self.service.add_documents(texts, embeddings, source_types, source_ids, metadatas)
        self.assertTrue(result)
        self.assertEqual(self.MockModelClass.objects.update_or_create.call_count, 2)

        expected_calls = [
            call(
                source_type="typeA", source_id="id1",
                defaults={'text_content': 'text1', 'embedding': [0.1]*1536, 'metadata': {'key': 'val1'}}
            ),
            call(
                source_type="typeA", source_id="id2",
                defaults={'text_content': 'text2', 'embedding': [0.2]*1536, 'metadata': {'key': 'val2'}}
            )
        ]
        self.MockModelClass.objects.update_or_create.assert_has_calls(expected_calls, any_order=False)
        self.MockModelClass.objects.create.assert_not_called()


    def test_add_documents_success_without_source_id_create(self):
        """Test adding documents where source_id is None, using create."""
        self.MockModelClass.objects.create.return_value = MockVectorDocument()

        texts = ["text_no_id_1"]
        embeddings = [[0.3]*1536]
        source_types = ["typeB"]
        source_ids = [None] # Explicitly None
        metadatas = [{"key": "val_no_id"}]

        result = self.service.add_documents(texts, embeddings, source_types, source_ids, metadatas)
        self.assertTrue(result)
        self.MockModelClass.objects.create.assert_called_once_with(
            text_content="text_no_id_1",
            embedding=[0.3]*1536,
            source_type="typeB",
            source_id=None,
            metadata={"key": "val_no_id"}
        )
        self.MockModelClass.objects.update_or_create.assert_not_called()

    def test_add_documents_mixed_source_ids(self):
        """Test adding documents with a mix of source_id presence."""
        self.MockModelClass.objects.update_or_create.return_value = (MockVectorDocument(), True)
        self.MockModelClass.objects.create.return_value = MockVectorDocument()

        texts = ["text_with_id", "text_no_id"]
        embeddings = [[0.1]*1536, [0.2]*1536]
        source_types = ["typeC", "typeC"]
        source_ids = ["id_c1", None]
        metadatas = [{"k": "v_id"}, {"k": "v_no_id"}]

        result = self.service.add_documents(texts, embeddings, source_types, source_ids, metadatas)
        self.assertTrue(result)
        self.MockModelClass.objects.update_or_create.assert_called_once_with(
            source_type="typeC", source_id="id_c1",
            defaults={'text_content': 'text_with_id', 'embedding': [0.1]*1536, 'metadata': {'k': 'v_id'}}
        )
        self.MockModelClass.objects.create.assert_called_once_with(
            text_content="text_no_id", embedding=[0.2]*1536, source_type="typeC", source_id=None, metadata={'k': 'v_no_id'}
        )


    def test_add_documents_input_mismatch_lengths(self):
        texts = ["text1"]
        embeddings = [[0.1]*1536, [0.2]*1536] # Mismatch
        source_types = ["typeA"]
        result = self.service.add_documents(texts, embeddings, source_types)
        self.assertFalse(result)
        self.MockModelClass.objects.update_or_create.assert_not_called()
        self.MockModelClass.objects.create.assert_not_called()

    def test_add_documents_db_error(self):
        self.MockModelClass.objects.update_or_create.side_effect = Exception("DB error on update_or_create")
        texts = ["text1"]
        embeddings = [[0.1]*1536]
        source_types = ["typeA"]
        source_ids = ["id1"]
        result = self.service.add_documents(texts, embeddings, source_types, source_ids)
        self.assertFalse(result) # Should be false as all operations failed

    @patch('apps.common.services.L2Distance') # Patch where L2Distance is imported/used by the service
    def test_search_similar_documents_success(self, mock_l2distance_class):
        mock_query_embedding = [0.5]*1536

        mock_qs = MagicMock()
        self.MockModelClass.objects.all.return_value = mock_qs
        mock_qs.annotate.return_value = mock_qs
        mock_qs.order_by.return_value = mock_qs

        doc1_instance = MockVectorDocument(id=1, text_content="doc1 text", source_type="typeA", source_id="id1", metadata={"meta": "data1"})
        doc1_instance.distance = 0.2
        doc2_instance = MockVectorDocument(id=2, text_content="doc2 text", source_type="typeA", source_id="id2", metadata={"meta": "data2"})
        doc2_instance.distance = 0.3
        mock_qs.__getitem__.return_value = [doc1_instance, doc2_instance]

        # Configure the mock L2Distance class instance if it's instantiated in the method,
        # or its return value if it's used directly as a function in `annotate`.
        # Assuming L2Distance is used like L2Distance('field', vector)
        mock_l2distance_instance = MagicMock()
        mock_l2distance_class.return_value = mock_l2distance_instance

        results = self.service.search_similar_documents(mock_query_embedding, top_n=2)

        self.MockModelClass.objects.all.assert_called_once()
        mock_l2distance_class.assert_called_once_with('embedding', [float(v) for v in mock_query_embedding])
        mock_qs.annotate.assert_called_once_with(distance=mock_l2distance_instance)
        mock_qs.order_by.assert_called_once_with('distance')
        mock_qs.__getitem__.assert_called_once_with(slice(None, 2, None))

        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]['text_content'], "doc1 text")
        self.assertIn('similarity_score', results[0])
        expected_score_doc1 = round(1 - (0.2**2 / 2), 4)
        self.assertAlmostEqual(results[0]['similarity_score'], expected_score_doc1, places=4)

    @patch('apps.common.services.L2Distance')
    def test_search_similar_documents_score_clamping(self, mock_l2distance_class):
        """Test similarity score clamping for extreme L2 distances."""
        mock_query_embedding = [0.5]*1536
        mock_qs = MagicMock()
        self.MockModelClass.objects.all.return_value = mock_qs
        mock_qs.annotate.return_value = mock_qs
        mock_qs.order_by.return_value = mock_qs

        # Test case 1: Perfect match (distance 0)
        doc_perfect = MockVectorDocument(id=1, text_content="perfect match")
        doc_perfect.distance = 0.0
        # Test case 2: Opposite (distance 2 for normalized vectors)
        doc_opposite = MockVectorDocument(id=2, text_content="opposite match")
        doc_opposite.distance = 2.0
        # Test case 3: Distance slightly > 2 (e.g. due to float issues, should still clamp)
        doc_far = MockVectorDocument(id=3, text_content="far match")
        doc_far.distance = 2.1

        mock_qs.__getitem__.return_value = [doc_perfect, doc_opposite, doc_far]
        mock_l2distance_instance = MagicMock()
        mock_l2distance_class.return_value = mock_l2distance_instance

        results = self.service.search_similar_documents(mock_query_embedding, top_n=3)

        self.assertEqual(len(results), 3)
        # Score for L2 distance 0.0: 1 - (0/2) = 1.0. Scaled: (1+1)/2 = 1.0 (if using raw cosine)
        # Current formula: cosine_similarity = 1 - (L2Distance^2 / 2)
        # For distance 0: score = 1 - (0/2) = 1.0
        self.assertAlmostEqual(results[0]['similarity_score'], 1.0, places=4)

        # Score for L2 distance 2.0: 1 - (4/2) = -1.0. (This is raw cosine)
        # The service's score_0_to_1 = (similarity_score + 1) / 2 in score_job_for_user
        # But VectorDBService search_similar_documents uses:
        # cosine_similarity = 1 - (l2_distance_squared / 2)
        # similarity_score = max(0.0, min(1.0, cosine_similarity)) <--- THIS IS THE KEY
        # So, for distance 2.0, l2_distance_squared = 4. cosine_similarity = 1 - (4/2) = -1.
        # similarity_score = max(0.0, min(1.0, -1.0)) = 0.0
        self.assertAlmostEqual(results[1]['similarity_score'], 0.0, places=4)

        # Score for L2 distance 2.1: 1 - (2.1^2 / 2) = 1 - (4.41/2) = 1 - 2.205 = -1.205
        # similarity_score = max(0.0, min(1.0, -1.205)) = 0.0
        self.assertAlmostEqual(results[2]['similarity_score'], 0.0, places=4)


    @patch('apps.common.services.L2Distance')
    def test_search_similar_documents_with_filters(self, mock_l2distance_class):
        mock_query_embedding = [0.5]*1536
        mock_qs_all = MagicMock()
        mock_qs_filtered = MagicMock()
        self.MockModelClass.objects.all.return_value = mock_qs_all
        mock_qs_all.filter.return_value = mock_qs_filtered # filter returns a new queryset
        mock_qs_filtered.annotate.return_value = mock_qs_filtered
        mock_qs_filtered.order_by.return_value = mock_qs_filtered
        mock_qs_filtered.__getitem__.return_value = []

        filter_criteria = {'source_type': 'job_listing', 'metadata__company__icontains': 'TechCorp'}
        self.service.search_similar_documents(mock_query_embedding, top_n=3, filter_criteria=filter_criteria)

        self.MockModelClass.objects.all.assert_called_once()
        mock_qs_all.filter.assert_called_once_with(source_type='job_listing', metadata__company__icontains='TechCorp')

    def test_search_similar_documents_empty_query(self):
        results = self.service.search_similar_documents([])
        self.assertEqual(results, [])
        self.MockModelClass.objects.all.assert_not_called()

    def test_delete_documents_success(self):
        mock_qs = MagicMock()
        self.MockModelClass.objects.filter.return_value = mock_qs
        mock_qs.delete.return_value = (1, {'apps.common.VectorDocument': 1})

        result = self.service.delete_documents(source_type="typeA", source_id="id1")
        self.assertTrue(result)
        self.MockModelClass.objects.filter.assert_called_once_with(source_type="typeA", source_id="id1")
        mock_qs.delete.assert_called_once()

    def test_delete_documents_db_error(self):
        mock_qs = MagicMock()
        self.MockModelClass.objects.filter.return_value = mock_qs
        mock_qs.delete.side_effect = Exception("DB delete error")

        result = self.service.delete_documents(source_type="typeA", source_id="id1")
        self.assertFalse(result)

    def test_delete_documents_invalid_input(self):
        result_no_type = self.service.delete_documents(source_type="", source_id="id1")
        self.assertFalse(result_no_type)
        result_no_id = self.service.delete_documents(source_type="typeA", source_id="")
        self.assertFalse(result_no_id)

if __name__ == '__main__':
    # This allows running the tests directly if the file structure is set up
    # and Django settings are minimally configured for model imports,
    # or if all Django dependencies are mocked out.
    # For full Django integration, use `python manage.py test apps.common`
    # unittest.main() # Comment out when running as part of Django test suite


# Placeholder for Skyvern tests if they are to be in this file.
# It's generally better to have separate test files per service if they grow large.
# For now, adding here as per plan "add to existing for now".

from unittest.mock import MagicMock as SkyvernMagicMock
from unittest.mock import call as skyvern_call
from unittest.mock import patch as skyvern_patch

# Assuming SkyvernAPIClient is in apps.integrations.services.skyvern
# from apps.integrations.services.skyvern import SkyvernAPIClient

class MockSkyvernResponse:
    def __init__(self, status_code, json_data=None, text_data=""):
        self.status_code = status_code
        self.json_data = json_data
        self.text = text_data
        self.ok = 200 <= status_code < 300

    def json(self):
        if self.json_data is not None:
            return self.json_data
        raise requests.exceptions.JSONDecodeError("No JSON data", "doc", 0)

    def raise_for_status(self):
        if not self.ok:
            # Simplified: Real requests.HTTPError would have request and response attributes
            raise requests.exceptions.HTTPError(f"HTTP Error {self.status_code}", response=self)


class TestSkyvernAPIClient(unittest.TestCase):
    def setUp(self):
        # Patch settings for SKYVERN_API_KEY
        self.settings_patcher = skyvern_patch('apps.integrations.services.skyvern.settings')
        self.mock_settings = self.settings_patcher.start()
        self.mock_settings.SKYVERN_API_KEY = "test_skyvern_key"
        # Mock for circuit breaker state changes metric if needed by Skyvern client
        self.skyvern_cb_metric_patcher = skyvern_patch('apps.integrations.services.skyvern.SKYVERN_CIRCUIT_BREAKER_STATE_CHANGES_TOTAL', SkyvernMagicMock())
        self.mock_skyvern_cb_metric = self.skyvern_cb_metric_patcher.start()

        # Patch requests.Session globally for where SkyvernAPIClient uses it
        self.session_patcher = skyvern_patch('requests.Session', autospec=True)
        self.MockSessionClass = self.session_patcher.start()
        self.mock_session_instance = self.MockSessionClass.return_value # This is what client.session will be

        # Mock Prometheus metrics used by SkyvernAPIClient
        self.skyvern_api_calls_patcher = skyvern_patch('apps.integrations.services.skyvern.SKYVERN_API_CALLS_TOTAL')
        self.mock_skyvern_api_calls = self.skyvern_api_calls_patcher.start()

        self.skyvern_api_duration_patcher = skyvern_patch('apps.integrations.services.skyvern.SKYVERN_API_CALL_DURATION_SECONDS')
        self.mock_skyvern_api_duration = self.skyvern_api_duration_patcher.start()

        self.skyvern_api_errors_patcher = skyvern_patch('apps.integrations.services.skyvern.SKYVERN_API_ERRORS_TOTAL')
        self.mock_skyvern_api_errors = self.skyvern_api_errors_patcher.start()


        from apps.integrations.services.skyvern import \
            SkyvernAPIClient  # Import here after patching settings & requests
        self.client = SkyvernAPIClient()
        # Ensure the client's session is the mocked one
        self.client.session = self.mock_session_instance


    def tearDown(self):
        self.settings_patcher.stop()
        self.session_patcher.stop()
        self.skyvern_cb_metric_patcher.stop()
        self.skyvern_api_calls_patcher.stop()
        self.skyvern_api_duration_patcher.stop()
        self.skyvern_api_errors_patcher.stop()

    def test_init_with_api_key(self):
        self.assertEqual(self.client.api_key, "test_skyvern_key")
        self.assertIsNotNone(self.client.session)

    @skyvern_patch('apps.integrations.services.skyvern.logger') # Patch logger inside the service
    def test_init_without_api_key(self, mock_logger):
        self.mock_settings.SKYVERN_API_KEY = None
        from apps.integrations.services.skyvern import SkyvernAPIClient
        client_no_key = SkyvernAPIClient() # Re-init after changing mock_settings
        self.assertIsNone(client_no_key.api_key)
        mock_logger.warning.assert_called_with("Skyvern API key not configured. SkyvernAPIClient will not be able to make calls.")

    def test_get_headers_success(self):
        headers = self.client._get_headers()
        self.assertEqual(headers["Authorization"], f"Bearer test_skyvern_key")
        self.assertEqual(headers["Content-Type"], "application/json")

    def test_get_headers_no_api_key_raises_error(self):
        self.client.api_key = None # Simulate no API key
        with self.assertRaises(ValueError) as context:
            self.client._get_headers()
        self.assertIn("Skyvern API key is not configured", str(context.exception))

    def test_run_task_success(self):
        mock_response_data = {"task_id": "sky_task_123", "status": "PENDING"}
        self.mock_session_instance.post.return_value = MockSkyvernResponse(200, json_data=mock_response_data)

        prompt = "Apply for this job."
        inputs = {"url": "http://example.com/job/1"}
        webhook_url = "http://my.webhook/skyvern"

        response = self.client.run_task(prompt, inputs, webhook_url=webhook_url)

        self.assertEqual(response, mock_response_data)
        expected_url = f"{self.client.BASE_URL}/run-task"
        expected_payload = {
            "prompt": prompt,
            "inputs": inputs,
            "webhook_url": webhook_url
        }
        self.mock_session_instance.post.assert_called_once_with(
            expected_url,
            headers=self.client._get_headers(),
            json=expected_payload,
            params=None, # Assuming params is None for run_task
            timeout=60
        )
        self.mock_skyvern_api_calls.labels(endpoint='/run-task', status_code='200').inc.assert_called_once()
        self.mock_skyvern_api_duration.labels(endpoint='/run-task').observe.assert_called_once()

    def test_run_task_api_http_error(self):
        self.mock_session_instance.post.return_value = MockSkyvernResponse(500, text_data="Server Error")

        response = self.client.run_task("prompt", {})
        self.assertIsNone(response) # _make_request returns None on HTTPError
        self.mock_skyvern_api_errors.labels(endpoint='/run-task', error_type='HTTPError').inc.assert_called_once()

    def test_get_task_status_success(self):
        task_id = "sky_task_123"
        mock_response_data = {"task_id": task_id, "status": "COMPLETED"}
        self.mock_session_instance.get.return_value = MockSkyvernResponse(200, json_data=mock_response_data)

        response = self.client.get_task_status(task_id)
        self.assertEqual(response, mock_response_data)
        expected_url = f"{self.client.BASE_URL}/task-status/{task_id}"
        self.mock_session_instance.get.assert_called_once_with(
            expected_url,
            headers=self.client._get_headers(),
            params=None, # Assuming no extra params for get_task_status
            timeout=30
        )
        self.mock_skyvern_api_calls.labels(endpoint=f'/task-status/{task_id}', status_code='200').inc.assert_called_once()

    def test_get_task_results_success(self):
        task_id = "sky_task_123"
        mock_response_data = {"task_id": task_id, "status": "COMPLETED", "data": {"applied": True}}
        self.mock_session_instance.get.return_value = MockSkyvernResponse(200, json_data=mock_response_data)

        response = self.client.get_task_results(task_id)
        self.assertEqual(response, mock_response_data)
        expected_url = f"{self.client.BASE_URL}/task-results/{task_id}"
        self.mock_session_instance.get.assert_called_once_with(
            expected_url,
            headers=self.client._get_headers(),
            params=None,
            timeout=30
        )

    # Conceptual test for circuit breaker - hard to test state changes without exposing CB state or more complex mocking
    @skyvern_patch('time.sleep') # To avoid actual sleep in tests
    def test_make_request_circuit_breaker_opens_and_blocks(self, mock_sleep):
        self.mock_session_instance.post.side_effect = requests.exceptions.ConnectionError("Simulated connection error")

        # Trigger failures to open circuit breaker
        for _ in range(self.client.CB_MAX_FAILURES):
            self.client.run_task("prompt", {}) # This will call _make_request

        # Circuit should be open now
        with self.assertRaises(requests.exceptions.ConnectionError) as context:
            self.client.run_task("prompt", {})
        self.assertIn("Skyvern Circuit Breaker is OPEN", str(context.exception))

        # Check metric for CB state change to OPEN
        self.mock_skyvern_cb_metric.labels(new_state='OPEN').inc.assert_called()


    @skyvern_patch('time.sleep') # To avoid actual sleep from backoff
    @skyvern_patch('time.monotonic')
    def test_make_request_retries_on_specific_http_errors(self, mock_monotonic, mock_sleep):
        # Configure monotonic for circuit breaker if it interacts
        mock_monotonic.side_effect = [1, 2, 3, 4, 5, 6] # Ensure time progresses for CB if needed

        # Simulate a 500 error twice, then a success
        self.mock_session_instance.post.side_effect = [
            MockSkyvernResponse(500, text_data="Internal Server Error"),
            MockSkyvernResponse(500, text_data="Internal Server Error"),
            MockSkyvernResponse(200, json_data={"task_id": "retried_task"})
        ]

        response = self.client.run_task("retry_prompt", {}) # Calls _make_request with POST

        self.assertIsNotNone(response)
        self.assertEqual(response["task_id"], "retried_task")
        self.assertEqual(self.mock_session_instance.post.call_count, 3) # Original call + 2 retries
        # Check that appropriate error metrics were NOT incremented for final success,
        # but API calls metric reflects the final success.
        self.mock_skyvern_api_calls.labels(endpoint='/run-task', status_code='200').inc.assert_called_once()
        self.mock_skyvern_api_errors.labels(endpoint='/run-task', error_type='HTTPError').inc.assert_not_called() # Because it eventually succeeded

    @skyvern_patch('time.sleep')
    @skyvern_patch('time.monotonic')
    def test_circuit_breaker_half_open_to_closed(self, mock_monotonic, mock_sleep):
        # --- 1. Open the Circuit Breaker ---
        self.mock_session_instance.post.side_effect = requests.exceptions.ConnectionError("Simulated connection error")
        # Configure monotonic for initial failures
        time_sequence = [i for i in range(1, self.client.CB_MAX_FAILURES + 2)]
        mock_monotonic.side_effect = time_sequence

        for _ in range(self.client.CB_MAX_FAILURES):
            self.client.run_task("prompt_to_open_cb", {})

        self.assertEqual(self.client._cb_state, "OPEN") # Assuming we can inspect state for test
        self.mock_skyvern_cb_metric.labels(new_state='OPEN').inc.assert_called()
        last_failure_time_for_open = self.client.CB_MAX_FAILURES # From mock_monotonic sequence

        # --- 2. Wait for Reset Timeout & Transition to HALF_OPEN ---
        # Simulate time passing beyond the reset timeout
        time_sequence_for_half_open = [
            last_failure_time_for_open + self.client.CB_RESET_TIMEOUT_SECONDS + 1, # For check that allows HALF_OPEN
        ]
        # Add times for successful calls in HALF_OPEN state
        time_sequence_for_half_open.extend([time_sequence_for_half_open[-1] + i for i in range(1, self.client.CB_HALF_OPEN_MAX_REQUESTS + 2)])
        mock_monotonic.side_effect = time_sequence_for_half_open

        # This call should transition state to HALF_OPEN if enough time has passed
        # and then succeed. We need to mock the actual API call to succeed now.
        successful_response_data = {"task_id": "half_open_success"}

        # Setup session mock for successful calls during HALF_OPEN
        # The first call after timeout check, then CB_HALF_OPEN_MAX_REQUESTS successful calls
        self.mock_session_instance.post.side_effect = [
            MockSkyvernResponse(200, json_data=successful_response_data)
            for _ in range(self.client.CB_HALF_OPEN_MAX_REQUESTS +1) # One to open, others to close
        ]

        # First call attempts to move to HALF_OPEN and succeeds
        response = self.client.run_task("prompt_half_open_1", {})
        self.assertEqual(response, successful_response_data)
        self.assertEqual(self.client._cb_state, "HALF_OPEN") # Check internal state
        self.mock_skyvern_cb_metric.labels(new_state='HALF_OPEN').inc.assert_called_once()

        # Subsequent successful calls to close the circuit
        for i in range(self.client.CB_HALF_OPEN_MAX_REQUESTS -1): # Already made one successful call
             response = self.client.run_task(f"prompt_half_open_succ_{i+2}", {})
             self.assertEqual(response, successful_response_data)
             if i < self.client.CB_HALF_OPEN_MAX_REQUESTS - 2: # Before the last one that closes it
                 self.assertEqual(self.client._cb_state, "HALF_OPEN")

        self.assertEqual(self.client._cb_state, "CLOSED") # Should be closed now
        self.mock_skyvern_cb_metric.labels(new_state='CLOSED').inc.assert_called_once()
        self.assertEqual(self.client._cb_failures, 0)


if __name__ == '__main__':
    # For full Django integration, use `python manage.py test apps.common`
    unittest.main()
