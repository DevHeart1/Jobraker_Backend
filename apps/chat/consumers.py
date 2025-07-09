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
        
        # Save message to database
        message = await self.save_message(user, message_content)
        
        if message:
            # Send message to room group
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'chat_message',
                    'message': {
                        'id': message.id,
                        'content': message.content,
                        'sender': 'user',
                        'timestamp': message.created_at.isoformat(),
                        'user_id': user.id
                    }
                }
            )
            
            # Generate AI response
            await self.generate_ai_response(message)
    
    async def handle_typing_indicator(self, data):
        """
        Handle typing indicators.
        """
        user = self.scope.get('user')
        if isinstance(user, AnonymousUser):
            return
        
        is_typing = data.get('is_typing', False)
        
        # Send typing indicator to room group
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'typing_indicator',
                'is_typing': is_typing,
                'user_id': user.id
            }
        )
    
    async def handle_mark_read(self, data):
        """
        Handle mark messages as read.
        """
        user = self.scope.get('user')
        if isinstance(user, AnonymousUser):
            return
        
        message_id = data.get('message_id')
        if message_id:
            await self.mark_message_read(message_id)
    
    async def generate_ai_response(self, user_message):
        """
        Generate AI response to user message.
        """
        try:
            # Get session history
            session = await self.get_session()
            if not session:
                return
            
            # Get recent messages for context
            messages = await self.get_recent_messages(session)
            
            # Generate AI response
            openai_service = OpenAIService()
            ai_response = await database_sync_to_async(
                openai_service.generate_chat_response
            )(messages, session.user)
            
            if ai_response:
                # Save AI response to database
                ai_message = await self.save_ai_message(ai_response)
                
                if ai_message:
                    # Send AI response to room group
                    await self.channel_layer.group_send(
                        self.room_group_name,
                        {
                            'type': 'chat_message',
                            'message': {
                                'id': ai_message.id,
                                'content': ai_message.content,
                                'sender': 'assistant',
                                'timestamp': ai_message.created_at.isoformat(),
                                'user_id': None
                            }
                        }
                    )
        
        except Exception as e:
            logger.error(f"Error generating AI response: {e}")
            await self.send_error('Failed to generate AI response')
    
    async def chat_message(self, event):
        """
        Called when we receive a message from the room group.
        """
        await self.send(text_data=json.dumps({
            'type': 'message',
            'message': event['message']
        }))
    
    async def typing_indicator(self, event):
        """
        Called when we receive a typing indicator from the room group.
        """
        await self.send(text_data=json.dumps({
            'type': 'typing',
            'is_typing': event['is_typing'],
            'user_id': event['user_id']
        }))
    
    async def send_error(self, message):
        """
        Send error message to client.
        """
        await self.send(text_data=json.dumps({
            'type': 'error',
            'message': message
        }))
    
    @database_sync_to_async
    def get_session(self):
        """
        Get or create chat session.
        """
        try:
            user = self.scope.get('user')
            if isinstance(user, AnonymousUser):
                return None
            
            session, created = ChatSession.objects.get_or_create(
                id=self.session_id,
                defaults={'user': user}
            )
            return session
        except Exception as e:
            logger.error(f"Error getting session: {e}")
            return None
    
    @database_sync_to_async
    def save_message(self, user, content):
        """
        Save user message to database.
        """
        try:
            session = ChatSession.objects.get(id=self.session_id)
            message = ChatMessage.objects.create(
                session=session,
                content=content,
                sender='user'
            )
            return message
        except Exception as e:
            logger.error(f"Error saving message: {e}")
            return None
    
    @database_sync_to_async
    def save_ai_message(self, content):
        """
        Save AI message to database.
        """
        try:
            session = ChatSession.objects.get(id=self.session_id)
            message = ChatMessage.objects.create(
                session=session,
                content=content,
                sender='assistant'
            )
            return message
        except Exception as e:
            logger.error(f"Error saving AI message: {e}")
            return None
    
    @database_sync_to_async
    def get_recent_messages(self, session, limit=10):
        """
        Get recent messages for context.
        """
        try:
            messages = ChatMessage.objects.filter(
                session=session
            ).order_by('-created_at')[:limit]
            
            return [{
                'content': msg.content,
                'sender': msg.sender,
                'timestamp': msg.created_at.isoformat()
            } for msg in reversed(messages)]
        except Exception as e:
            logger.error(f"Error getting recent messages: {e}")
            return []
    
    @database_sync_to_async
    def mark_message_read(self, message_id):
        """
        Mark message as read.
        """
        try:
            ChatMessage.objects.filter(id=message_id).update(is_read=True)
        except Exception as e:
            logger.error(f"Error marking message as read: {e}")


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
        # Leave room group
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
