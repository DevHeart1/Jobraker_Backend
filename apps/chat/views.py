from django.shortcuts import render
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiParameter, OpenApiExample, OpenApiResponse
from drf_spectacular.openapi import OpenApiTypes
from .models import ChatSession, ChatMessage # Import models
from .serializers import ( # Import serializers
    ChatSessionSerializer, ChatSessionListSerializer, ChatSessionCreateSerializer,
    ChatMessageSerializer
)
# Assuming StandardResultsSetPagination is defined elsewhere, e.g., in a project-wide paginators.py
# from jobraker.paginators import StandardResultsSetPagination # Example path

# Placeholder for pagination if not defined globally
from rest_framework.pagination import PageNumberPagination
class StandardResultsSetPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 100


@extend_schema_view(
    list=extend_schema(
        summary="List User's Chat Sessions",
        description="Retrieve a paginated list of chat sessions for the authenticated user, ordered by most recent activity.",
        tags=['Chat'],
        responses={
            200: ChatSessionListSerializer(many=True), # Use ChatSessionListSerializer
            401: OpenApiResponse(description="Authentication required", examples=[OpenApiExample('Unauthorized', value={'detail': 'Authentication credentials were not provided.'})])
        }
    ),
    create=extend_schema(
        summary="Create New Chat Session",
        description="Start a new chat session with the AI assistant. A title is optional.",
        tags=['Chat'],
        request=ChatSessionCreateSerializer, # Use ChatSessionCreateSerializer for request
        responses={
            201: ChatSessionSerializer, # Return full session details on create
            400: OpenApiResponse(description="Validation Error", examples=[OpenApiExample('Bad Request', value={'title': ['This field may not be blank.']})]),
            401: OpenApiResponse(description="Authentication required")
        }
    ),
    retrieve=extend_schema(
        summary="Retrieve Chat Session",
        description="Get details of a specific chat session, including its messages.",
        tags=['Chat'],
        responses={
            200: ChatSessionSerializer, # Full detail with messages
            404: OpenApiResponse(description="Not Found"),
            401: OpenApiResponse(description="Authentication required")
        }
    ),
    # Standard update/destroy are less common for sessions, usually handled by archiving or auto-cleanup.
    # For now, we'll rely on ModelViewSet defaults if needed, or can disable them.
    # Example: Disabling update/partial_update/destroy if not desired on this ViewSet directly
    # update=extend_schema(exclude=True),
    # partial_update=extend_schema(exclude=True),
    # destroy=extend_schema(exclude=True),
)
class ChatSessionViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing AI chat sessions.
    
    Allows users to:
    - Create new chat sessions.
    - List their existing chat sessions.
    - Retrieve a specific session with its message history.
    
    Sessions are ordered by the most recent message.
    """
    queryset = ChatSession.objects.all() # Base queryset
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = StandardResultsSetPagination # Add pagination

    def get_serializer_class(self):
        if self.action == 'list':
            return ChatSessionListSerializer
        elif self.action == 'create':
            return ChatSessionCreateSerializer
        # For retrieve (and potentially update/partial_update if enabled)
        return ChatSessionSerializer

    def get_queryset(self):
        """
        This view should return a list of all chat sessions
        for the currently authenticated user.
        """
        return ChatSession.objects.filter(user=self.request.user).order_by('-last_message_at', '-updated_at')

    def perform_create(self, serializer):
        """
        Associate the chat session with the current user upon creation.
        Also sets initial last_message_at.
        """
        from django.utils import timezone # Local import for clarity
        serializer.save(user=self.request.user, last_message_at=timezone.now())
        logger.info(f"ChatSession created for user {self.request.user.id} with title '{serializer.instance.title}'.")

    # Standard list and create actions are provided by ModelViewSet.
    # We've customized get_queryset and perform_create.
    # The `list` method implementation is now handled by ModelViewSet + get_queryset + get_serializer_class.
    # The `create` method implementation is now handled by ModelViewSet + perform_create + get_serializer_class.

    # If you need custom logic beyond what perform_create offers for the create action:
    # def create(self, request, *args, **kwargs):
    #     serializer = self.get_serializer(data=request.data)
    #     serializer.is_valid(raise_exception=True)
    #     self.perform_create(serializer) # This calls our perform_create above
    #     # Customize response if needed, default is to return serialized object with 201
    #     headers = self.get_success_headers(serializer.data)
    #     # Return the full ChatSessionSerializer data on create
    #     full_session_serializer = ChatSessionSerializer(serializer.instance, context=self.get_serializer_context())
    #     return Response(full_session_serializer.data, status=status.HTTP_201_CREATED, headers=headers)


@extend_schema(
    summary="Send chat message",
    description="Send a message to the AI chat assistant for job-related help",
    tags=['Chat'],
    request=OpenApiExample(
        'Chat Message',
        summary='Send message to AI assistant',
        description='Message with optional session context',
        value={
            "message": "Can you help me improve my resume for a Python developer position?",
            "session_id": "session_123"
        }
    ),
    responses={
        200: OpenApiExample(
            'AI Response',
            summary='AI assistant response',
            description='Response from AI with job advice',
            value={
                "user_message": "Can you help me improve my resume for a Python developer position?",
                "ai_response": "I'd be happy to help you improve your resume for a Python developer position. Here are some key recommendations...",
                "session_id": "session_123",
                "message_id": "msg_789",
                "timestamp": "2025-06-16T08:30:00Z"
            }
        ),
        400: OpenApiExample(
            'Bad Request',
            value={'error': 'Message is required'},
            response_only=True
        ),
        401: OpenApiExample(
            'Unauthorized',
            value={'error': 'Authentication required'},
            response_only=True
        )
    }
)
class ChatView(APIView):
    """
    AI-powered job assistance chat interface.
    
    Provides intelligent job search and career guidance through:
    - Resume review and optimization suggestions
    - Interview preparation and practice questions
    - Salary negotiation advice
    - Job market insights and trends
    - Application strategy recommendations
    - Career path guidance
    
    Maintains conversation context for personalized responses.
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        """
        Send a message to the AI assistant and receive guidance.
        
        The AI assistant can help with various job-related topics
        using context from the user's profile and job market data.
        """
        message = request.data.get('message', '')
        session_id = request.data.get('session_id')
        
        if not message:
            return Response(
                {'error': 'Message is required'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # TODO: Implement AI chat response using OpenAI integration
        # This would:
        # 1. Process the user message
        # 2. Get context from user profile and job data
        # 3. Generate AI response using OpenAI
        # 4. Store conversation history
        
        return Response({
            'message': 'AI chat coming soon',
            'user_message': message,
            'ai_response': 'Hello! I\'m your AI job assistant. This feature is coming soon.',
            'session_id': session_id or 'new_session'
        })


@extend_schema(
    summary="Get job advice",
    description="Get AI-powered personalized job advice and recommendations",
    tags=['Chat'],
    request=OpenApiExample(
        'Job Advice Request',
        summary='Request specific job advice',
        description='Request advice for specific job-related topics',
        value={
            "type": "resume",
            "context": "I'm applying for senior Python developer positions and need help with my technical skills section"
        }
    ),
    responses={
        200: OpenApiExample(
            'Job Advice Response',
            summary='Personalized job advice',
            description='AI-generated advice based on user context',
            value={
                "advice_type": "resume",
                "advice": "For senior Python developer positions, highlight your experience with frameworks like Django/Flask, database technologies, cloud platforms, and any leadership or mentoring experience...",
                "recommendations": [
                    "Include specific technologies and versions",
                    "Quantify your achievements with metrics",
                    "Highlight leadership and collaboration skills"
                ],
                "generated_at": "2025-06-16T08:45:00Z"
            }
        ),
        400: OpenApiExample(
            'Bad Request',
            value={'error': 'Invalid advice type'},
            response_only=True
        ),
        401: OpenApiExample(
            'Unauthorized',
            value={'error': 'Authentication required'},
            response_only=True
        )
    }
)
class JobAdviceView(APIView):
    """
    AI-powered personalized job advice and recommendations.
    
    Provides specialized guidance for different job search aspects:
    - Resume: Optimization tips and content suggestions
    - Interview: Preparation strategies and practice questions
    - Salary: Negotiation tactics and market data
    - Applications: Strategy and timing recommendations
    - Skills: Development priorities and learning paths
    - Networking: Connection building and relationship tips
    
    Uses user profile data and job market insights for personalization.
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        """
        Get personalized job advice for specific topics.
        
        Analyzes user context and provides tailored recommendations
        based on their profile, experience, and career goals.
        """
        question_type = request.data.get('type', 'general')  # resume, interview, salary, etc.
        context = request.data.get('context', '')
        
        # TODO: Implement AI-powered job advice
        return Response({
            'message': 'AI job advice coming soon',
            'advice_type': question_type,
            'advice': 'Personalized job advice will be available soon!'
        })
