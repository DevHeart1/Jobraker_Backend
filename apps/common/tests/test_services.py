import unittest
from unittest.mock import patch, MagicMock, call, ANY
from typing import List, Dict, Any, Optional

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

        from apps.common.services import VectorDBService # Import service after model is patched
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
    unittest.main()
