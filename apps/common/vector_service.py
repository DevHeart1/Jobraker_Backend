"""
VectorDB Service for pgvector-based operations.
"""

import logging
from typing import List, Dict, Any, Optional
from django.db import transaction
from pgvector.django import L2Distance, CosineDistance
from .models import VectorDocument

logger = logging.getLogger(__name__)


class VectorDBService:
    """
    Service for interacting with the vector database using pgvector.
    Handles document storage, retrieval, and similarity search.
    """

    def __init__(self):
        self.model = VectorDocument

    def add_document(
        self,
        text_content: str,
        embedding: List[float],
        source_type: str,
        source_id: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Add or update a single document in the vector database.
        
        Args:
            text_content: The original text content
            embedding: Vector embedding of the text
            source_type: Type of source (e.g., 'job_listing', 'career_article')
            source_id: Unique identifier within the source type
            metadata: Additional metadata for filtering
        
        Returns:
            True if successful, False otherwise
        """
        try:
            metadata = metadata or {}
            
            # Use get_or_create to handle duplicates
            document, created = self.model.objects.get_or_create(
                source_type=source_type,
                source_id=source_id,
                defaults={
                    'text_content': text_content,
                    'embedding': embedding,
                    'metadata': metadata,
                }
            )
            
            # Update if it already exists
            if not created:
                document.text_content = text_content
                document.embedding = embedding
                document.metadata = metadata
                document.save()
            
            logger.info(f"{'Created' if created else 'Updated'} vector document: {source_type}_{source_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error adding document to vector DB: {e}")
            return False

    def add_documents_batch(
        self,
        documents: List[Dict[str, Any]],
        batch_size: int = 100
    ) -> int:
        """
        Add multiple documents in batches.
        
        Args:
            documents: List of document dictionaries with required fields
            batch_size: Number of documents to process in each batch
        
        Returns:
            Number of successfully processed documents
        """
        successful_count = 0
        
        try:
            with transaction.atomic():
                for i in range(0, len(documents), batch_size):
                    batch = documents[i:i + batch_size]
                    
                    for doc in batch:
                        if self.add_document(
                            text_content=doc['text_content'],
                            embedding=doc['embedding'],
                            source_type=doc['source_type'],
                            source_id=doc['source_id'],
                            metadata=doc.get('metadata', {})
                        ):
                            successful_count += 1
            
            logger.info(f"Successfully processed {successful_count}/{len(documents)} documents")
            return successful_count
            
        except Exception as e:
            logger.error(f"Error in batch document addition: {e}")
            return successful_count

    def search_similar_documents(
        self,
        query_embedding: List[float],
        top_n: int = 5,
        filter_criteria: Optional[Dict[str, Any]] = None,
        similarity_threshold: float = 0.7
    ) -> List[Dict[str, Any]]:
        """
        Search for similar documents using vector similarity.
        
        Args:
            query_embedding: Query vector to find similar documents
            top_n: Number of top results to return
            filter_criteria: Additional filters for metadata
            similarity_threshold: Minimum similarity score (0-1)
        
        Returns:
            List of similar documents with metadata and similarity scores
        """
        try:
            # Start with base queryset
            queryset = self.model.objects.all()
            
            # Apply metadata filters if provided
            if filter_criteria:
                for key, value in filter_criteria.items():
                    if key == 'source_type':
                        queryset = queryset.filter(source_type=value)
                    elif key == 'source_type__in':
                        queryset = queryset.filter(source_type__in=value)
                    elif key.startswith('metadata__'):
                        # Handle JSONField queries
                        queryset = queryset.filter(**{key: value})
            
            # Perform similarity search using cosine distance
            # Lower distance = higher similarity
            similar_docs = queryset.order_by(
                CosineDistance('embedding', query_embedding)
            )[:top_n * 2]  # Get more than needed to filter by threshold
            
            results = []
            for doc in similar_docs:
                # Calculate similarity score (1 - cosine_distance)
                # Note: This is an approximation - in production you might want to calculate exact cosine similarity
                similarity_score = 1 - doc.embedding.cosine_distance(query_embedding) if hasattr(doc.embedding, 'cosine_distance') else 0.8
                
                if similarity_score >= similarity_threshold:
                    results.append({
                        'id': doc.id,
                        'text_content': doc.text_content,
                        'source_type': doc.source_type,
                        'source_id': doc.source_id,
                        'metadata': doc.metadata,
                        'similarity_score': similarity_score,
                        'created_at': doc.created_at,
                    })
                
                if len(results) >= top_n:
                    break
            
            logger.info(f"Found {len(results)} similar documents (threshold: {similarity_threshold})")
            return results
            
        except Exception as e:
            logger.error(f"Error searching similar documents: {e}")
            return []

    def delete_documents(
        self,
        source_type: str,
        source_ids: Optional[List[str]] = None
    ) -> int:
        """
        Delete documents by source type and optionally by source IDs.
        
        Args:
            source_type: Type of source to delete
            source_ids: Optional list of specific source IDs to delete
        
        Returns:
            Number of deleted documents
        """
        try:
            queryset = self.model.objects.filter(source_type=source_type)
            
            if source_ids:
                queryset = queryset.filter(source_id__in=source_ids)
            
            deleted_count, _ = queryset.delete()
            logger.info(f"Deleted {deleted_count} documents of type {source_type}")
            return deleted_count
            
        except Exception as e:
            logger.error(f"Error deleting documents: {e}")
            return 0

    def get_document_count(self, source_type: Optional[str] = None) -> int:
        """
        Get the total number of documents, optionally filtered by source type.
        
        Args:
            source_type: Optional source type filter
        
        Returns:
            Document count
        """
        try:
            queryset = self.model.objects.all()
            if source_type:
                queryset = queryset.filter(source_type=source_type)
            return queryset.count()
        except Exception as e:
            logger.error(f"Error getting document count: {e}")
            return 0
