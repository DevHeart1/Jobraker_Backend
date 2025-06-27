from django.db import models
from django.conf import settings

class ChatSession(models.Model):
    """
    Represents a single chat conversation session.
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='chat_sessions',
        help_text="The user who initiated the chat session."
    )
    title = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="Optional title for the chat session."
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="Timestamp when the chat session was created."
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text="Timestamp when the chat session was last updated (e.g., new message)."
    )

    class Meta:
        ordering = ['-updated_at']
        verbose_name = "Chat Session"
        verbose_name_plural = "Chat Sessions"

    def __str__(self):
        return f"Session with {self.user.username} (ID: {self.id}) - {self.title if self.title else 'Untitled'}"

class ChatMessage(models.Model):
    """
    Represents a single message within a chat session.
    """
    SENDER_CHOICES = [
        ('user', 'User'),
        ('ai', 'AI'),
    ]

    session = models.ForeignKey(
        ChatSession,
        on_delete=models.CASCADE,
        related_name='messages',
        help_text="The chat session this message belongs to."
    )
    sender = models.CharField(
        max_length=10,
        choices=SENDER_CHOICES,
        help_text="The sender of the message (user or AI)."
    )
    message_text = models.TextField(
        help_text="The content of the chat message."
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="Timestamp when the message was created."
    )

    class Meta:
        ordering = ['created_at']
        verbose_name = "Chat Message"
        verbose_name_plural = "Chat Messages"

    def __str__(self):
        return f"{self.get_sender_display()} message in session {self.session.id} at {self.created_at.strftime('%Y-%m-%d %H:%M')}"
