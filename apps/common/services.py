"""
Common Services for the Jobraker Application.
Includes VectorDBService for interacting with pgvector.
"""
import logging
from typing import List, Dict, Optional, Any
# from django.db import connection # For raw SQL if needed with pgvector
# from pgvector.django import L2Distance # Example import for pgvector operations with Django ORM
# Assuming models.py is in the same app 'common'
# from .models import VectorDocument # This will be used once models.py is confirmed

logger = logging.getLogger(__name__)


class VectorDBService:
    """
    Service for interacting with the vector database (pgvector).
    This is a conceptual design; actual implementation would use Django ORM with pgvector
    or raw SQL for pgvector operations.
    """

    def __init__(self):
        # In a real scenario, you might pass a model class or specific configurations.
        # For now, it's self-contained for conceptual logic.
        try:
            from .models import VectorDocument # Assuming models.py is in the same app 'common'
            self.document_model = VectorDocument
        except ImportError:
            logger.error("VectorDBService: Could not import VectorDocument model. Ensure it's defined in apps.common.models.")
            self.document_model = None
        pass

    def add_documents(
        self,
        texts: List[str],
        embeddings: List[List[float]],
        source_types: List[str],
        source_ids: Optional[List[Optional[str]]] = None,
        metadatas: Optional[List[Optional[Dict[str, Any]]]] = None
    ) -> bool:
        """
        Adds documents and their embeddings to the vector database.
        (Conceptual implementation)
        """
        if self.document_model is None:
            logger.error("VectorDBService: VectorDocument model not loaded. Cannot add documents.")
            return False

        if not (len(texts) == len(embeddings) == len(source_types)):
            logger.error("VectorDBService: Mismatch in lengths of texts, embeddings, or source_types.")
            return False

        num_documents = len(texts)
        _source_ids = source_ids if source_ids is not None else [None] * num_documents
        _metadatas = metadatas if metadatas is not None else [{}] * num_documents

        if not (len(_source_ids) == num_documents and len(_metadatas) == num_documents):
            logger.error("VectorDBService: Mismatch in lengths for optional source_ids or metadatas after defaulting.")
            return False

        created_count = 0
        updated_count = 0
        processed_with_error = 0

        for i in range(num_documents):
            current_embedding = [float(val) for val in embeddings[i]] if embeddings[i] is not None else None

            # `source_id` can be None for some source_types.
            # The VectorDocument model has `unique_together = ('source_type', 'source_id')`.
            # If source_id is None, this constraint won't prevent multiple entries with source_id=NULL
            # unless the database treats NULLs as distinct in unique constraints (PostgreSQL does).
            # However, for `update_or_create`, if source_id is None, we need a different strategy
            # or accept that these might be created as new entries if no other unique fields are used for lookup.

            defaults = {
                'text_content': texts[i],
                'embedding': current_embedding,
                'metadata': _metadatas[i]
            }

            try:
                if _source_ids[i] is not None: # Common case: document linked to a specific source object
                    obj, created = self.document_model.objects.update_or_create(
                        source_type=source_types[i],
                        source_id=_source_ids[i],
                        defaults=defaults
                    )
                    if created:
                        created_count += 1
                    else:
                        updated_count += 1
                else:
                    # Case: source_id is None. These are typically generic documents not tied to a specific DB object.
                    # We might create them directly. If text_content should be unique for these,
                    # a custom lookup or a hash of content could be used as a pseudo source_id.
                    # For now, creating directly. This might lead to duplicates if called multiple times with identical content.
                    # A more robust solution for source_id=None might involve checking for existing similar content if desired.
                    self.document_model.objects.create(
                        text_content=texts[i],
                        embedding=current_embedding,
                        source_type=source_types[i],
                        source_id=None,
                        metadata=_metadatas[i]
                    )
                    created_count += 1
            except Exception as e:
                logger.error(f"VectorDBService: Error processing document (type: {source_types[i]}, id: {_source_ids[i]}): {e}")
                processed_with_error += 1

        total_attempted = num_documents
        successful_ops = created_count + updated_count
        logger.info(
            f"VectorDBService: Processed {total_attempted} documents. "
            f"Created: {created_count}, Updated: {updated_count}, Errors: {processed_with_error}."
        )
        # Return True if at least some documents were processed without error,
        # or adjust based on stricter success criteria.
        return successful_ops > 0 or total_attempted == 0


    def search_similar_documents(
        self,
        query_embedding: List[float],
        top_n: int = 5,
        filter_criteria: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Searches for documents in the vector database similar to the query_embedding.

        Args:
            query_embedding: The vector embedding of the query.
            top_n: The number of similar documents to return.
            filter_criteria: Optional dictionary for filtering results
                             (e.g., {'source_type': 'career_article', 'metadata__category': 'interview_tips'}).
                             Supports Django ORM style __contains, __in for metadata JSONField.

        Returns:
            A list of dictionaries, where each dictionary contains the document's
            text_content, source_type, source_id, metadata, and a conceptual similarity_score.
        """
        if self.document_model is None:
            logger.error("VectorDBService: VectorDocument model not loaded. Cannot search documents.")
            return []

        if not query_embedding:
            logger.warning("VectorDBService: Empty query embedding provided for search.")
            return []

        from pgvector.django import L2Distance # CosineDistance, MaxInnerProduct also available

        queryset = self.document_model.objects.all()

        # Apply filters from filter_criteria
        # Example: filter_criteria = {'source_type': 'job_listing', 'metadata__location__icontains': 'new york'}
        if filter_criteria:
            orm_filters = {}
            for key, value in filter_criteria.items():
                # Simple direct field filters (e.g., source_type)
                if not '__' in key and hasattr(self.document_model, key):
                    orm_filters[key] = value
                # Metadata filters (e.g., metadata__some_key__exact='some_value')
                elif key.startswith('metadata__'):
                    orm_filters[key] = value
                # Add more complex filter logic if needed

            if orm_filters:
                try:
                    queryset = queryset.filter(**orm_filters)
                except Exception as e: # Catch field errors, etc.
                    logger.error(f"VectorDBService: Error applying filters {orm_filters}: {e}")
                    # Potentially return empty or raise, depending on desired strictness
                    return []


        # Ensure query_embedding is a list of Python floats
        query_embedding_float = [float(val) for val in query_embedding]

        # Order by similarity using L2Distance (smaller distance is more similar)
        # The `distance` will be available as an annotation on each object.
        # For OpenAI embeddings (normalized), L2 distance and Cosine Similarity are related.
        # Cosine Distance = 2 * (1 - Cosine Similarity). Smaller L2 means higher Cosine Similarity.
        queryset = queryset.annotate(distance=L2Distance('embedding', query_embedding_float)).order_by('distance')

        # Limit to top_n results
        similar_docs_instances = list(queryset[:top_n]) # Evaluate queryset

        results = []
        for doc_instance in similar_docs_instances:
            distance = getattr(doc_instance, 'distance', float('inf'))

            # Convert L2 distance to a similarity score (0 to 1).
            # A common way for normalized vectors: score = 1 - (L2_distance^2 / 2) which is cosine similarity.
            # Or, if L2 distance is small, 1 / (1 + distance) is a simple heuristic.
            # For L2 distance on normalized vectors, max distance is sqrt(2) for orthogonal, 2 for opposite.
            # Let's use a simple inverse relationship for score, higher is better.
            # Max L2 distance for normalized vectors is 2.
            # similarity_score = 1 - (distance / 2) if distance <= 2 else 0.0 # Scale L2 to 0-1 range
            # Or, more directly related to cosine for normalized vectors:
            # Cosine Similarity = 1 - (L2Distance^2 / 2)
            # Ensure distance is not negative if somehow it can be
            l2_distance_squared = distance ** 2
            cosine_similarity = 1 - (l2_distance_squared / 2)
            # Clamp to [0,1] as floating point issues or extreme distances might push it out
            similarity_score = max(0.0, min(1.0, cosine_similarity))


            results.append({
                'text_content': doc_instance.text_content,
                'source_type': doc_instance.source_type,
                'source_id': doc_instance.source_id,
                'metadata': doc_instance.metadata,
                'similarity_score': round(similarity_score, 4) # Round for readability
            })

        logger.info(f"VectorDBService: Found {len(results)} similar documents for query.")
        return results

    def delete_documents(self, source_type: str, source_id: str) -> bool:
        """
        Deletes documents from the vector database based on source_type and source_id.
        """
        if self.document_model is None:
            logger.error("VectorDBService: VectorDocument model not loaded. Cannot delete documents.")
            return False

        if not source_type or not source_id: # Basic validation
            logger.warning("VectorDBService: source_type and source_id must be provided for deletion.")
            return False

        try:
            # Filter for the documents to be deleted
            queryset = self.document_model.objects.filter(source_type=source_type, source_id=source_id)
            count, deleted_types = queryset.delete()

            logger.info(f"VectorDBService: Deleted {count} documents for source_type='{source_type}', source_id='{source_id}'. Detailed deletions: {deleted_types}")
            return True
        except Exception as e:
            logger.error(f"VectorDBService: Error deleting documents for source_type='{source_type}', source_id='{source_id}': {e}")
            return False
