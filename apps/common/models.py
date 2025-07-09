from django.db import models
from typing import List
from django.conf import settings

# Handle pgvector import gracefully
try:
    from pgvector.django import VectorField
    PGVECTOR_AVAILABLE = True
except ImportError:
    PGVECTOR_AVAILABLE = False

class VectorDocument(models.Model):
    """
    Stores text content and its corresponding vector embedding, along with metadata.
    Used for RAG (Retrieval-Augmented Generation) by enabling similarity searches.
    """
    id = models.BigAutoField(primary_key=True)
    text_content = models.TextField(help_text="The actual text content that was embedded.")

    # Use pgvector in production, JSONField for development
    if PGVECTOR_AVAILABLE and not settings.DEBUG:
        embedding = VectorField(
            dimensions=1536,
            help_text="Vector embedding of the text_content using pgvector."
        )
    else:
        embedding = models.JSONField(
            default=list,
            help_text="Vector embedding of the text_content (JSON array for development compatibility)."
        )

    source_type = models.CharField(
        max_length=50,
        db_index=True,
        help_text="Type of the source document (e.g., 'job_listing', 'career_article', 'faq')."
    )
    source_id = models.CharField(
        max_length=255,
        blank=True,
        default='',
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
        # Ensure logger is available if this method is used more broadly
        import logging
        logger = logging.getLogger(__name__)

        self.text_content = new_text_content
        self.embedding = new_embedding
        # self.save() # updated_at will be set automatically - call save where this method is used.
        logger.info(f"Updated content and embedding for VectorDocument: {self.source_type}:{self.source_id} (pending save)")


class KnowledgeArticle(models.Model):
    """
    Model for storing curated content like career advice articles, FAQs,
    interview tips, etc., which can be used for RAG.
    """
    SOURCE_TYPE_CHOICES = [
        ('career_advice', 'Career Advice'),
        ('faq', 'Frequently Asked Question'),
        ('interview_tips', 'Interview Tips'),
        ('company_profile', 'Company Profile'), # Example, if we store general company info
        ('industry_insight', 'Industry Insight'),
        ('other', 'Other Curated Content'),
    ]

    id = models.BigAutoField(primary_key=True)
    title = models.CharField(max_length=255, help_text="Title of the article or content piece.")
    slug = models.SlugField(max_length=255, unique=True, help_text="URL-friendly slug for the article.")
    content = models.TextField(help_text="Full text content of the article.")

    source_type = models.CharField(
        max_length=50,
        choices=SOURCE_TYPE_CHOICES,
        default='other',
        db_index=True,
        help_text="The type of curated content (e.g., 'career_advice', 'faq')."
    )
    category = models.CharField(
        max_length=100,
        blank=True,
        default='',
        db_index=True,
        help_text="Optional category for organizing articles (e.g., 'Resume Writing', 'Job Search Strategies')."
    )
    tags = models.CharField(
        max_length=255,
        blank=True,
        default='',
        help_text="Comma-separated tags for findability (e.g., 'python, django, negotiation')."
    )

    is_active = models.BooleanField(
        default=False,
        db_index=True,
        help_text="Only active articles will be processed for RAG and shown to users."
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Knowledge Article"
        verbose_name_plural = "Knowledge Articles"
        ordering = ['-updated_at', 'title']

    def __str__(self):
        return self.title

    def get_tags_list(self) -> List[str]:
        """Returns tags as a list of strings."""
        if self.tags:
            return [tag.strip() for tag in self.tags.split(',') if tag.strip()]
        return []

    # In a real application, the saving of this model would trigger
    # a signal to embed its content and add/update it in the VectorDocument table.
    # (This will be part of Phase 2 of this plan step)
