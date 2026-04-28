import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from .models import CallRoom, CallSignal

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
