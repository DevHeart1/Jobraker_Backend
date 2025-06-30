from rest_framework import serializers
from drf_spectacular.utils import extend_schema_serializer, OpenApiExample
from .models import ChatSession, ChatMessage
# from apps.accounts.serializers import UserSerializer # For nested user info if needed

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
        read_only_fields = ('id', 'session', 'timestamp') # Role, content typically set on create
        # `session` is usually set by the view/service logic, not directly by client via serializer for message creation within a session.

# For ChatSessionSerializer, we might want to show the last message or a count.
class ChatSessionListSerializer(serializers.ModelSerializer):
    """
    Lightweight serializer for listing ChatSession instances.
    Includes a preview of the last message.
    """
    last_message_preview = serializers.SerializerMethodField(help_text="A short preview of the last message in the session.")
    message_count = serializers.SerializerMethodField(help_text="Total number of messages in this session.")

    class Meta:
        model = ChatSession
        fields = [
            'id',
            'user', # Typically a read_only_field showing user ID or nested UserSerializer
            'title',
            'created_at',
            'updated_at',
            'last_message_at',
            'last_message_preview',
            'message_count'
        ]
        read_only_fields = ('id', 'user', 'created_at', 'updated_at', 'last_message_at', 'last_message_preview', 'message_count')

    def get_last_message_preview(self, obj: ChatSession) -> Optional[str]:
        last_msg = obj.messages.order_by('-timestamp').first()
        if last_msg:
            return f"{last_msg.get_role_display()}: {last_msg.content[:75]}{'...' if len(last_msg.content) > 75 else ''}"
        return None

    def get_message_count(self, obj: ChatSession) -> int:
        return obj.messages.count()


@extend_schema_serializer(
    examples=[
        OpenApiExample(
            'ChatSession Detail Example',
            summary='Detailed view of a chat session with recent messages.',
            description='Includes session metadata and a list of recent messages.',
            value={
                "id": "s1s2c3s4-s5f6-s8s0-s2s4-s6s8s0abcdef",
                "user": 1, # or nested user object
                "title": "Resume Review for Python Role",
                "created_at": "2023-10-27T10:00:00Z",
                "updated_at": "2023-10-27T10:35:00Z",
                "last_message_at": "2023-10-27T10:35:00Z",
                "messages": [
                    {
                        "id": "m1...", "role": "user", "content": "Hi, can you look at my resume?",
                        "timestamp": "2023-10-27T10:00:00Z", "function_call_data": None, "function_name": None, "metadata": {}
                    },
                    {
                        "id": "m2...", "role": "assistant", "content": "Sure, please provide it!",
                        "timestamp": "2023-10-27T10:01:00Z", "function_call_data": None, "function_name": None, "metadata": {}
                    }
                ]
            }
        )
    ]
)
class ChatSessionSerializer(serializers.ModelSerializer):
    """
    Serializer for the ChatSession model, including a list of recent messages.
    """
    messages = ChatMessageSerializer(many=True, read_only=True, help_text="Messages within this chat session.")
    # user = UserSerializer(read_only=True) # Example if you want full nested user

    class Meta:
        model = ChatSession
        fields = [
            'id',
            'user',
            'title',
            'created_at',
            'updated_at',
            'last_message_at',
            'messages' # For detail view
        ]
        read_only_fields = ('id', 'user', 'created_at', 'updated_at', 'last_message_at')
        # Title can be writable on create/update

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # For performance, only include messages if it's a detail view (instance is present)
        # or if specifically requested via context.
        # This example assumes messages are always included if this serializer is used.
        # A common pattern is to have a separate Detail serializer for messages.
        # For now, this will try to serialize all messages.
        # In a view, you might prefetch: `queryset.prefetch_related('messages')`


class ChatSessionCreateSerializer(serializers.ModelSerializer):
    """
    Serializer specifically for creating a new ChatSession.
    Only `title` is writeable by the user. `user` is set by the view.
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
        fields = ['title'] # Only title is user-settable on create
        # 'user' will be set in the view based on request.user
        # 'id', 'created_at', 'updated_at', 'last_message_at' are auto-set or set by logic
