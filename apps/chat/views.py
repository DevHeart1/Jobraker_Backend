from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import viewsets, permissions, status, serializers
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.pagination import PageNumberPagination
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiExample, OpenApiResponse
from .models import ChatSession, ChatMessage
from .serializers import (
    ChatSessionSerializer,
    ChatSessionListSerializer,
    ChatSessionCreateSerializer,
    ChatMessageSerializer
)

# Optional: for job-specific advice views later
# from apps.accounts.serializers import UserSerializer


# --- Pagination Class ---
class StandardResultsSetPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 100


# --- ChatSession ViewSet ---
@extend_schema_view(
    list=extend_schema(
        summary="List Chat Sessions",
        description="Retrieve all chat sessions for the current user, ordered by most recent activity.",
        tags=["Chat"],
        responses={
            200: ChatSessionListSerializer(many=True),
            401: OpenApiResponse(description="Authentication required")
        }
    ),
    create=extend_schema(
        summary="Create Chat Session",
        description="Start a new chat session. Title is optional.",
        tags=["Chat"],
        request=ChatSessionCreateSerializer,
        responses={
            201: ChatSessionSerializer,
            400: OpenApiResponse(description="Validation Error"),
            401: OpenApiResponse(description="Authentication required")
        }
    ),
    retrieve=extend_schema(
        summary="Retrieve Chat Session",
        description="Get full details of a chat session, including all messages.",
        tags=["Chat"],
        responses={
            200: ChatSessionSerializer,
            404: OpenApiResponse(description="Not Found"),
            401: OpenApiResponse(description="Authentication required")
        }
    )
)
class ChatSessionViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing chat sessions.
    """
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        return ChatSession.objects.filter(user=self.request.user).order_by('-last_message_at', '-updated_at')

    def get_serializer_class(self):
        if self.action == 'list':
            return ChatSessionListSerializer
        elif self.action == 'create':
            return ChatSessionCreateSerializer
        return ChatSessionSerializer

    def perform_create(self, serializer):
        serializer.save(user=self.request.user, last_message_at=timezone.now())


# --- Chat Message Sending View ---
class ChatMessageRequestSerializer(serializers.Serializer):
    message_text = serializers.CharField()
    session_id = serializers.UUIDField(required=False, allow_null=True)

    def validate_message_text(self, value):
        if not value.strip():
            raise serializers.ValidationError("Message cannot be empty.")
        return value


class ChatMessageAcceptedResponseSerializer(serializers.Serializer):
    task_id = serializers.CharField()
    session_id = serializers.UUIDField()
    user_message = ChatMessageSerializer()
    detail = serializers.CharField()


@extend_schema(
    summary="Send Message (Async)",
    description="Send a message to the assistant. If `session_id` is not provided, a new session will be created.",
    tags=["Chat"],
    request=ChatMessageRequestSerializer,
    responses={
        222: ChatMessageAcceptedResponseSerializer,
        400: OpenApiResponse(description="Validation Error"),
        401: OpenApiResponse(description="Authentication required"),
        404: OpenApiResponse(description="Session not found"),
        500: OpenApiResponse(description="Failed to queue AI task")
    }
)
class ChatView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = ChatMessageRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        user = request.user
        session = None

        if data.get('session_id'):
            session = get_object_or_404(ChatSession, id=data['session_id'], user=user)
        else:
            session = ChatSession.objects.create(user=user, title="New Chat", last_message_at=timezone.now())

        user_msg = ChatMessage.objects.create(
            session=session,
            role='user',
            content=data['message_text']
        )

        # --- Simulated AI Response Placeholder ---
        ChatMessage.objects.create(
            session=session,
            role='assistant',
            content=f"AI response placeholder for: {data['message_text']}"
        )

        # --- OpenAI Integration via Celery ---
        from apps.integrations.services.openai_service import OpenAIJobAssistant

        history = list(
            session.messages.filter(timestamp__lt=user_msg.timestamp)
            .order_by('-timestamp')[:10]
            .values('role', 'content')
        )[::-1]

        profile_data = None
        if hasattr(user, 'profile'):
            profile = user.profile
            profile_data = {
                "experience_level": getattr(profile, 'experience_level', ''),
                "skills": list(getattr(profile, 'skills', []))
            }

        assistant = OpenAIJobAssistant()
        result = assistant.chat_response(
            user_id=user.id,
            session_id=session.id,
            message=user_msg.content,
            conversation_history=history,
            user_profile=profile_data
        )

        session.save()

        if result.get("status") == "queued":
            return Response({
                "task_id": result.get("task_id"),
                "session_id": session.id,
                "user_message": ChatMessageSerializer(user_msg).data,
                "detail": "AI is processing your message..."
            }, status=222)
        else:
            return Response({
                "session_id": session.id,
                "user_message": ChatMessageSerializer(user_msg).data,
                "error": result.get("message", "Unknown error."),
                "error_code": result.get("error_code", "task_queue_failed")
            }, status=500)


# --- Placeholder for Future Advice Feature ---
@extend_schema(
    summary="[COMING SOON] Get AI Job Advice",
    description="Get structured AI guidance on resume, interview, salary, and job strategies. [Not yet implemented]",
    tags=["Chat - Future"],
    deprecated=True,
    responses={
        501: OpenApiResponse(description="Not implemented"),
        401: OpenApiResponse(description="Unauthorized")
    }
)
class JobAdviceView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        return Response(
            {"detail": "This feature (Job Advice) is not yet implemented."},
            status=501
        )
