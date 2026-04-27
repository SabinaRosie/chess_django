import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from .models import CallRoom, CallSignal

class CallConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.room_id = self.scope['url_route']['kwargs']['room_id']
        self.room_group_name = f'call_{self.room_id}'

        # Join room group
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )

        await self.accept()

    async def disconnect(self, close_code):
        # Leave room group
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    # Receive message from WebSocket
    async def receive(self, text_data):
        data = json.loads(text_data)
        signal_type = data.get('type')
        payload = data.get('data')

        # Broadcast to room group
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'call_signal',
                'signal_type': signal_type,
                'data': payload,
                'sender_channel': self.channel_name
            }
        )

    # Receive message from room group
    async def call_signal(self, event):
        # Don't send the message back to the sender
        if self.channel_name != event['sender_channel']:
            await self.send(text_data=json.dumps({
                'type': event['signal_type'],
                'data': event['data']
            }))

class NotificationConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        if self.scope["user"].is_anonymous:
            await self.close()
            return
            
        self.user_group_name = f'user_{self.scope["user"].id}'
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
