"""
Common Services for the Jobraker Application.
Includes VectorDBService for interacting with pgvector and EmailService for notifications.
"""
import logging
from typing import List, Dict, Optional, Any
from django.core.mail import EmailMultiAlternatives
from django.template import Template, Context
from django.conf import settings
from django.utils import timezone
# from django.db import connection # For raw SQL if needed with pgvector
# from pgvector.django import L2Distance # Example import for pgvector operations with Django ORM
# Assuming models.py is in the same app 'common'
# from .models import VectorDocument # This will be used once models.py is confirmed

logger = logging.getLogger(__name__)


class EmailService:
    """
    Service for sending templated emails and notifications.
    """
    
    def __init__(self):
        self.from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@jobraker.com')
    
    def send_templated_email(
        self,
        template_name: str,
        recipient_email: str,
        context_data: Dict[str, Any],
        recipient_name: Optional[str] = None
    ) -> bool:
        """
        Send an email using a stored template.
        
        Args:
            template_name: Name of the email template to use
            recipient_email: Email address to send to
            context_data: Dictionary of variables for template rendering
            recipient_name: Optional recipient name for personalization
        
        Returns:
            True if email was sent successfully, False otherwise
        """
        try:
            from apps.common.models import EmailTemplate
            
            template = EmailTemplate.objects.get(name=template_name, is_active=True)
            
            # Add standard context variables
            full_context = {
                'recipient_name': recipient_name or 'User',
                'site_name': 'Jobraker',
                'site_url': getattr(settings, 'SITE_URL', 'https://jobraker.com'),
                'current_year': timezone.now().year,
                **context_data
            }
            
            # Render templates
            subject = Template(template.subject_template).render(Context(full_context))
            html_content = Template(template.html_template).render(Context(full_context))
            text_content = Template(template.text_template).render(Context(full_context))
            
            # Create and send email
            email = EmailMultiAlternatives(
                subject=subject,
                body=text_content,
                from_email=self.from_email,
                to=[recipient_email]
            )
            email.attach_alternative(html_content, "text/html")
            
            email.send()
            logger.info(f"Email sent successfully to {recipient_email} using template {template_name}")
            return True
            
        except EmailTemplate.DoesNotExist:
            logger.error(f"Email template '{template_name}' not found or inactive")
            return False
        except Exception as e:
            logger.error(f"Error sending email to {recipient_email}: {e}")
            return False
    
    def send_job_alert_email(
        self,
        user_email: str,
        user_name: str,
        jobs: List[Dict[str, Any]],
        alert_name: str
    ) -> bool:
        """
        Send job alert email with matching jobs.
        
        Args:
            user_email: User's email address
            user_name: User's name
            jobs: List of job dictionaries
            alert_name: Name of the job alert
        
        Returns:
            True if email was sent successfully
        """
        context = {
            'alert_name': alert_name,
            'jobs': jobs,
            'jobs_count': len(jobs)
        }
        
        return self.send_templated_email(
            template_name='job_alert',
            recipient_email=user_email,
            recipient_name=user_name,
            context_data=context
        )
    
    def send_application_status_email(
        self,
        user_email: str,
        user_name: str,
        job_title: str,
        company_name: str,
        status: str,
        additional_info: Optional[str] = None
    ) -> bool:
        """
        Send application status update email.
        
        Args:
            user_email: User's email address
            user_name: User's name
            job_title: Title of the job
            company_name: Name of the company
            status: Current application status
            additional_info: Optional additional information
        
        Returns:
            True if email was sent successfully
        """
        context = {
            'job_title': job_title,
            'company_name': company_name,
            'status': status,
            'additional_info': additional_info
        }
        
        return self.send_templated_email(
            template_name='application_status',
            recipient_email=user_email,
            recipient_name=user_name,
            context_data=context
        )
    
    def send_job_recommendations_email(
        self,
        user_email: str,
        user_name: str,
        recommended_jobs: List[Dict[str, Any]]
    ) -> bool:
        """
        Send personalized job recommendations email.
        
        Args:
            user_email: User's email address
            user_name: User's name
            recommended_jobs: List of recommended job dictionaries
        
        Returns:
            True if email was sent successfully
        """
        context = {
            'recommended_jobs': recommended_jobs,
            'recommendations_count': len(recommended_jobs)
        }
        
        return self.send_templated_email(
            template_name='job_recommendations',
            recipient_email=user_email,
            recipient_name=user_name,
            context_data=context
        )
    
    def send_welcome_email(
        self,
        user_email: str,
        user_name: str
    ) -> bool:
        """
        Send welcome email to new users.
        
        Args:
            user_email: User's email address
            user_name: User's name
        
        Returns:
            True if email was sent successfully
        """
        context = {
            'getting_started_url': f"{getattr(settings, 'SITE_URL', 'https://jobraker.com')}/getting-started",
            'dashboard_url': f"{getattr(settings, 'SITE_URL', 'https://jobraker.com')}/dashboard"
        }
        
        return self.send_templated_email(
            template_name='welcome',
            recipient_email=user_email,
            recipient_name=user_name,
            context_data=context
        )


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


