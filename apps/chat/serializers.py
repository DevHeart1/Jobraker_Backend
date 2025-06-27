from rest_framework import serializers
from .models import ChatSession, ChatMessage
from apps.accounts.serializers import UserSerializer # Assuming a UserSerializer exists in accounts

class ChatMessageSerializer(serializers.ModelSerializer):
    """
    Serializer for ChatMessage model.
    """
    # Potentially include sender details if User model is linked to sender
    # For now, keeping it simple as per plan
    class Meta:
        model = ChatMessage
        fields = ['id', 'session', 'sender', 'message_text', 'created_at']
        read_only_fields = ['id', 'created_at']

class ChatSessionSerializer(serializers.ModelSerializer):
    """
    Serializer for ChatSession model (basic).
    """
    user = UserSerializer(read_only=True) # Display user details, but don't allow update via this serializer directly
    last_message = serializers.SerializerMethodField()
    message_count = serializers.SerializerMethodField()

    class Meta:
        model = ChatSession
        fields = ['id', 'user', 'title', 'created_at', 'updated_at', 'last_message', 'message_count']
        read_only_fields = ['id', 'user', 'created_at', 'updated_at', 'last_message', 'message_count']

    def get_last_message(self, obj):
        last_msg = obj.messages.order_by('-created_at').first()
        if last_msg:
            return ChatMessageSerializer(last_msg).data
        return None

    def get_message_count(self, obj):
        return obj.messages.count()

class ChatSessionDetailSerializer(ChatSessionSerializer):
    """
    Detailed serializer for a single ChatSession, including all its messages.
    Extends ChatSessionSerializer.
    """
    messages = ChatMessageSerializer(many=True, read_only=True)

    class Meta(ChatSessionSerializer.Meta): # Inherits Meta from ChatSessionSerializer
        fields = ChatSessionSerializer.Meta.fields + ['messages']
        # read_only_fields are also inherited and extended if needed, but messages is already read_only by ChatMessageSerializer

    def to_representation(self, instance):
        """Ensure messages are ordered by creation time."""
        representation = super().to_representation(instance)
        # Messages are already ordered by ChatMessage.Meta.ordering = ['created_at']
        # If custom ordering is needed here for the detail view, it can be done by
        # re-fetching and serializing messages in a specific order.
        # For now, relying on model's default ordering.
        return representation
