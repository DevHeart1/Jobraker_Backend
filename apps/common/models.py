"""
Common models for shared functionality across apps.
"""

import uuid
from django.db import models
from django.utils import timezone
from pgvector.django import VectorField
from typing import List # Added this import

class VectorDocument(models.Model):
    """
    Model for storing documents with vector embeddings for RAG and semantic search.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Document content
    text_content = models.TextField(help_text="The original text content of the document")
    
    # Vector embedding
    embedding = VectorField(dimensions=1536, null=True, blank=True, help_text="Vector embedding of the text content")
    
    # Source information
    source_type = models.CharField(
        max_length=50, 
        db_index=True,
        help_text="Type of source (e.g., 'job_listing', 'knowledge_article', 'career_advice')"
    )
    source_id = models.CharField(
        max_length=100, 
        null=True, 
        blank=True, 
        db_index=True,
        help_text="ID of the source object (can be null for standalone documents)"
    )
    
    # Metadata storage
    metadata = models.JSONField(
        default=dict, 
        blank=True,
        help_text="Additional metadata for filtering and context"
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'vector_documents'
        verbose_name = 'Vector Document'
        verbose_name_plural = 'Vector Documents'
        indexes = [
            models.Index(fields=['source_type', 'source_id']),
            models.Index(fields=['source_type', 'created_at']),
        ]
        # Allow multiple documents with same source_type and null source_id
        unique_together = []
    
    def __str__(self):
        source_info = f"{self.source_type}"
        if self.source_id:
            source_info += f":{self.source_id}"
        return f"VectorDoc ({source_info}) - {self.text_content[:50]}..."

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
    Model for storing knowledge articles for career advice and job search guidance.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    title = models.CharField(max_length=200)
    content = models.TextField()
    
    # Categories for organization
    category = models.CharField(
        max_length=50,
        choices=[
            ('resume', 'Resume Writing'),
            ('interview', 'Interview Preparation'),
            ('salary', 'Salary Negotiation'),
            ('networking', 'Professional Networking'),
            ('skills', 'Skill Development'),
            ('career_change', 'Career Change'),
            ('job_search', 'Job Search Strategy'),
            ('cover_letter', 'Cover Letter Writing'),
            ('general', 'General Career Advice'),
        ],
        default='general'
    )
    
    # Tags for better organization and filtering
    tags = models.JSONField(default=list, help_text="List of tags for categorization")
    
    # SEO and content metadata
    slug = models.SlugField(max_length=255, unique=True)
    excerpt = models.TextField(blank=True, help_text="Short description or summary")
    
    # Content management
    is_published = models.BooleanField(default=False)
    published_at = models.DateTimeField(null=True, blank=True)
    
    # Author information (optional, can be linked to User model later)
    author_name = models.CharField(max_length=100, blank=True)
    
    # Analytics
    view_count = models.PositiveIntegerField(default=0)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'knowledge_articles'
        verbose_name = 'Knowledge Article'
        verbose_name_plural = 'Knowledge Articles'
        ordering = ['-published_at', '-created_at']
        indexes = [
            models.Index(fields=['category', 'is_published']),
            models.Index(fields=['is_published', '-published_at']),
        ]
    
    def __str__(self):
        return self.title
    
    def save(self, *args, **kwargs):
        if self.is_published and not self.published_at:
            self.published_at = timezone.now()
        super().save(*args, **kwargs)
    
    def increment_view_count(self):
        """Increment the view count for this article."""
        self.view_count += 1
        self.save(update_fields=['view_count'])

    def get_tags_list(self) -> List[str]:
        """Returns tags as a list of strings."""
        if self.tags:
            return [tag.strip() for tag in self.tags.split(',') if tag.strip()]
        return []

    # In a real application, the saving of this model would trigger
    # a signal to embed its content and add/update it in the VectorDocument table.
    # (This will be part of Phase 2 of this plan step)


class EmailTemplate(models.Model):
    """
    Model for storing email templates for notifications and communications.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    
    # Email content
    subject_template = models.CharField(max_length=200)
    html_template = models.TextField(help_text="HTML email template")
    text_template = models.TextField(help_text="Plain text email template")
    
    # Template variables documentation
    variables = models.JSONField(
        default=list, 
        help_text="List of available template variables"
    )
    
    # Categories
    category = models.CharField(
        max_length=50,
        choices=[
            ('job_alert', 'Job Alert'),
            ('application_status', 'Application Status'),
            ('recommendation', 'Job Recommendation'),
            ('welcome', 'Welcome Email'),
            ('notification', 'General Notification'),
            ('reminder', 'Reminder'),
        ],
        default='notification'
    )
    
    # Status
    is_active = models.BooleanField(default=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'email_templates'
        verbose_name = 'Email Template'
        verbose_name_plural = 'Email Templates'
        ordering = ['category', 'name']
    
    def __str__(self):
        return f"{self.name} ({self.category})"
