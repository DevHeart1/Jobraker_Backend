"""
Enhanced Vector Storage Service with proper database persistence.
"""

import logging
from typing import Any, Dict, List, Optional, Union

from django.conf import settings
from django.db import connection, transaction
from pgvector.django import CosineDistance, InnerProduct, L2Distance

from .models import VectorDocument

logger = logging.getLogger(__name__)


class VectorStorageService:
    """
    Enhanced service for vector storage and retrieval with proper persistence.
    Handles both development (JSONField) and production (pgvector) environments.
    """

    def __init__(self):
        self.model = VectorDocument
        self.is_production = not settings.DEBUG and hasattr(
            VectorDocument._meta.get_field("embedding"), "dimensions"
        )

    def store_embeddings_batch(
        self,
        documents: List[Dict[str, Any]],
        batch_size: int = 100,
        update_existing: bool = True,
    ) -> Dict[str, int]:
        """
        Store multiple document embeddings in batches for optimal performance.

        Args:
            documents: List of document dictionaries with required fields
            batch_size: Number of documents to process in each batch
            update_existing: Whether to update existing documents

        Returns:
            Dictionary with statistics of the operation
        """
        stats = {"created": 0, "updated": 0, "skipped": 0, "errors": 0}

        try:
            with transaction.atomic():
                for i in range(0, len(documents), batch_size):
                    batch = documents[i : i + batch_size]
                    batch_stats = self._process_batch(batch, update_existing)

                    for key in stats:
                        stats[key] += batch_stats.get(key, 0)

                    logger.info(f"Processed batch {i//batch_size + 1}: {batch_stats}")

            logger.info(f"Batch storage completed: {stats}")
            return stats

        except Exception as e:
            logger.error(f"Error in batch storage: {e}", exc_info=True)
            stats["errors"] = len(documents)
            return stats

    def _process_batch(
        self, batch: List[Dict[str, Any]], update_existing: bool
    ) -> Dict[str, int]:
        """Process a single batch of documents."""
        stats = {"created": 0, "updated": 0, "skipped": 0, "errors": 0}

        for doc in batch:
            try:
                result = self._store_single_document(doc, update_existing)
                stats[result] += 1
            except Exception as e:
                logger.error(
                    f"Error processing document {doc.get('source_id', 'unknown')}: {e}"
                )
                stats["errors"] += 1

        return stats

    def _store_single_document(self, doc: Dict[str, Any], update_existing: bool) -> str:
        """Store or update a single document."""
        required_fields = ["text_content", "embedding", "source_type", "source_id"]
        if not all(field in doc for field in required_fields):
            raise ValueError(f"Missing required fields. Required: {required_fields}")

        # Check if document exists
        existing = self.model.objects.filter(
            source_type=doc["source_type"], source_id=doc["source_id"]
        ).first()

        if existing:
            if update_existing:
                # Update existing document
                existing.text_content = doc["text_content"]
                existing.embedding = doc["embedding"]
                existing.metadata = doc.get("metadata", {})
                existing.save(
                    update_fields=[
                        "text_content",
                        "embedding",
                        "metadata",
                        "updated_at",
                    ]
                )
                return "updated"
            else:
                return "skipped"
        else:
            # Create new document
            self.model.objects.create(
                text_content=doc["text_content"],
                embedding=doc["embedding"],
                source_type=doc["source_type"],
                source_id=doc["source_id"],
                metadata=doc.get("metadata", {}),
            )
            return "created"

    def search_similar_vectors(
        self,
        query_embedding: List[float],
        top_k: int = 10,
        similarity_threshold: float = 0.7,
        source_types: Optional[List[str]] = None,
        metadata_filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Search for similar vectors with comprehensive filtering.

        Args:
            query_embedding: Query vector to find similar documents
            top_k: Number of top results to return
            similarity_threshold: Minimum similarity score
            source_types: Filter by source types
            metadata_filters: Additional metadata filters

        Returns:
            List of similar documents with similarity scores
        """
        try:
            queryset = self.model.objects.all()

            # Apply source type filters
            if source_types:
                queryset = queryset.filter(source_type__in=source_types)

            # Apply metadata filters
            if metadata_filters:
                for key, value in metadata_filters.items():
                    filter_key = f"metadata__{key}"
                    if isinstance(value, list):
                        queryset = queryset.filter(**{f"{filter_key}__in": value})
                    else:
                        queryset = queryset.filter(**{filter_key: value})

            # Perform similarity search
            if self.is_production:
                # Use pgvector for production
                similar_docs = (
                    queryset.annotate(
                        similarity=1 - CosineDistance("embedding", query_embedding)
                    )
                    .filter(similarity__gte=similarity_threshold)
                    .order_by("-similarity")[:top_k]
                )
            else:
                # Fallback for development - get all and compute similarity in Python
                all_docs = list(queryset)
                scored_docs = []

                for doc in all_docs:
                    similarity = self._compute_cosine_similarity(
                        query_embedding, doc.embedding
                    )
                    if similarity >= similarity_threshold:
                        doc.similarity = similarity
                        scored_docs.append(doc)

                # Sort by similarity and take top_k
                similar_docs = sorted(
                    scored_docs, key=lambda x: x.similarity, reverse=True
                )[:top_k]

            # Format results
            results = []
            for doc in similar_docs:
                results.append(
                    {
                        "id": doc.id,
                        "text_content": doc.text_content,
                        "source_type": doc.source_type,
                        "source_id": doc.source_id,
                        "metadata": doc.metadata,
                        "similarity_score": getattr(doc, "similarity", 0.0),
                        "created_at": doc.created_at,
                    }
                )

            logger.info(
                f"Found {len(results)} similar documents (threshold: {similarity_threshold})"
            )
            return results

        except Exception as e:
            logger.error(f"Error in similarity search: {e}", exc_info=True)
            return []

    def _compute_cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """Compute cosine similarity between two vectors (fallback for development)."""
        try:
            import numpy as np

            # Convert to numpy arrays
            a = np.array(vec1)
            b = np.array(vec2)

            # Compute cosine similarity
            dot_product = np.dot(a, b)
            norms = np.linalg.norm(a) * np.linalg.norm(b)

            if norms == 0:
                return 0.0

            return dot_product / norms

        except Exception as e:
            logger.error(f"Error computing cosine similarity: {e}")
            return 0.0

    def get_storage_stats(self) -> Dict[str, Any]:
        """Get statistics about stored vectors."""
        try:
            stats = {
                "total_documents": self.model.objects.count(),
                "by_source_type": {},
                "storage_size_mb": 0,
                "index_status": "unknown",
            }

            # Count by source type
            source_types = self.model.objects.values_list(
                "source_type", flat=True
            ).distinct()
            for source_type in source_types:
                count = self.model.objects.filter(source_type=source_type).count()
                stats["by_source_type"][source_type] = count

            # Estimate storage size
            if self.is_production:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT pg_size_pretty(pg_total_relation_size('common_vectordocument'))
                    """
                    )
                    size = cursor.fetchone()[0]
                    stats["storage_size"] = size

                    # Check index status
                    cursor.execute(
                        """
                        SELECT indexname, indexdef 
                        FROM pg_indexes 
                        WHERE tablename = 'common_vectordocument' 
                        AND indexname LIKE '%embedding%'
                    """
                    )
                    indexes = cursor.fetchall()
                    stats["vector_indexes"] = [idx[0] for idx in indexes]

            return stats

        except Exception as e:
            logger.error(f"Error getting storage stats: {e}")
            return {"error": str(e)}

    def cleanup_old_vectors(
        self, days_old: int = 30, source_types: Optional[List[str]] = None
    ) -> int:
        """
        Clean up old vector documents to manage storage.

        Args:
            days_old: Delete documents older than this many days
            source_types: Only clean up specific source types

        Returns:
            Number of documents deleted
        """
        try:
            from datetime import timedelta

            from django.utils import timezone

            cutoff_date = timezone.now() - timedelta(days=days_old)
            queryset = self.model.objects.filter(created_at__lt=cutoff_date)

            if source_types:
                queryset = queryset.filter(source_type__in=source_types)

            deleted_count, _ = queryset.delete()
            logger.info(
                f"Cleaned up {deleted_count} old vector documents (older than {days_old} days)"
            )

            return deleted_count

        except Exception as e:
            logger.error(f"Error in cleanup: {e}")
            return 0

    def reindex_vectors(self) -> bool:
        """
        Rebuild vector indexes for optimal performance.
        Only works in production with pgvector.
        """
        if not self.is_production:
            logger.warning("Reindexing only available in production with pgvector")
            return False

        try:
            with connection.cursor() as cursor:
                # Reindex HNSW index
                cursor.execute(
                    "REINDEX INDEX CONCURRENTLY vector_document_embedding_hnsw_idx;"
                )

                # Update statistics
                cursor.execute("ANALYZE common_vectordocument;")

            logger.info("Vector indexes rebuilt successfully")
            return True

        except Exception as e:
            logger.error(f"Error reindexing vectors: {e}")
            return False
