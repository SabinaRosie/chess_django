import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.utils import timezone
from .models import CallRoom, CallSignal, Conversation, ChatMessage

class CallConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.room_id = self.scope['url_route']['kwargs']['room_id']
        self.room_group_name = f'call_{self.room_id}'

        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        await self.accept()

        # 🔹 Send all buffered signals to the new joiner
        await self.send_buffered_signals()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    async def receive(self, text_data):
        data = json.loads(text_data)
        signal_type = data.get('type')
        payload = data.get('data')

        if signal_type == 'ping':
            await self.send(text_data=json.dumps({'type': 'pong'}))
            return

        # 🔹 Buffer all important signals
        if signal_type in ('offer', 'answer', 'candidate'):
            await self.buffer_signal(signal_type, payload)

        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'call_signal',
                'signal_type': signal_type,
                'data': payload,
                'sender_channel': self.channel_name
            }
        )

    async def call_signal(self, event):
        if self.channel_name != event['sender_channel']:
            await self.send(text_data=json.dumps({
                'type': event['signal_type'],
                'data': event['data']
            }))

    @database_sync_to_async
    def buffer_signal(self, signal_type, data):
        try:
            room = CallRoom.objects.get(room_id=self.room_id)
            # Update room fields for quick access
            if signal_type == 'offer':
                room.offer_sdp = data
                room.save()
            elif signal_type == 'answer':
                room.answer_sdp = data
                room.save()
            
            # Save to CallSignal for full history (especially candidates)
            CallSignal.objects.create(
                room=room,
                sender=self.scope['user'],
                signal_type=signal_type,
                data=data
            )
        except Exception as e:
            print(f"Error buffering signal: {e}")

    async def send_buffered_signals(self):
        signals = await self.get_buffered_signals()
        for signal in signals:
            # Don't send back to the user who originally sent it
            if signal['sender_id'] != self.scope['user'].id:
                await self.send(text_data=json.dumps({
                    'type': signal['type'],
                    'data': signal['data']
                }))

    @database_sync_to_async
    def get_buffered_signals(self):
        try:
            room = CallRoom.objects.get(room_id=self.room_id)
            signals = CallSignal.objects.filter(room=room).order_by('created_at')
            return [{
                'type': s.signal_type,
                'data': s.data,
                'sender_id': s.sender_id
            } for s in signals]
        except Exception:
            return []

class NotificationConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        if self.scope["user"].is_anonymous:
            await self.close()
            return
            
        self.user_group_name = f'user_{self.scope["user"].id}'.replace(' ', '_')
        await self.channel_layer.group_add(
            self.user_group_name,
            self.channel_name
        )
        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, 'user_group_name'):
            await self.channel_layer.group_discard(
                self.user_group_name,
                self.channel_name
            )

    async def incoming_call(self, event):
        await self.send(text_data=json.dumps({
            'type': 'incoming_call',
            'data': event['data']
        }))

    async def call_cancelled(self, event):
        await self.send(text_data=json.dumps({
            'type': 'call_cancelled',
            'data': event['data']
        }))

    async def chat_notification(self, event):
        await self.send(text_data=json.dumps({
            'type': 'chat_notification',
            'data': event['data']
        }))

class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.conversation_id = self.scope['url_route']['kwargs']['conversation_id']
        self.room_group_name = f'chat_{self.conversation_id}'
        
        user = self.scope.get('user')
        if not user or not user.is_authenticated:
            await self.close()
            return
            
        is_participant = await self.check_participant(user)
        if not is_participant:
            await self.close()
            return

        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
        except Exception:
            return

        message_type = data.get('type')
        
        if message_type == 'ping':
            await self.send(text_data=json.dumps({'type': 'pong'}))
            return
            
        if message_type == 'message':
            content = data.get('content')
            msg_type = data.get('message_type', 'text')
            
            # Save to DB first
            msg = await self.save_message(content, msg_type)
            
            # Broadcast to group
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'chat_message_relay',
                    'message': {
                        'id': msg.id,
                        'sender_id': msg.sender.id,
                        'content': msg.content,
                        'message_type': msg.message_type,
                        'status': msg.status,
                        'created_at': str(msg.created_at),
                    },
                    'sender_channel': self.channel_name
                }
            )

            # Notify the other participant via NotificationConsumer for background/global alerts
            other_user = await self.get_other_participant()
            if other_user:
                await self.channel_layer.group_send(
                    f'user_{other_user.id}'.replace(' ', '_'),
                    {
                        'type': 'chat_notification',
                        'data': {
                            'sender': self.scope['user'].username,
                            'content': content[:50],
                            'conversation_id': str(self.conversation_id)
                        }
                    }
                )

        elif message_type == 'typing':
            is_typing = data.get('is_typing', False)
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'user_typing',
                    'user_id': self.scope['user'].id,
                    'is_typing': is_typing,
                    'sender_channel': self.channel_name
                }
            )
            
        elif message_type == 'read':
            await self.mark_messages_seen()
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'messages_seen',
                    'user_id': self.scope['user'].id,
                    'sender_channel': self.channel_name
                }
            )

    async def chat_message_relay(self, event):
        if self.channel_name != event['sender_channel']:
            await self.send(text_data=json.dumps({
                'type': 'message',
                'message': event['message']
            }))

    async def user_typing(self, event):
        if self.channel_name != event['sender_channel']:
            await self.send(text_data=json.dumps({
                'type': 'typing',
                'user_id': event['user_id'],
                'is_typing': event['is_typing']
            }))

    async def messages_seen(self, event):
        if self.channel_name != event['sender_channel']:
            await self.send(text_data=json.dumps({
                'type': 'seen',
                'user_id': event['user_id']
            }))

    @database_sync_to_async
    def check_participant(self, user):
        return Conversation.objects.filter(id=self.conversation_id, participants=user).exists()

    @database_sync_to_async
    def get_other_participant(self):
        conv = Conversation.objects.get(id=self.conversation_id)
        return conv.participants.exclude(id=self.scope['user'].id).first()

    @database_sync_to_async
    def save_message(self, content, msg_type):
        conv = Conversation.objects.get(id=self.conversation_id)
        msg = ChatMessage.objects.create(
            conversation=conv,
            sender=self.scope['user'],
            content=content,
            message_type=msg_type,
            status='sent'
        )
        conv.last_message_content = content
        conv.last_message_time = timezone.now()
        conv.save()
        return msg

    @database_sync_to_async
    def mark_messages_seen(self):
        ChatMessage.objects.filter(
            conversation_id=self.conversation_id,
            status__in=['sent', 'delivered']
        ).exclude(sender=self.scope['user']).update(status='seen')
