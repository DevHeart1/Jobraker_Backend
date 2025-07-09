from rest_framework import serializers
from drf_spectacular.utils import extend_schema_serializer, OpenApiExample
from .models import ChatSession, ChatMessage
# from apps.accounts.serializers import UserSerializer  # Optional if you want nested user info


@extend_schema_serializer(
    examples=[
        OpenApiExample(
            'ChatMessage Example',
            summary='A single chat message within a session.',
            description='Represents a message sent by either the user or the AI assistant, including content and role.',
            value={
                "id": "a1b2c3d4-e5f6-7890-1234-567890abcdef",
                "session": "s1s2c3s4-s5f6-s8s0-s2s4-s6s8s0abcdef",
                "role": "user",
                "content": "Can you help me find jobs for a Python developer?",
                "timestamp": "2023-10-27T10:30:00Z",
                "function_call_data": None,
                "function_name": None,
                "metadata": {"model_used": "gpt-4"}
            }
        )
    ]
)
class ChatMessageSerializer(serializers.ModelSerializer):
    """
    Serializer for the ChatMessage model.
    """
    class Meta:
        model = ChatMessage
        fields = [
            'id',
            'session',
            'role',
            'content',
            'timestamp',
            'function_call_data',
            'function_name',
            'metadata'
        ]
        read_only_fields = ('id', 'session', 'timestamp')


class ChatSessionListSerializer(serializers.ModelSerializer):
    """
    Lightweight serializer for listing ChatSession instances.
    Includes a preview of the last message and message count.
    """
    last_message_preview = serializers.SerializerMethodField(help_text="A short preview of the last message in the session.")
    message_count = serializers.SerializerMethodField()
    
    class Meta:
        model = ChatSession
        fields = [
            'id', 'title', 'created_at', 'updated_at', 
            'last_message_at', 'last_message_preview', 'message_count'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'last_message_at']
    
    def get_last_message_preview(self, obj):
        """Get a preview of the last message."""
        last_message = obj.messages.order_by('-timestamp').first()
        if last_message:
            content = last_message.content
            return content[:100] + "..." if len(content) > 100 else content
        return None
    
    def get_message_count(self, obj):
        """Get the number of messages in this session."""
        return obj.messages.count()


@extend_schema_serializer(
    examples=[
        OpenApiExample(
            'ChatSession Detail Example',
            summary='Detailed view of a chat session with recent messages.',
            description='Includes session metadata and a list of recent messages.',
            value={
                "id": "s1s2c3s4-s5f6-s8s0-s2s4-s6s8s0abcdef",
                "user": 1,
                "title": "Resume Review for Python Role",
                "created_at": "2023-10-27T10:00:00Z",
                "updated_at": "2023-10-27T10:35:00Z",
                "last_message_at": "2023-10-27T10:35:00Z",
                "messages": [
                    {
                        "id": "m1...",
                        "role": "user",
                        "content": "Hi, can you look at my resume?",
                        "timestamp": "2023-10-27T10:00:00Z",
                        "function_call_data": None,
                        "function_name": None,
                        "metadata": {}
                    },
                    {
                        "id": "m2...",
                        "role": "assistant",
                        "content": "Sure, please provide it!",
                        "timestamp": "2023-10-27T10:01:00Z",
                        "function_call_data": None,
                        "function_name": None,
                        "metadata": {}
                    }
                ]
            }
        )
    ]
)
class ChatSessionSerializer(serializers.ModelSerializer):
    """
    Detailed serializer for ChatSession including all its messages.
    """
    messages = ChatMessageSerializer(many=True, read_only=True, help_text="Messages within this chat session.")
    # user = UserSerializer(read_only=True)  # Optional

    class Meta:
        model = ChatSession
        fields = [
            'id',
            'user',
            'title',
            'created_at',
            'updated_at',
            'last_message_at',
            'messages'
        ]
        read_only_fields = fields


class ChatSessionCreateSerializer(serializers.ModelSerializer):
    """
    Serializer for creating a new ChatSession.
    Only `title` is user-writable. `user` is set via request context.
    """
    title = serializers.CharField(
        max_length=255,
        required=False,
        allow_blank=True,
        allow_null=True,
        help_text="Optional title for the new chat session."
    )

    class Meta:
        model = ChatSession
        fields = ['title']


@extend_schema_serializer(
    examples=[
        OpenApiExample(
            'Send Message Request',
            summary='Send a message to the AI assistant',
            description='Request to send a message in a chat session',
            value={
                "content": "Can you help me improve my resume for a senior Python developer position?",
                "session_id": "550e8400-e29b-41d4-a716-446655440000"
            },
            request_only=True
        )
    ]
)
class SendMessageSerializer(serializers.Serializer):
    """
    Serializer for sending messages to the AI assistant.
    """
    content = serializers.CharField(
        max_length=10000,
        help_text="The message content to send to the AI assistant"
    )
    session_id = serializers.UUIDField(
        required=False,
        allow_null=True,
        help_text="Optional session ID. If not provided, a new session will be created."
    )
    
    def validate_content(self, value):
        """Validate message content."""
        if not value.strip():
            raise serializers.ValidationError("Message content cannot be empty")
        return value.strip()


@extend_schema_serializer(
    examples=[
        OpenApiExample(
            'Chat Response',
            summary='AI assistant response',
            description='Response from the AI assistant including both messages',
            value={
                "session_id": "550e8400-e29b-41d4-a716-446655440000",
                "user_message": {
                    "id": "660f9500-f39c-52e5-b827-557766551111",
                    "role": "user",
                    "content": "Can you help me improve my resume?",
                    "timestamp": "2025-07-08T10:30:00Z"
                },
                "assistant_message": {
                    "id": "770fa600-f49d-63f6-c938-668877662222",
                    "role": "assistant",
                    "content": "I'd be happy to help you improve your resume. Please share your current resume or tell me about your experience and the type of position you're targeting.",
                    "timestamp": "2025-07-08T10:30:15Z"
                }
            }
        )
    ]
)
class ChatResponseSerializer(serializers.Serializer):
    """
    Serializer for chat responses from the AI assistant.
    """
    session_id = serializers.UUIDField(help_text="The session ID")
    user_message = ChatMessageSerializer(help_text="The user's message")
    assistant_message = ChatMessageSerializer(help_text="The AI assistant's response")
