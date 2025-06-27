from django.shortcuts import render
from rest_framework import viewsets, permissions, status, serializers # Added serializers
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiParameter, OpenApiExample
from drf_spectacular.openapi import OpenApiTypes

from .models import ChatSession, ChatMessage
from .serializers import ChatSessionSerializer, ChatSessionDetailSerializer, ChatMessageSerializer


@extend_schema_view(
    list=extend_schema(
        summary="List chat sessions",
        description="Retrieve all chat sessions for the current user, ordered by the most recently updated.",
        tags=['Chat'],
        responses={
            200: ChatSessionSerializer(many=True), # Updated to use actual serializer
            401: OpenApiExample(
                'Unauthorized',
                value={'detail': 'Authentication credentials were not provided.'}, # Standard DRF message
                response_only=True
            )
        }
    ),
    create=extend_schema(
        summary="Create chat session",
        description="Start a new chat session with the AI assistant. A title can optionally be provided.",
        tags=['Chat'],
        request=ChatSessionSerializer, # Specify serializer for request body
        responses={
            201: ChatSessionSerializer, # Updated to use actual serializer
            400: OpenApiExample(
                'Bad Request',
                value={'title': ['This field may not be blank.']}, # Example error
                response_only=True
            ),
            401: OpenApiExample(
                'Unauthorized',
                value={'detail': 'Authentication credentials were not provided.'},
                response_only=True
            )
        }
    ),
    retrieve=extend_schema(
        summary="Retrieve a chat session",
        description="Retrieve a specific chat session along with all its messages.",
        tags=['Chat'],
        responses={
            200: ChatSessionDetailSerializer, # Updated to use actual serializer
            401: OpenApiExample(
                'Unauthorized',
                value={'detail': 'Authentication credentials were not provided.'},
                response_only=True
            ),
            404: OpenApiExample(
                'Not Found',
                value={'detail': 'Not found.'},
                response_only=True
            )
        }
    )
)
class ChatSessionViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing AI chat sessions.
    
    Handles chat session lifecycle:
    - Create new chat sessions for different topics
    - List user's chat history and sessions (ordered by last update)
    - Retrieve a specific session with all its messages
    - Manage session metadata and context (e.g., title)
    - Archive or delete old sessions (standard ModelViewSet behavior)
    
    Each session maintains conversation context for better AI responses.
    """
    permission_classes = [permissions.IsAuthenticated]
    # queryset will be set by get_queryset

    def get_queryset(self):
        """
        This view should only return ChatSession objects for the current
        authenticated user, ordered by the last update.
        """
        return ChatSession.objects.filter(user=self.request.user).order_by('-updated_at')

    def get_serializer_class(self):
        """
        Return appropriate serializer class based on action.
        """
        if self.action == 'retrieve':
            return ChatSessionDetailSerializer
        return ChatSessionSerializer

    def perform_create(self, serializer):
        """
        Associate the chat session with the current authenticated user.
        """
        serializer.save(user=self.request.user)

    # list, create, retrieve, update, partial_update, destroy actions
    # are handled by ModelViewSet by default.
    # list: uses get_queryset and ChatSessionSerializer
    # create: uses ChatSessionSerializer and perform_create
    # retrieve: uses get_queryset and ChatSessionDetailSerializer (due to get_serializer_class)

    # Example of custom action if needed later:
    # @action(detail=True, methods=['post'])
    # def archive(self, request, pk=None):
    #     session = self.get_object()
    #     # ... logic to archive session ...
    #     return Response({'status': 'session archived'})


class ChatMessageRequestSerializer(serializers.Serializer):
    """Serializer for the request body of ChatView."""
    message_text = serializers.CharField()
    session_id = serializers.IntegerField(required=False, allow_null=True)
    # session_id is now effectively required if user wants to continue a specific chat,
    # but can be omitted to start a new one.

    def validate_message_text(self, value):
        if not value.strip():
            raise serializers.ValidationError("Message cannot be empty.")
        return value

class ChatMessageAcceptedResponseSerializer(serializers.Serializer):
    """Serializer for the 202 Accepted response from ChatView."""
    task_id = serializers.CharField()
    session_id = serializers.IntegerField()
    user_message = ChatMessageSerializer() # Re-use ChatMessageSerializer for the user's message
    detail = serializers.CharField()


@extend_schema(
    summary="Send chat message (Asynchronous)",
    description="Send a message to the AI chat assistant. If session_id is provided, the message is added to that session. Otherwise, a new session is created. The AI response is processed asynchronously.",
    tags=['Chat'],
    request=ChatMessageRequestSerializer,
    responses={
        status.HTTP_222_ACCEPTED: ChatMessageAcceptedResponseSerializer,
        status.HTTP_400_BAD_REQUEST: OpenApiExample(
            'Bad Request',
            value={'message_text': ['This field is required.']}, # Example, could also be from ChatMessageRequestSerializer directly
            response_only=True
        ),
        401: OpenApiExample(
            'Unauthorized',
            value={'detail': 'Authentication credentials were not provided.'},
            response_only=True
        ),
        status.HTTP_404_NOT_FOUND: OpenApiExample(
            'Session Not Found',
            value={'detail': 'Chat session not found or does not belong to user.'},
            response_only=True
        ),
        status.HTTP_500_INTERNAL_SERVER_ERROR: OpenApiExample(
            'Task Queuing Failed',
            value={'error': 'Failed to queue AI processing task.', 'error_code': 'task_queue_failed'},
            response_only=True
        )
        # Potentially a 422 if input is flagged by moderation before queuing
        # status.HTTP_422_UNPROCESSABLE_ENTITY: OpenApiExample(...)
    }
)
class ChatView(APIView):
    """
    Handles sending messages within a chat session.
    If a session_id is provided, the message is added to that session.
    Otherwise, a new session is created for the user.
    Currently simulates AI responses.
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        """
        Receives a user message, associates it with a chat session (existing or new),
        stores the message, simulates an AI response, and stores that too.
        """
        request_serializer = ChatMessageRequestSerializer(data=request.data)
        if not request_serializer.is_valid():
            return Response(request_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        validated_data = request_serializer.validated_data
        user_message_text = validated_data['message_text']
        session_id = validated_data.get('session_id')
        
        session = None
        
        if session_id:
            try:
                session = ChatSession.objects.get(id=session_id, user=request.user)
            except ChatSession.DoesNotExist:
                return Response(
                    {'detail': 'Chat session not found or does not belong to user.'},
                    status=status.HTTP_404_NOT_FOUND
                )
        else:
            # Create a new session
            # You might want to generate a title automatically or leave it blank
            session = ChatSession.objects.create(user=request.user, title="New Chat")
                                                                        # TODO: Better title generation or allow user to set later

        # Create and save the user's message
        user_chat_message = ChatMessage.objects.create(
            session=session,
            sender='user',
            message_text=user_message_text
        )

        # Simulate AI response (Placeholder for actual OpenAI integration)
        # TODO: Replace this with actual OpenAI call in a later step
        ai_simulated_response_text = "AI response will be here. I received: '{}'".format(user_message_text)
        ai_chat_message = ChatMessage.objects.create(
            session=session,
            sender='ai',
            message_text=ai_simulated_response_text
        )

        # The session's updated_at field will be automatically updated by ChatMessage post_save signal if implemented,
        # or by the ChatSession model's auto_now=True on updated_at if a message save triggers session save.
        # Explicitly save session to ensure updated_at is current if no signals are set up for that.

        # --- OpenAI Integration (Now Asynchronous via Celery) ---
        from apps.integrations.services.openai_service import OpenAIJobAssistant
        from django.conf import settings # For OPENAI_MODEL setting

        # Construct conversation history for the assistant
        # This history should represent the state *before* the current user_chat_message was added,
        # as the task will receive the current message separately.
        # Let's fetch messages older than the current user_chat_message.
        MAX_HISTORY_MESSAGES_FOR_PROMPT = 10
        conversation_history_for_prompt = list(
            session.messages.filter(created_at__lt=user_chat_message.created_at)
            .order_by('-created_at')[:MAX_HISTORY_MESSAGES_FOR_PROMPT]
            .values('sender', 'message_text')
        )[::-1] # Reverse to maintain chronological order for the prompt

        # Prepare user profile data (simplified for now)
        # TODO: Enhance user profile data extraction
        user_profile_data_for_assistant = None
        if hasattr(request.user, 'profile'):
            profile = request.user.profile
            user_profile_data_for_assistant = {
                'experience_level': getattr(profile, 'experience_level', ''),
                'skills': list(getattr(profile, 'skills', []))
                # Add other relevant fields from UserProfile as needed by the assistant/task
            }

        assistant = OpenAIJobAssistant()
        task_submission_result = assistant.chat_response(
            user_id=request.user.id,
            session_id=session.id,
            message=user_chat_message.message_text, # The new user message
            conversation_history=conversation_history_for_prompt,
            user_profile=user_profile_data_for_assistant
        )
        # --- End OpenAI Integration ---

        session.save() # Ensures user_chat_message saving updates session's updated_at

        user_message_data = ChatMessageSerializer(user_chat_message).data

        if task_submission_result.get('status') == 'queued':
            return Response({
                'task_id': task_submission_result.get('task_id'),
                'session_id': session.id,
                'user_message': user_message_data,
                'detail': "AI is processing your message. The response will appear shortly."
            }, status=status.HTTP_222_ACCEPTED) # HTTP 202 Accepted
        else:
            # Handle failure to queue the task (e.g., Celery not running, moderation failure)
            error_message = task_submission_result.get('message', 'Failed to queue AI processing task.')
            error_code = task_submission_result.get('error_code', 'task_queue_failed')
            # Log this server-side error
            # logger.error(f"Failed to queue OpenAI task for session {session.id}: {error_message}") # Assuming logger is configured
            return Response({
                'session_id': session.id,
                'user_message': user_message_data, # Still return the saved user message
                'error': error_message,
                'error_code': error_code
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR) # Or a more specific error like 422 if input flagged


# TODO: [Feature Enhancement] Implement JobAdviceView
# This view is intended to provide specific, structured AI advice based on predefined types
# (e.g., resume, interview, salary). It's distinct from the general conversational chat
# and will require its own logic, request/response serializers, and potentially
# different OpenAI prompting strategies. This can be tackled as a separate feature.
@extend_schema(
    summary="[COMING SOON] Get specific job advice",
    description="Get AI-powered personalized job advice for specific categories like resume review, interview preparation, etc. This feature is not yet implemented.",
    tags=['Chat - Future'],
    deprecated=True, # Mark as deprecated until implemented
    request=OpenApiExample(
        'Job Advice Request (Example)',
        summary='Example request for specific job advice',
        description='Request advice for specific job-related topics. Actual request structure TBD.',
        value={
            "advice_type": "resume_review", # e.g., resume_review, interview_prep, salary_negotiation
            "context_data": { # Structure for context will depend on advice_type
                "job_description_url": "http://example.com/job/123",
                "resume_text": "My current resume text..."
            }
        }
    ),
    responses={
        200: OpenApiExample(
            'Job Advice Response (Example)',
            summary='Example of personalized job advice',
            description='AI-generated advice based on user context. Actual response structure TBD.',
            value={
                "advice_type": "resume_review",
                "summary": "Overall, your resume is strong but could be improved by...",
                "detailed_feedback": [
                    {"section": "Skills", "comment": "Consider adding more quantifiable achievements."},
                    {"section": "Experience", "comment": "Tailor your experience to the job description."}
                ],
                "next_steps": ["Update resume", "Practice STAR method for interviews"],
                "generated_at": "2025-06-16T08:45:00Z"
            }
        ),
        501: OpenApiExample( # Not Implemented
            'Not Implemented',
            value={'detail': 'This feature (Job Advice) is not yet implemented.'},
            response_only=True
        ),
        401: OpenApiExample(
            'Unauthorized',
            value={'detail': 'Authentication credentials were not provided.'},
            response_only=True
        )
    }
)
class JobAdviceView(APIView):
    """
    **[FUTURE FEATURE] AI-powered personalized job advice and recommendations.**
    
    This endpoint is planned to provide specialized guidance for different job search aspects:
    - Resume: Optimization tips and content suggestions
    - Interview: Preparation strategies and practice questions
    - Salary: Negotiation tactics and market data
    - Applications: Strategy and timing recommendations
    - Skills: Development priorities and learning paths
    - Networking: Connection building and relationship tips
    
    It will use user profile data and job market insights for personalization.
    **This feature is not yet implemented.**
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        """
        **Endpoint not yet implemented.**
        When implemented, this will analyze user context and provide tailored recommendations
        based on their profile, experience, and career goals for specific advice types.
        """
        # TODO: [Feature Enhancement] Define request serializer for JobAdviceView
        # TODO: [Feature Enhancement] Implement logic for different advice_type
        # TODO: [Feature Enhancement] Integrate with OpenAI using specific prompts for job advice
        # TODO: [Feature Enhancement] Define response serializer for JobAdviceView
        
        return Response(
            {'detail': 'This feature (Job Advice) is not yet implemented.'},
            status=status.HTTP_501_NOT_IMPLEMENTED
        )
