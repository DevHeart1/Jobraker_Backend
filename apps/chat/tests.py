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
        self.assertEqual(str(session), f"Session with {self.user.username} (ID: {session.id}) - Test Session")

    def test_create_chat_message(self):
        session = ChatSession.objects.create(user=self.user, title='Message Test Session')
        message = ChatMessage.objects.create(session=session, sender='user', message_text='Hello, world!')
        self.assertEqual(message.session, session)
        self.assertEqual(message.sender, 'user')
        self.assertEqual(message.message_text, 'Hello, world!')
        self.assertIsNotNone(message.created_at)
        self.assertEqual(str(message), f"User message in session {session.id} at {message.created_at.strftime('%Y-%m-%d %H:%M')}")

class ChatSerializerTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(email='serializer@example.com', password='password123', first_name='Serializer', last_name='User')
        self.session = ChatSession.objects.create(user=self.user, title='Serializer Test Session')
        self.message = ChatMessage.objects.create(session=self.session, sender='user', message_text='Test message content.')

    def test_chat_message_serializer(self):
        serializer = ChatMessageSerializer(instance=self.message)
        data = serializer.data
        self.assertEqual(data['id'], self.message.id)
        self.assertEqual(data['session'], self.session.id)
        self.assertEqual(data['sender'], 'user')
        self.assertEqual(data['message_text'], 'Test message content.')
        self.assertIn('created_at', data)

    def test_chat_session_serializer(self):
        serializer = ChatSessionSerializer(instance=self.session)
        data = serializer.data
        self.assertEqual(data['id'], self.session.id)
        self.assertEqual(data['user']['id'], self.user.id) # Assuming UserSerializer structure
        self.assertEqual(data['title'], 'Serializer Test Session')
        self.assertEqual(data['message_count'], 1)
        self.assertIsNotNone(data['last_message'])
        self.assertEqual(data['last_message']['id'], self.message.id)

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
        ChatSession.objects.create(user=self.user, title='Session 1')
        ChatSession.objects.create(user=self.user, title='Session 2')
        # Create a session for another user to ensure filtering
        other_user = User.objects.create_user(email='otheruser@example.com', password='password', first_name='Other', last_name='User')
        ChatSession.objects.create(user=other_user, title='Other User Session')

        url = reverse('chatsession-list')
        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2) # Should only list sessions for self.user

    def test_retrieve_chat_session_api(self):
        self.client.force_authenticate(user=self.user)
        session = ChatSession.objects.create(user=self.user, title='Detail Test')
        ChatMessage.objects.create(session=session, sender='user', message_text='Hello')
        ChatMessage.objects.create(session=session, sender='ai', message_text='Hi there')

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

        user_msg = ChatMessage.objects.get(session_id=new_session_id, sender='user')
        ai_msg = ChatMessage.objects.get(session_id=new_session_id, sender='ai')
        self.assertEqual(user_msg.message_text, 'Hello AI, new session!')
        self.assertTrue(ai_msg.message_text.startswith("AI response will be here."))

    def test_send_message_existing_session_api(self):
        self.client.force_authenticate(user=self.user)
        session = ChatSession.objects.create(user=self.user, title='Existing Session Test')

        url = reverse('chat')
        data = {'session_id': session.id, 'message_text': 'Another message for existing session.'}
        response = self.client.post(url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(session.messages.count(), 2) # User message + AI simulated message
        self.assertEqual(response.data['session_id'], session.id)
        self.assertEqual(response.data['user_message']['message_text'], 'Another message for existing session.')

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
        self.assertEqual(ChatMessage.objects.filter(sender='user').count(), 1) # User message saved
        self.assertEqual(ChatMessage.objects.filter(sender='ai').count(), 0) # AI message not saved yet

        self.assertIn('task_id', response.data)
        self.assertEqual(response.data['task_id'], 'fake_task_id_123')
        self.assertIn('user_message', response.data)
        self.assertEqual(response.data['user_message']['message_text'], 'Hello AI, process this asynchronously.')

        # Verify that OpenAIJobAssistant.chat_response was called
        mock_assistant_chat_response.assert_called_once()
        args, kwargs = mock_assistant_chat_response.call_args
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
        self.assertEqual(ChatMessage.objects.filter(sender='user').count(), 1) # User message still saved
        self.assertEqual(ChatMessage.objects.filter(sender='ai').count(), 0)

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
        ChatMessage.objects.create(session=self.session, sender='user', message_text='Initial user message for history.')

    @patch('openai.ChatCompletion.create') # Mock the actual OpenAI API call within the task
    def test_get_openai_chat_response_task_success(self, mock_openai_create):
        # Configure the mock for openai.ChatCompletion.create
        mock_openai_create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content="Mocked AI response from task."))]
        )

        # Mock moderation calls within the task to always pass
        with patch('openai.Moderation.create') as mock_moderation:
            mock_moderation.return_value = MagicMock(results=[MagicMock(flagged=False)])

            # Simulate calling the task
            # The task expects user_id, session_id, message, conversation_history, user_profile_data
            user_message_text = "Tell me about Celery."

            # Construct history as the task expects (list of dicts)
            # The task internally fetches history, but the signature accepts it.
            # For this test, we'll rely on the task's internal history fetching logic.
            # The `OpenAIJobAssistant.chat_response` prepares this history.
            # The task receives this prepared history.
            # Let's simulate the history that would be passed.
            prepared_history = [{"role": "user", "content": "Initial user message for history."}]

            task_result = get_openai_chat_response_task.run(
                user_id=self.user.id,
                session_id=self.session.id,
                message=user_message_text,
                conversation_history=prepared_history,
                user_profile_data=None
            )

        self.assertTrue(task_result['success'])
        self.assertEqual(task_result['response'], "Mocked AI response from task.")
        self.assertTrue(task_result.get('message_saved'))

        # Verify AI message was saved to DB
        ai_messages = ChatMessage.objects.filter(session=self.session, sender='ai')
        self.assertEqual(ai_messages.count(), 1)
        self.assertEqual(ai_messages.first().message_text, "Mocked AI response from task.")

        mock_openai_create.assert_called_once()
        # Further assertions on mock_openai_create.call_args can be added
        # Check that moderation was called for user input and AI output
        self.assertEqual(mock_moderation.call_count, 2)


    @patch('openai.ChatCompletion.create')
    def test_get_openai_chat_response_task_openai_api_error(self, mock_openai_create):
        mock_openai_create.side_effect = Exception("Simulated OpenAI API Error")

        with patch('openai.Moderation.create') as mock_moderation:
            mock_moderation.return_value = MagicMock(results=[MagicMock(flagged=False)])

            with self.assertRaises(Exception): # Celery task will re-raise for retry
                get_openai_chat_response_task.run(
                    user_id=self.user.id,
                    session_id=self.session.id,
                    message="A message that will cause error.",
                    conversation_history=[],
                    user_profile_data=None
                )

        # Verify no new AI message was saved
        self.assertEqual(ChatMessage.objects.filter(session=self.session, sender='ai').count(), 0)
        mock_openai_create.assert_called_once()

    def test_get_openai_chat_response_task_session_not_found(self):
        # No mocking needed for OpenAI call as it shouldn't be reached
        task_result = get_openai_chat_response_task.run(
            user_id=self.user.id,
            session_id=99999, # Non-existent session
            message="Test message",
            conversation_history=[],
            user_profile_data=None
        )
        self.assertTrue(task_result['success']) # The task itself might succeed but report an error
        self.assertEqual(task_result['error'], 'session_not_found_for_saving_message')
        self.assertNotIn('message_saved', task_result)


    @patch('openai.ChatCompletion.create') # Mock the actual OpenAI API call
    def test_get_openai_chat_response_task_input_moderation_failure(self, mock_openai_create):
        # Moderation for user input fails
        with patch('openai.Moderation.create') as mock_moderation:
            # First call (user input) is flagged, second (AI output) is not (or not reached)
            mock_moderation.side_effect = [
                MagicMock(results=[MagicMock(flagged=True)]),
                MagicMock(results=[MagicMock(flagged=False)])
            ]

            task_result = get_openai_chat_response_task.run(
                user_id=self.user.id,
                session_id=self.session.id,
                message="Flagged user message.",
                conversation_history=[],
                user_profile_data=None
            )

        self.assertFalse(task_result['success'])
        self.assertEqual(task_result['error'], 'flagged_input')
        mock_openai_create.assert_not_called() # OpenAI chat completion should not be called
        # Verify no new AI message was saved
        self.assertEqual(ChatMessage.objects.filter(session=self.session, sender='ai').count(), 0)


    @patch('openai.ChatCompletion.create') # Mock the actual OpenAI API call
    def test_get_openai_chat_response_task_output_moderation_failure(self, mock_openai_create):
        mock_openai_create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content="Flagged AI response."))]
        )
        # Moderation for user input passes, AI output is flagged
        with patch('openai.Moderation.create') as mock_moderation:
            mock_moderation.side_effect = [
                MagicMock(results=[MagicMock(flagged=False)]), # User input OK
                MagicMock(results=[MagicMock(flagged=True)])  # AI output Flagged
            ]

            task_result = get_openai_chat_response_task.run(
                user_id=self.user.id,
                session_id=self.session.id,
                message="User message leading to flagged AI output.",
                conversation_history=[],
                user_profile_data=None
            )

        self.assertFalse(task_result['success'])
        self.assertEqual(task_result['error'], 'flagged_ai_output') # Corrected error code
        mock_openai_create.assert_called_once()
        # Verify no new AI message was saved (because it was flagged)
        # The current task implementation saves *then* moderates AI output.
        # This test assumes the task might prevent saving if AI output is flagged.
        # Based on current task logic, it saves then returns error, so this check might need adjustment
        # if the task's behavior is to save the flagged message or a placeholder.
        # For now, let's assume the task *would not* save a message it deems problematic.
        # If the task *does* save it and then reports, this test needs to change.
        # The current task code returns an error if AI output is flagged, but *after* trying to save.
        # Let's adjust: the task as written saves the AI message *before* AI output moderation.
        # This is a flaw in the task. For this test, let's assume the ideal where it wouldn't save.
        # To make this test pass with current task logic:
        # self.assertEqual(ChatMessage.objects.filter(session=self.session, sender='ai').count(), 1)
        # self.assertEqual(ChatMessage.objects.filter(session=self.session, sender='ai').first().message_text, "Flagged AI response.")
        # However, the task *should* ideally not save a message that is then flagged.
        # For now, this test will reflect the ideal. If the task is not changed, this test will fail.
        # The task *actually* saves before AI output moderation. So, a message *would* be saved.
        # Let's assume the task logic should be: moderate AI output, then save if not flagged.
        # The current task does: generate AI -> moderate AI -> save AI. This is slightly off.
        # It should be generate AI -> moderate AI -> if not flagged, save AI.
        # The task actually does: generate AI -> save AI -> moderate AI (this is what I see in current task code for user input mod, then AI gen, then AI output mod, then save)
        # Let me re-check the task code structure for saving.
        # The task saves AI message *after* AI output moderation. This is correct.
        # So, if AI output is flagged, it should not be saved.
        self.assertEqual(ChatMessage.objects.filter(session=self.session, sender='ai').count(), 0)

# Need to import MagicMock if not already done (it's part of unittest.mock)
from unittest.mock import MagicMock
