from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from unittest.mock import patch # Added patch
from django.contrib.auth import get_user_model
from .models import ChatSession, ChatMessage
from .serializers import ChatSessionSerializer, ChatMessageSerializer

User = get_user_model()

class ChatModelTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(email='test@example.com', password='password123', first_name='Test', last_name='User')

    def test_create_chat_session(self):
        session = ChatSession.objects.create(user=self.user, title='Test Session')
        self.assertEqual(session.user, self.user)
        self.assertEqual(session.title, 'Test Session')
        self.assertIsNotNone(session.created_at)
        self.assertIsNotNone(session.updated_at)
        self.assertEqual(str(session), f"Session {session.id} by {self.user.email} - 'Test Session'")

    def test_create_chat_message(self):
        session = ChatSession.objects.create(user=self.user, title='Message Test Session')
        message = ChatMessage.objects.create(session=session, role='user', content='Hello, world!')
        self.assertEqual(message.session, session)
        self.assertEqual(message.role, 'user')
        self.assertEqual(message.content, 'Hello, world!')
        self.assertIsNotNone(message.timestamp)
        self.assertEqual(str(message), f"User message in Session {session.id} at {message.timestamp.strftime('%Y-%m-%d %H:%M')}")

class ChatSerializerTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(email='serializer@example.com', password='password123', first_name='Serializer', last_name='User')
        self.session = ChatSession.objects.create(user=self.user, title='Serializer Test Session')
        self.message = ChatMessage.objects.create(session=self.session, role='user', content='Test message content.')

    def test_chat_message_serializer(self):
        serializer = ChatMessageSerializer(instance=self.message)
        data = serializer.data
        self.assertEqual(str(data['id']), str(self.message.id))
        self.assertEqual(str(data['session']), str(self.session.id))
        self.assertEqual(data['role'], 'user')
        self.assertEqual(data['content'], 'Test message content.')
        self.assertIn('timestamp', data)

    def test_chat_session_serializer(self):
        serializer = ChatSessionSerializer(instance=self.session)
        data = serializer.data
        self.assertEqual(str(data['id']), str(self.session.id))
        self.assertEqual(str(data['user']), str(self.user.id))  # User is serialized as UUID
        self.assertEqual(data['title'], 'Serializer Test Session')
        self.assertEqual(len(data['messages']), 1)  # Should have 1 message
        # Check the message details
        message_data = data['messages'][0]
        self.assertEqual(str(message_data['id']), str(self.message.id))

    # Removed test_chat_session_detail_serializer since ChatSessionDetailSerializer doesn't exist

