from django.db import models
from pgvector.django import VectorField

class VectorDocument(models.Model):
    """
    Stores text content and its corresponding vector embedding, along with metadata.
    Used for RAG (Retrieval-Augmented Generation) by enabling similarity searches.
    """
    id = models.BigAutoField(primary_key=True) # Explicitly adding BigAutoField for clarity
    text_content = models.TextField(help_text="The actual text content that was embedded.")

    # Assuming usage of OpenAI's text-embedding-3-small or similar, which can have 1536 dimensions.
    # Adjust dimensions if using a different embedding model.
    embedding = VectorField(dimensions=1536, help_text="Vector embedding of the text_content.")

    source_type = models.CharField(
        max_length=50,
        db_index=True,
        help_text="Type of the source document (e.g., 'job_listing', 'career_article', 'faq')."
    )
    source_id = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        db_index=True,
        help_text="Identifier of the original source object (e.g., Job ID, Article ID)."
    )
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Additional metadata for filtering or display (e.g., company, location, category, tags)."
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Vector Document"
        verbose_name_plural = "Vector Documents"
        # Unique constraint to prevent duplicate entries for the same source object
        unique_together = ('source_type', 'source_id')
        indexes = [
            # A HNSW index is generally recommended for pgvector for performance.
            # This needs to be created with a separate migration operation if not automatically handled.
            # Example (to be added in a migration if needed):
            # HnswIndex(
            #     name='vectordoc_embedding_hnsw_l2_idx',
            #     field='embedding',
            #     m=16, # Default is 16
            #     ef_construction=64, # Default is 64
            #     opclasses=['vector_l2_ops'] # For L2 distance, common with normalized OpenAI embeddings
            # )
            # Or for cosine similarity: opclasses=['vector_cosine_ops']
            # For now, basic field indexes are created by db_index=True on source_type and source_id.
            # The VectorField itself will also typically be indexed by pgvector.
        ]

    def __str__(self):
        return f"{self.source_type}:{self.source_id} - {self.text_content[:60]}..."

    def update_embedding(self, new_text_content: str, new_embedding: list[float]):
        """
        Helper method to update text content and embedding.
        """
        self.text_content = new_text_content
        self.embedding = new_embedding
        self.save() # updated_at will be set automatically
        logger.info(f"Updated embedding for VectorDocument: {self.source_type}:{self.source_id}")

# It's good practice to import logger if used in model methods, though not strictly necessary for this definition.
# import logging
# logger = logging.getLogger(__name__)
