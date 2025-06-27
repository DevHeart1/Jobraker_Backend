from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from unittest.mock import patch # Added patch
from django.contrib.auth import get_user_model
from .models import ChatSession, ChatMessage
from .serializers import ChatSessionSerializer, ChatMessageSerializer, ChatSessionDetailSerializer

User = get_user_model()

class ChatModelTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', email='test@example.com', password='password123')

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
        self.user = User.objects.create_user(username='serializeruser', email='serializer@example.com', password='password123')
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

    def test_chat_session_detail_serializer(self):
        # Add another message for detail view
        ChatMessage.objects.create(session=self.session, sender='ai', message_text='AI reply.')
        serializer = ChatSessionDetailSerializer(instance=self.session)
        data = serializer.data
        self.assertEqual(data['id'], self.session.id)
        self.assertEqual(len(data['messages']), 2)
        self.assertEqual(data['messages'][0]['sender'], 'user')
        self.assertEqual(data['messages'][1]['sender'], 'ai')

class ChatAPITests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='apiuser', email='api@example.com', password='password123')
        self.client.login(username='apiuser', password='password123') # Not strictly necessary for token auth but good for session auth if active

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
        other_user = User.objects.create_user(username='otheruser', password='password')
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
        other_user = User.objects.create_user(username='anotherapiuser', password='password')
        other_session = ChatSession.objects.create(user=other_user, title='Not My Session')

        url = reverse('chat')
        data = {'session_id': other_session.id, 'message_text': 'Trying to hijack.'}
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND) # Should be treated as not found for this user

    @patch('apps.integrations.services.openai.OpenAIClient.chat_completion')
    def test_send_message_openai_integration_success(self, mock_chat_completion):
        # Configure the mock to return a successful response
        mock_chat_completion.return_value = "This is a mocked AI response."

        self.client.force_authenticate(user=self.user)
        url = reverse('chat')
        data = {'message_text': 'Hello AI, tell me a joke.'}
        response = self.client.post(url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(ChatMessage.objects.count(), 2) # User message + AI message

        ai_message = ChatMessage.objects.get(sender='ai')
        self.assertEqual(ai_message.message_text, "This is a mocked AI response.")

        # Verify that chat_completion was called
        mock_chat_completion.assert_called_once()
        # You can add more assertions here to check the arguments passed to chat_completion
        args, kwargs = mock_chat_completion.call_args
        self.assertIn('messages', kwargs)
        self.assertTrue(any(msg['role'] == 'user' and msg['content'] == 'Hello AI, tell me a joke.' for msg in kwargs['messages']))

    @patch('apps.integrations.services.openai.OpenAIClient.chat_completion')
    def test_send_message_openai_integration_api_error(self, mock_chat_completion):
        # Configure the mock to simulate an API error
        mock_chat_completion.side_effect = Exception("OpenAI API Error")

        self.client.force_authenticate(user=self.user)
        url = reverse('chat')
        data = {'message_text': 'Query that might cause an error.'}
        response = self.client.post(url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED) # Still 201 as we handle the error internally
        self.assertEqual(ChatMessage.objects.count(), 2) # User message + AI placeholder message

        ai_message = ChatMessage.objects.get(sender='ai')
        self.assertEqual(ai_message.message_text, "Default AI response: Could not connect to AI service.")

        mock_chat_completion.assert_called_once()
