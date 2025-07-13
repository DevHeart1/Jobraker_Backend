"""
WebSocket consumers for real-time chat and notifications.
"""

import json
import logging
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from apps.chat.models import ChatSession, ChatMessage
from apps.integrations.services.openai_service import OpenAIService

logger = logging.getLogger(__name__)
User = get_user_model()


class ChatConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for real-time chat functionality.
    """
    
    async def connect(self):
        """
        Called when the websocket is handshaking as part of the connection process.
        """
        self.session_id = self.scope['url_route']['kwargs']['session_id']
        self.room_group_name = f'chat_{self.session_id}'
        
        # Join room group
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        
        # Accept the connection
        await self.accept()
        
        # Send connection success message
        await self.send(text_data=json.dumps({
            'type': 'connection_established',
            'message': 'Connected to chat session'
        }))
    
    async def disconnect(self, close_code):
        """
        Called when the WebSocket closes for any reason.
        """
        # Leave room group
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )
    
    async def receive(self, text_data):
        """
        Called when we receive a message from the WebSocket.
        """
        try:
            data = json.loads(text_data)
            message_type = data.get('type', 'message')
            
            if message_type == 'message':
                await self.handle_chat_message(data)
            elif message_type == 'typing':
                await self.handle_typing_indicator(data)
            elif message_type == 'mark_read':
                await self.handle_mark_read(data)
            else:
                await self.send_error('Unknown message type')
        
        except json.JSONDecodeError:
            await self.send_error('Invalid JSON')
        except Exception as e:
            logger.error(f"Error handling WebSocket message: {e}")
            await self.send_error('Internal server error')
    
    async def handle_chat_message(self, data):
        """
        Handle incoming chat messages.
        """
        user = self.scope.get('user')
        if isinstance(user, AnonymousUser):
            await self.send_error('Authentication required')
            return
        
        message_content = data.get('message', '').strip()
        if not message_content:
            await self.send_error('Message content required')
            return
        
        # Save user message to database
        await self.save_message(user, message_content, 'user')

        # Trigger AI response generation via Celery task
        from apps.integrations.tasks import get_openai_chat_response_task
        get_openai_chat_response_task.delay(
            user_id=str(user.id),
            session_id=self.session_id,
            message=message_content
        )

        # Send the user's message back to the group immediately
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'chat_message',
                'message': message_content,
                'sender': user.username,
                'sender_type': 'user'
            }
        )

    async def handle_typing_indicator(self, data):
        """
        Handle typing indicators from users.
        """
        user = self.scope.get('user')
        if isinstance(user, AnonymousUser):
            return # Ignore typing from anonymous users

        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'typing_indicator',
                'user': user.username,
                'is_typing': data.get('is_typing', False)
            }
        )

    async def handle_mark_read(self, data):
        """
        Handle marking messages as read.
        """
        user = self.scope.get('user')
        if isinstance(user, AnonymousUser):
            return

        message_id = data.get('message_id')
        if message_id:
            await self.mark_message_as_read(user, message_id)

    @database_sync_to_async
    def save_message(self, user, content, sender_type):
        """
        Save a chat message to the database.
        """
        try:
            session = ChatSession.objects.get(id=self.session_id)
            # Ensure the user is part of the session
            if user not in session.participants.all():
                logger.warning(f"User {user.id} not in session {self.session_id}. Adding.")
                session.participants.add(user)

            message = ChatMessage.objects.create(
                session=session,
                sender=user,
                content=content,
                sender_type=sender_type
            )
            return message
        except ChatSession.DoesNotExist:
            logger.error(f"Chat session not found: {self.session_id}")
            return None
        except Exception as e:
            logger.error(f"Error saving message for session {self.session_id}: {e}")
            return None

    @database_sync_to_async
    def mark_message_as_read(self, user, message_id):
        """
        Mark a specific message as read by the user.
        (This is a placeholder for a more complex read-status implementation)
        """
        try:
            message = ChatMessage.objects.get(id=message_id)
            # In a real system, you'd have a ManyToManyField for read receipts
            logger.info(f"User {user.username} marked message {message_id} as read.")
        except ChatMessage.DoesNotExist:
            logger.warning(f"Could not mark message as read, not found: {message_id}")

    # --- Handlers for messages from the channel layer ---

    async def chat_message(self, event):
        """
        Receive a message from the room group and send it to the WebSocket.
        This is now used for both user messages and AI responses.
        """
        await self.send(text_data=json.dumps({
            'type': 'message',
            'message': event['message'],
            'sender': event.get('sender', 'AI Assistant'),
            'sender_type': event.get('sender_type', 'ai')
        }))

    async def typing_indicator(self, event):
        """
        Receive a typing indicator from the group and forward it.
        """
        await self.send(text_data=json.dumps({
            'type': 'typing',
            'user': event['user'],
            'is_typing': event['is_typing']
        }))
    
    async def ai_response(self, event):
        """
        Handler for when an AI response is ready from the Celery task.
        The task will send a message to this group.
        """
        await self.send(text_data=json.dumps({
            'type': 'message',
            'message': event['response'],
            'sender': 'AI Assistant',
            'sender_type': 'ai',
            'model_used': event.get('model_used')
        }))

    async def send_error(self, message):
        """
        Send an error message to the client.
        """
        await self.send(text_data=json.dumps({
            'type': 'error',
            'message': message
        }))


class NotificationConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for real-time notifications.
    """
    
    async def connect(self):
        """
        Called when the websocket is handshaking as part of the connection process.
        """
        user = self.scope.get('user')
        if isinstance(user, AnonymousUser):
            await self.close()
            return
        
        self.user_id = user.id
        self.room_group_name = f'notifications_{self.user_id}'
        
        # Join room group
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        
        # Accept the connection
        await self.accept()
        
        # Send connection success message
        await self.send(text_data=json.dumps({
            'type': 'connection_established',
            'message': 'Connected to notifications'
        }))
    
    async def disconnect(self, close_code):
        """
        Called when the WebSocket closes for any reason.
        """
        # Leave room group only if we successfully joined it
        if hasattr(self, 'room_group_name'):
            await self.channel_layer.group_discard(
                self.room_group_name,
                self.channel_name
            )
    
    async def receive(self, text_data):
        """
        Handle incoming messages (for ping/pong or mark as read).
        """
        try:
            data = json.loads(text_data)
            message_type = data.get('type', 'ping')
            
            if message_type == 'ping':
                await self.send(text_data=json.dumps({
                    'type': 'pong'
                }))
            elif message_type == 'mark_read':
                # Handle marking notifications as read
                notification_id = data.get('notification_id')
                if notification_id:
                    await self.mark_notification_read(notification_id)
        
        except json.JSONDecodeError:
            pass  # Ignore invalid JSON
        except Exception as e:
            logger.error(f"Error handling notification WebSocket message: {e}")
    
    async def notification_message(self, event):
        """
        Called when we receive a notification from the room group.
        """
        await self.send(text_data=json.dumps({
            'type': 'notification',
            'notification': event['notification']
        }))
    
    @database_sync_to_async
    def mark_notification_read(self, notification_id):
        """
        Mark notification as read.
        """
        try:
            # This would mark a notification as read if we had a notification model
            # For now, it's a placeholder
            pass
        except Exception as e:
            logger.error(f"Error marking notification as read: {e}")


# Utility function to send notifications to users
async def send_notification_to_user(user_id, notification_data):
    """
    Send notification to a specific user via WebSocket.
    """
    from channels.layers import get_channel_layer
    
    channel_layer = get_channel_layer()
    await channel_layer.group_send(
        f'notifications_{user_id}',
        {
            'type': 'notification_message',
            'notification': notification_data
        }
    )