import logging
from typing import List, Dict, Any, Optional, Tuple, Iterable

from django.conf import settings
from pinecone import Pinecone, Index, ApiException
# from pinecone.models.sparse_values import SparseValues # If using sparse vectors

logger = logging.getLogger(__name__)

# Define a default embedding dimension if not specified elsewhere or to validate against
# Common dimension for text-embedding-3-small is 1536
DEFAULT_EMBEDDING_DIMENSION = 1536


class VectorDBService:
    """
    Service for interacting with a vector database (Pinecone).
    Handles initialization, adding/upserting documents, searching, and deleting.
    """

    def __init__(self, index_name: Optional[str] = None, namespace: Optional[str] = None):
        self.api_key = getattr(settings, 'PINECONE_API_KEY', None)
        self.environment = getattr(settings, 'PINECONE_ENVIRONMENT', None)
        self.index_name = index_name or getattr(settings, 'PINECONE_INDEX_NAME', 'jobraker-default-index')
        self.namespace = namespace or getattr(settings, 'PINECONE_NAMESPACE', 'jobraker-default-ns') # Default namespace

        if not self.api_key or not self.environment:
            logger.error("Pinecone API key or environment not configured in settings.")
            raise ValueError("Pinecone API key or environment not configured.")

        try:
            # Initialize Pinecone client
            # As of pinecone-client v3.x, initialization is simplified
            self.pinecone_client = Pinecone(api_key=self.api_key, environment=self.environment)
            self.index: Index = self._get_or_create_index()

        except Exception as e:
            logger.error(f"Failed to initialize Pinecone client or connect to index '{self.index_name}': {e}")
            # Depending on strictness, could raise error or allow for mock/dummy operations
            raise ConnectionError(f"Could not connect to Pinecone: {e}") from e

    def _get_or_create_index(self) -> Index:
        """
        Gets the Pinecone index object. Creates it if it doesn't exist with default settings.
        Note: Production index creation should ideally be managed via IaC or Pinecone console.
        """
        try:
            if self.index_name not in self.pinecone_client.list_indexes().names:
                logger.warning(
                    f"Pinecone index '{self.index_name}' not found. "
                    f"Attempting to create it with default dimension ({DEFAULT_EMBEDDING_DIMENSION}) and metric ('cosine')."
                )
                # Default metric is 'cosine' for many text embedding models
                # Dimension should match your embedding model, e.g., 1536 for text-embedding-3-small
                self.pinecone_client.create_index(
                    name=self.index_name,
                    dimension=getattr(settings, 'PINECONE_INDEX_DIMENSION', DEFAULT_EMBEDDING_DIMENSION),
                    metric=getattr(settings, 'PINECONE_INDEX_METRIC', 'cosine'),
                    spec={"serverless": {"cloud": "aws", "region": "us-west-2"}} # Example for serverless, adjust as needed
                    # For pod-based indexes, spec would be different, e.g.
                    # spec={"pod": {"environment": self.environment, "pods": 1, "pod_type": "p1.x1"}}
                )
                logger.info(f"Pinecone index '{self.index_name}' created successfully.")
            else:
                logger.info(f"Successfully connected to existing Pinecone index '{self.index_name}'.")
            return self.pinecone_client.Index(self.index_name)
        except ApiException as e:
            logger.error(f"Pinecone API error while getting/creating index '{self.index_name}': {e}")
            raise
        except Exception as e: # Catch other potential errors during index handling
            logger.error(f"Unexpected error while getting/creating index '{self.index_name}': {e}")
            raise


    def add_documents(
        self,
        texts: List[str], # Though not directly stored in vector, useful for context if metadata doesn't have it
        embeddings: List[List[float]],
        source_types: List[str],
        source_ids: List[str],
        metadatas: List[Dict[str, Any]],
        batch_size: int = 100 # Pinecone recommends batching upserts
    ) -> bool:
        """
        Adds or updates documents (vectors) in the Pinecone index.

        Args:
            texts: Original text content (can be part of metadata).
            embeddings: List of embedding vectors.
            source_types: List of source types for each document (e.g., 'job_listing', 'knowledge_article').
            source_ids: List of unique IDs for each document within its source type.
            metadatas: List of metadata dictionaries for each document.
                       Metadata should be suitable for Pinecone (strings, numbers, booleans, or lists of strings).
            batch_size: Number of vectors to upsert in a single batch.

        Returns:
            True if documents were added/updated successfully, False otherwise.
        """
        if not (len(texts) == len(embeddings) == len(source_types) == len(source_ids) == len(metadatas)):
            logger.error("Mismatched lengths of input arguments for add_documents.")
            return False

        if not self.index:
            logger.error("Pinecone index not available for add_documents.")
            return False

        vectors_to_upsert = []
        for i, embedding in enumerate(embeddings):
            doc_id = f"{source_types[i]}_{source_ids[i]}" # Construct a unique ID for Pinecone

            # Ensure metadata is clean and suitable for Pinecone
            # Pinecone metadata values can be string, number, boolean, or list of strings.
            # Complex objects or deeply nested dicts are not directly supported.
            current_metadata = {
                "original_text_preview": texts[i][:200], # Store a preview of text
                "source_type": source_types[i],
                "source_id": source_ids[i],
                **metadatas[i] # Add other metadata
            }

            # Sanitize metadata: convert non-compliant types to strings or handle them
            sanitized_metadata = {}
            for key, value in current_metadata.items():
                if isinstance(value, (str, int, float, bool)):
                    sanitized_metadata[key] = value
                elif isinstance(value, list) and all(isinstance(item, str) for item in value):
                    sanitized_metadata[key] = value
                elif value is None:
                    continue # Skip None values or replace with a placeholder like "N/A"
                else:
                    # For other types (like dicts, complex objects), convert to string or skip
                    sanitized_metadata[key] = str(value)[:1000] # Truncate long strings
                    logger.debug(f"Converted metadata field '{key}' to string for document ID '{doc_id}'. Original type: {type(value)}")

            vectors_to_upsert.append({
                "id": doc_id,
                "values": embedding,
                "metadata": sanitized_metadata
            })

        try:
            for i in range(0, len(vectors_to_upsert), batch_size):
                batch = vectors_to_upsert[i:i + batch_size]
                self.index.upsert(vectors=batch, namespace=self.namespace)
            logger.info(f"Successfully upserted {len(vectors_to_upsert)} documents to Pinecone index '{self.index_name}' in namespace '{self.namespace}'.")
            return True
        except ApiException as e:
            logger.error(f"Pinecone API error during upsert: {e}")
        except Exception as e:
            logger.error(f"Unexpected error during upsert to Pinecone: {e}")
        return False

    def search_similar_documents(
        self,
        query_embedding: List[float],
        top_n: int = 5,
        filter_criteria: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Searches for documents in Pinecone similar to the query embedding.

        Args:
            query_embedding: The embedding vector of the query.
            top_n: The number of similar documents to retrieve.
            filter_criteria: A dictionary for metadata filtering (e.g., {"source_type": "job_listing"}).
                             See Pinecone documentation for filter syntax.

        Returns:
            A list of dictionaries, each representing a similar document
            including its ID, score, and metadata.
        """
        if not self.index:
            logger.error("Pinecone index not available for search_similar_documents.")
            return []

        try:
            results = self.index.query(
                vector=query_embedding,
                top_k=top_n,
                include_metadata=True,
                namespace=self.namespace,
                filter=filter_criteria # Pinecone filter dict
            )

            formatted_results = []
            if results and results.matches:
                for match in results.matches:
                    # Reconstruct original source_id and source_type if stored in metadata
                    metadata = match.metadata or {}
                    text_content = metadata.get("original_text_preview", "") # Example, adjust if full text is needed
                    if not text_content and metadata.get("source_id") and metadata.get("source_type"):
                        # Potentially fetch full text from primary DB if only preview is in Pinecone
                        # For now, this is a placeholder if full text is not in metadata
                        pass

                    formatted_results.append({
                        "id": match.id, # Pinecone's unique ID
                        "score": match.score,
                        "metadata": metadata,
                        "text_content": text_content, # Include text if available
                        "source_type": metadata.get("source_type"),
                        "source_id": metadata.get("source_id")
                    })
            return formatted_results
        except ApiException as e:
            logger.error(f"Pinecone API error during search: {e}")
        except Exception as e:
            logger.error(f"Unexpected error during search in Pinecone: {e}")
        return []

    def delete_documents(
        self,
        source_type: Optional[str] = None, # Original source type
        source_id: Optional[str] = None,   # Original source ID
        doc_ids: Optional[List[str]] = None # Direct Pinecone document IDs
    ) -> bool:
        """
        Deletes documents from the Pinecone index.
        Can delete by a single source_type/source_id pair or by a list of direct Pinecone doc_ids.

        Args:
            source_type: The original source type of the document.
            source_id: The original source ID of the document.
            doc_ids: A list of direct Pinecone document IDs to delete.

        Returns:
            True if deletion was successful or documents were not found, False on error.
        """
        if not self.index:
            logger.error("Pinecone index not available for delete_documents.")
            return False

        ids_to_delete = []
        if doc_ids:
            ids_to_delete.extend(doc_ids)
        elif source_type and source_id:
            constructed_id = f"{source_type}_{source_id}"
            ids_to_delete.append(constructed_id)
        else:
            logger.warning("No valid identifiers provided for document deletion.")
            return False

        if not ids_to_delete:
            logger.info("No documents to delete.")
            return True

        try:
            delete_response = self.index.delete(ids=ids_to_delete, namespace=self.namespace)
            # Pinecone delete operation doesn't explicitly state how many were deleted,
            # it's successful if no error is raised.
            # delete_response is typically {} or None on success.
            logger.info(f"Delete operation for IDs {ids_to_delete} in namespace '{self.namespace}' completed. Response: {delete_response}")
            return True
        except ApiException as e:
            logger.error(f"Pinecone API error during delete: {e}")
        except Exception as e:
            logger.error(f"Unexpected error during delete from Pinecone: {e}")
        return False

    def get_index_stats(self) -> Optional[Dict[str, Any]]:
        """Returns statistics about the current index."""
        if not self.index:
            logger.error("Pinecone index not available for get_index_stats.")
            return None
        try:
            return self.index.describe_index_stats()
        except Exception as e:
            logger.error(f"Error fetching index stats: {e}")
            return None

# Example usage (for testing or direct calls, not typically used by Celery tasks directly this way)
# if __name__ == '__main__':
#     # This requires Django settings to be configured, especially PINECONE_API_KEY etc.
#     # Not runnable standalone without manage.py context or similar setup.
#     try:
#         # Configure settings if running standalone (very basic, for local testing only)
#         from django.conf import settings as django_settings
#         if not django_settings.configured:
#             django_settings.configure(
#                 PINECONE_API_KEY="YOUR_API_KEY",
#                 PINECONE_ENVIRONMENT="YOUR_ENV",
#                 PINECONE_INDEX_NAME="my-test-index",
#                 # PINECONE_NAMESPACE="my-test-ns" # Optional
#             )
#         logger.info("Attempting to initialize VectorDBService for example.")
#         vector_db = VectorDBService()
#         logger.info(f"Index stats: {vector_db.get_index_stats()}")

#         # Example: Add documents
#         # texts_data = ["Sample job 1 description", "Another job details here"]
#         # embeddings_data = [[0.1]*DEFAULT_EMBEDDING_DIMENSION, [0.2]*DEFAULT_EMBEDDING_DIMENSION] # Replace with actual embeddings
#         # source_types_data = ["job", "job"]
#         # source_ids_data = ["job123", "job456"]
#         # metadatas_data = [{"title": "Software Engineer"}, {"title": "Data Analyst"}]
#         # vector_db.add_documents(texts_data, embeddings_data, source_types_data, source_ids_data, metadatas_data)
#         # logger.info(f"Index stats after add: {vector_db.get_index_stats()}")

#         # Example: Search
#         # query_emb = [0.15]*DEFAULT_EMBEDDING_DIMENSION # Replace with actual query embedding
#         # results = vector_db.search_similar_documents(query_emb, top_n=1)
#         # logger.info(f"Search results: {results}")

#         # Example: Delete
#         # vector_db.delete_documents(source_type="job", source_id="job123")
#         # logger.info(f"Index stats after delete: {vector_db.get_index_stats()}")

#     except Exception as e:
#         logger.error(f"Error in VectorDBService example: {e}")

# Placeholder for KnowledgeArticle model if needed by service directly
# from apps.common.models import KnowledgeArticle (if used directly, but tasks handle model fetching)

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
