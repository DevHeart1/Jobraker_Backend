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

    def validate_message_text(self, value):
        if not value.strip():
            raise serializers.ValidationError("Message cannot be empty.")
        return value

@extend_schema(
    summary="Send chat message",
    description="Send a message to the AI chat assistant. If session_id is provided, the message is added to that session. Otherwise, a new session is created.",
    tags=['Chat'],
    request=ChatMessageRequestSerializer,
    responses={
        201: OpenApiExample( # Changed to 201 as new messages are created
            'AI Response',
            summary='AI assistant response and user message',
            description='Returns the user message and the (simulated) AI response, along with session ID.',
            value={
                "session_id": 123,
                "user_message": {
                    "id": 1,
                    "session": 123,
                    "sender": "user",
                    "message_text": "Can you help me improve my resume?",
                    "created_at": "2025-06-16T08:30:00Z"
                },
                "ai_response": {
                    "id": 2,
                    "session": 123,
                    "sender": "ai",
                    "message_text": "AI response will be here.",
                    "created_at": "2025-06-16T08:30:05Z"
                }
            }
        ),
        400: OpenApiExample(
            'Bad Request',
            value={'message_text': ['This field is required.']},
            response_only=True
        ),
        401: OpenApiExample(
            'Unauthorized',
            value={'detail': 'Authentication credentials were not provided.'},
            response_only=True
        ),
        404: OpenApiExample(
            'Session Not Found',
            value={'detail': 'Chat session not found or does not belong to user.'},
            response_only=True
        )
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

        # --- OpenAI Integration ---
        from apps.integrations.services.openai import OpenAIClient
        open_ai_client = OpenAIClient()

        # Construct conversation history for OpenAI
        history_messages = session.messages.order_by('created_at').all() # Get all messages for context
        # Limit history to avoid overly long prompts, e.g., last 10 messages (5 user, 5 AI)
        # More sophisticated context management can be added later.
        MAX_HISTORY_MESSAGES = 10
        recent_history = history_messages.order_by('-created_at')[:MAX_HISTORY_MESSAGES:-1] # fetch last N, then reverse to chronological

        openai_messages = [{"role": "system", "content": "You are a helpful AI job assistant."}]
        for msg in recent_history:
            openai_messages.append({"role": msg.sender, "content": msg.message_text})
        # The user's current message (user_chat_message) is the last one in the history for the API call

        ai_response_text = "Default AI response: Could not connect to AI service."
        try:
            # The user_chat_message is already saved, so it's part of `recent_history` if MAX_HISTORY_MESSAGES is large enough
            # or it's the latest message. The prompt should be the user's *new* message.
            # Let's ensure the history sent to OpenAI includes the latest user message.
            current_openai_prompt_messages = [{"role": "system", "content": "You are a helpful AI job assistant."}]
            for msg_obj in recent_history: # recent_history includes the user_chat_message if correctly fetched
                 current_openai_prompt_messages.append({"role": msg_obj.sender, "content": msg_obj.message_text})


            if not any(m['role'] == 'user' and m['content'] == user_chat_message.message_text for m in current_openai_prompt_messages):
                 # This case should ideally not happen if history fetching is correct
                 # but as a safeguard, ensure the current user message is included.
                 current_openai_prompt_messages.append({"role": "user", "content": user_chat_message.message_text})


            ai_response_text = open_ai_client.chat_completion(
                messages=current_openai_prompt_messages, # Pass the constructed list of message dicts
                model=getattr(settings, 'OPENAI_MODEL', 'gpt-4o-mini') # Use model from settings
            )
        except Exception as e:
            # Log the error, e.g., logger.error(f"OpenAI API call failed: {e}")
            # Keep the default error message for the user for now
            print(f"Error calling OpenAI: {e}") # Basic logging for now
            pass # ai_response_text remains the default error message

        ai_chat_message = ChatMessage.objects.create(
            session=session,
            sender='ai',
            message_text=ai_response_text
        )
        # --- End OpenAI Integration ---

        session.save() # Ensures updated_at is refreshed after AI message too.

        user_message_data = ChatMessageSerializer(user_chat_message).data
        ai_response_data = ChatMessageSerializer(ai_chat_message).data
        
        return Response({
            'session_id': session.id,
            'user_message': user_message_data,
            'ai_response': ai_response_data
        }, status=status.HTTP_201_CREATED)


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