class ChatAPITests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(email='api@example.com', password='password123', first_name='API', last_name='User')
        # Use force_authenticate for tests instead of login
        
        # For token authentication, you'd typically generate and use a token:
        # from rest_framework_simplejwt.tokens import RefreshToken
        # refresh = RefreshToken.for_user(self.user)
        # self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {refresh.access_token}')
        # For simplicity in these basic tests, if JWT is the primary auth, ensure it's configured
        # or use self.client.force_authenticate(user=self.user) if simplejwt is not fully set up for tests

    def test_create_chat_session_api(self):
        self.client.force_authenticate(user=self.user) # Ensure user is authenticated
        url = reverse('chatsession-list') # DefaultRouter names it basename-list
        data = {'title': 'API Test Session'}
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(ChatSession.objects.count(), 1)
        self.assertEqual(ChatSession.objects.get().title, 'API Test Session')
        self.assertEqual(ChatSession.objects.get().user, self.user)

    def test_list_chat_sessions_api(self):
        self.client.force_authenticate(user=self.user)
        
        # Clean up any existing sessions for this user (from other tests)
        ChatSession.objects.filter(user=self.user).delete()
        
        ChatSession.objects.create(user=self.user, title='Session 1')
        ChatSession.objects.create(user=self.user, title='Session 2')
        # Create a session for another user to ensure filtering
        other_user = User.objects.create_user(email='otheruser@example.com', password='password', first_name='Other', last_name='User')
        ChatSession.objects.create(user=other_user, title='Other User Session')

        url = reverse('chatsession-list')
        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # The response is paginated, so check the 'results' key
        self.assertIn('results', response.data)
        self.assertEqual(len(response.data['results']), 2) # Should only list sessions for self.user

    def test_retrieve_chat_session_api(self):
        self.client.force_authenticate(user=self.user)
        session = ChatSession.objects.create(user=self.user, title='Detail Test')
        ChatMessage.objects.create(session=session, role='user', content='Hello')
        ChatMessage.objects.create(session=session, role='assistant', content='Hi there')

        url = reverse('chatsession-detail', kwargs={'pk': session.pk})
        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['title'], 'Detail Test')
        self.assertEqual(len(response.data['messages']), 2)

    def test_send_message_new_session_api(self):
        self.client.force_authenticate(user=self.user)
        url = reverse('chat') # Name given in apps/chat/urls.py
        data = {'message_text': 'Hello AI, new session!'}
        response = self.client.post(url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(ChatMessage.objects.count(), 2) # User message + AI simulated message
        self.assertEqual(ChatSession.objects.count(), 1)
        new_session_id = response.data['session_id']
        self.assertIsNotNone(new_session_id)

        user_msg = ChatMessage.objects.get(session_id=new_session_id, role='user')
        ai_msg = ChatMessage.objects.get(session_id=new_session_id, role='assistant')
        self.assertEqual(user_msg.content, 'Hello AI, new session!')
        
        # The AI response should contain some actual response
        self.assertIsNotNone(ai_msg.content)
        self.assertTrue(len(ai_msg.content) > 0)

    def test_send_message_existing_session_api(self):
        self.client.force_authenticate(user=self.user)
        session = ChatSession.objects.create(user=self.user, title='Existing Session Test')

        url = reverse('chat')
        data = {'session_id': session.id, 'message_text': 'Another message for existing session.'}
        response = self.client.post(url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(session.messages.count(), 2) # User message + AI simulated message
        self.assertEqual(response.data['session_id'], session.id)
        self.assertEqual(response.data['user_message']['content'], 'Another message for existing session.')

    def test_send_message_no_text_api(self):
        self.client.force_authenticate(user=self.user)
        url = reverse('chat')
        data = {'message_text': ''} # Empty message
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('message_text', response.data)

    def test_send_message_to_nonexistent_session_api(self):
        self.client.force_authenticate(user=self.user)
        url = reverse('chat')
        data = {'session_id': 9999, 'message_text': 'Message to nowhere.'} # Non-existent session
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_send_message_to_other_user_session_api(self):
        self.client.force_authenticate(user=self.user)
        other_user = User.objects.create_user(email='anotherapiuser@example.com', password='password', first_name='Another', last_name='User')
        other_session = ChatSession.objects.create(user=other_user, title='Not My Session')

        url = reverse('chat')
        data = {'session_id': other_session.id, 'message_text': 'Trying to hijack.'}
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND) # Should be treated as not found for this user

    @patch('apps.integrations.services.openai_service.OpenAIJobAssistant.chat_response')
    def test_send_message_async_task_queued_successfully(self, mock_assistant_chat_response):
        # Configure the mock to return a successful task queuing response
        mock_assistant_chat_response.return_value = {
            'status': 'queued',
            'task_id': 'fake_task_id_123'
        }

        self.client.force_authenticate(user=self.user)
        url = reverse('chat')
        data = {'message_text': 'Hello AI, process this asynchronously.'}
        response = self.client.post(url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(ChatMessage.objects.filter(role='user').count(), 1) # User message saved
        self.assertEqual(ChatMessage.objects.filter(role='assistant').count(), 0) # AI message not saved yet

        self.assertIn('task_id', response.data)
        self.assertEqual(response.data['task_id'], 'fake_task_id_123')
        self.assertIn('user_message', response.data)
        self.assertEqual(response.data['user_message']['content'], 'Hello AI, process this asynchronously.')

        # Verify that OpenAIJobAssistant.chat_response was called
        mock_assistant_chat_response.assert_called_once()
        _, kwargs = mock_assistant_chat_response.call_args
        self.assertEqual(kwargs['message'], 'Hello AI, process this asynchronously.')
        self.assertIsNotNone(kwargs['session_id']) # Check that session_id is passed

    @patch('apps.integrations.services.openai_service.OpenAIJobAssistant.chat_response')
    def test_send_message_async_task_queue_failure(self, mock_assistant_chat_response):
        # Configure the mock to simulate a failure in task queuing (e.g., moderation failed)
        mock_assistant_chat_response.return_value = {
            'status': 'error',
            'message': 'Input violates content guidelines.',
            'error_code': 'flagged_input'
        }

        self.client.force_authenticate(user=self.user)
        url = reverse('chat')
        data = {'message_text': 'A message that would fail moderation.'}
        response = self.client.post(url, data, format='json')

        # Assuming 500 for general task queue failure, or could be 422 if specifically handled
        self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
        self.assertEqual(ChatMessage.objects.filter(role='user').count(), 1) # User message still saved
        self.assertEqual(ChatMessage.objects.filter(role='assistant').count(), 0)

        self.assertIn('error', response.data)
        self.assertEqual(response.data['error'], 'Input violates content guidelines.')
        self.assertEqual(response.data['error_code'], 'flagged_input')
        mock_assistant_chat_response.assert_called_once()

# Tests for the Celery Task
from apps.integrations.tasks import get_openai_chat_response_task
# Note: To test Celery tasks directly, ensure CELERY_TASK_ALWAYS_EAGER=True in test settings.
# This is typically set in jobraker/settings/testing.py

class ChatCeleryTaskTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(email='task@example.com', password='password123', first_name='Task', last_name='User')
        self.session = ChatSession.objects.create(user=self.user, title='Celery Task Test Session')
        # Create an initial user message in the session for history context
        ChatMessage.objects.create(session=self.session, role='user', content='Initial user message for history.')

    @patch('openai.OpenAI')
    def test_get_openai_chat_response_task_success(self, mock_openai_client):
        # Configure the mock for the new OpenAI client
        mock_client_instance = MagicMock()
        mock_openai_client.return_value = mock_client_instance
        mock_client_instance.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content="Mocked AI response from task."))]
        )

        # Simulate calling the task
        user_message_text = "Tell me about Celery."
        prepared_history = [{"role": "user", "content": "Initial user message for history."}]

        task_result = get_openai_chat_response_task.run(
            user_id=self.user.id,
            session_id=self.session.id,
            message=user_message_text,
            conversation_history=prepared_history,
            user_profile_data=None
        )

        self.assertEqual(task_result['status'], 'success')
        self.assertEqual(task_result['content'], "Mocked AI response from task.")
        self.assertIn('message_id', task_result)

        # Verify AI message was saved to DB
        ai_messages = ChatMessage.objects.filter(session=self.session, role='assistant')
        self.assertEqual(ai_messages.count(), 1)
        self.assertEqual(ai_messages.first().content, "Mocked AI response from task.")

        mock_client_instance.chat.completions.create.assert_called_once()


    @patch('openai.OpenAI')
    def test_get_openai_chat_response_task_openai_api_error(self, mock_openai_client):
        # Mock OpenAI API to raise an exception
        mock_client_instance = MagicMock()
        mock_openai_client.return_value = mock_client_instance
        mock_client_instance.chat.completions.create.side_effect = Exception("API Error")

        # The task should handle the error and still save a message
        task_result = get_openai_chat_response_task.run(
            user_id=self.user.id,
            session_id=self.session.id,
            message="Test message",
            conversation_history=[],
            user_profile_data=None
        )

        # Task should still return a result with error status
        self.assertEqual(task_result['status'], 'error')
        self.assertIn('message_id', task_result)
        
        # An error message should be saved
        ai_messages = ChatMessage.objects.filter(session=self.session, role='assistant')
        self.assertEqual(ai_messages.count(), 1)

    def test_get_openai_chat_response_task_session_not_found(self):
        # No mocking needed for OpenAI call as it shouldn't be reached
        task_result = get_openai_chat_response_task.run(
            user_id=self.user.id,
            session_id=99999, # Non-existent session
            message="Test message",
            conversation_history=[],
            user_profile_data=None
        )
        self.assertEqual(task_result['status'], 'error')
        self.assertEqual(task_result['reason'], 'session_not_found')
        self.assertNotIn('message_id', task_result)


    def test_get_openai_chat_response_task_no_api_key(self):
        # Test when no API key is configured
        with patch('django.conf.settings.OPENAI_API_KEY', ''):
            task_result = get_openai_chat_response_task.run(
                user_id=self.user.id,
                session_id=self.session.id,
                message="Test message without API key",
                conversation_history=[],
                user_profile_data=None
            )

        self.assertEqual(task_result['status'], 'error')
        self.assertEqual(task_result['reason'], 'no_api_key')
        self.assertIn('message_id', task_result)
        
        # Verify error message was saved
        ai_messages = ChatMessage.objects.filter(session=self.session, role='assistant')
        self.assertEqual(ai_messages.count(), 1)
        self.assertIn("connection to my core services", ai_messages.first().content)


    @patch('openai.OpenAI')
    def test_get_openai_chat_response_task_with_conversation_history(self, mock_openai_client):
        # Test that conversation history is properly processed
        mock_client_instance = MagicMock()
        mock_openai_client.return_value = mock_client_instance
        mock_client_instance.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content="AI response with history context."))]
        )
        
        # Prepare conversation history with correct field names
        conversation_history = [
            {"role": "user", "content": "Previous user message"},
            {"role": "assistant", "content": "Previous AI response"}
        ]

        task_result = get_openai_chat_response_task.run(
            user_id=self.user.id,
            session_id=self.session.id,
            message="Current user message",
            conversation_history=conversation_history,
            user_profile_data=None
        )

        self.assertEqual(task_result['status'], 'success')
        self.assertEqual(task_result['content'], "AI response with history context.")
        
        # Verify the OpenAI API was called with proper message structure
        mock_client_instance.chat.completions.create.assert_called_once()
        
        # Verify AI message was saved
        ai_messages = ChatMessage.objects.filter(session=self.session, role='assistant')
        self.assertEqual(ai_messages.count(), 1)

# Need to import MagicMock if not already done (it's part of unittest.mock)
from unittest.mock import MagicMock
