from django.db import models
from django.conf import settings
from django.utils import timezone
import uuid


class ChatSession(models.Model):
    """
    Represents a single conversation session between a user and the AI assistant.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='chat_sessions',
        help_text="The user who initiated and owns this chat session."
    )

    title = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="Optional user-defined title for the chat session (e.g., 'Resume Review for Python Role')."
    )

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True, db_index=True)

    last_message_at = models.DateTimeField(
        default=timezone.now,
        db_index=True,
        help_text="Timestamp of the last message in this session, for ordering."
    )

    class Meta:
        verbose_name = "Chat Session"
        verbose_name_plural = "Chat Sessions"
        ordering = ['-last_message_at', '-created_at']
        indexes = [
            models.Index(fields=['user', '-last_message_at']),
        ]

    def __str__(self):
        return f"Session {self.id} by {self.user.email} - '{self.title or 'Untitled'}'"

    def update_last_message_at(self):
        """Updates the last_message_at timestamp to now."""
        self.last_message_at = timezone.now()
        self.save(update_fields=['last_message_at', 'updated_at'])


class ChatMessage(models.Model):
    """
    Represents a single message within a ChatSession.
    """

    ROLE_CHOICES = [
        ('user', 'User'),
        ('assistant', 'Assistant'),
        ('system', 'System'),
        ('function', 'Function'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    session = models.ForeignKey(
        ChatSession,
        on_delete=models.CASCADE,
        related_name='messages',
        help_text="The chat session this message belongs to."
    )

    role = models.CharField(
        max_length=10,
        choices=ROLE_CHOICES,
        help_text="The role of the sender of this message (user, assistant, etc.)."
    )

    content = models.TextField(help_text="The text content of the message.")

    function_call_data = models.JSONField(
        null=True,
        blank=True,
        help_text="If role is 'assistant' and a function call was requested by AI, stores call details (name, arguments)."
    )

    function_name = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        help_text="If role is 'function', the name of the function that was called."
    )

    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)

    metadata = models.JSONField(
        default=dict,
        null=True,
        blank=True,
        help_text="Optional metadata (e.g., OpenAI model used, token counts, processing time)."
    )

    class Meta:
        verbose_name = "Chat Message"
        verbose_name_plural = "Chat Messages"
        ordering = ['timestamp']
        indexes = [
            models.Index(fields=['session', 'timestamp']),
        ]

    def __str__(self):
        return f"{self.get_role_display()} message in Session {self.session_id} at {self.timestamp.strftime('%Y-%m-%d %H:%M')}"
