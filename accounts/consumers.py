import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.utils import timezone
from .models import CallRoom, CallSignal, Conversation, ChatMessage
from .fcm_utils import send_push_notification

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
    # Global tracking of online users: set of user_ids
    online_users = set()

    async def connect(self):
        if self.scope["user"].is_anonymous:
            await self.close()
            return
            
        self.user_id = self.scope["user"].id
        self.user_group_name = f'user_{self.user_id}'.replace(' ', '_')
        
        await self.channel_layer.group_add(
            self.user_group_name,
            self.channel_name
        )
        
        # Track globally online
        NotificationConsumer.online_users.add(self.user_id)
        
        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, 'user_group_name'):
            await self.channel_layer.group_discard(
                self.user_group_name,
                self.channel_name
            )
            
        # Untrack globally online
        if hasattr(self, 'user_id'):
            NotificationConsumer.online_users.discard(self.user_id)

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

    async def game_invitation(self, event):
        await self.send(text_data=json.dumps({
            'type': 'game_invitation',
            'data': event['data']
        }))

    async def invitation_accepted(self, event):
        await self.send(text_data=json.dumps({
            'type': 'invitation_accepted',
            'data': event['data']
        }))

    async def invitation_declined(self, event):
        await self.send(text_data=json.dumps({
            'type': 'invitation_declined',
            'data': event['data']
        }))
    
    async def invitation_cancelled(self, event):
        await self.send(text_data=json.dumps({
            'type': 'invitation_cancelled',
            'data': event['data']
        }))

class ChatConsumer(AsyncWebsocketConsumer):
    # In-memory tracking of active users in each chat room
    # conversation_id -> set of user_ids
    active_users = {}

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

        self.user_id = user.id

        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )

        # Track active user
        conv_id_str = str(self.conversation_id)
        if conv_id_str not in ChatConsumer.active_users:
            ChatConsumer.active_users[conv_id_str] = set()
        ChatConsumer.active_users[conv_id_str].add(self.user_id)

        await self.accept()
        print(f"WS CONNECT: User {self.user_id} joined room {self.room_group_name}")

    async def disconnect(self, close_code):
        # Leave room group
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

        # Untrack active user
        conv_id_str = str(self.conversation_id)
        if hasattr(self, 'user_id') and conv_id_str in ChatConsumer.active_users:
            ChatConsumer.active_users[conv_id_str].discard(self.user_id)
            if not ChatConsumer.active_users[conv_id_str]:
                del ChatConsumer.active_users[conv_id_str]

        print(f"WS DISCONNECT: User {getattr(self, 'user_id', 'unknown')} left room {self.room_group_name}")

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
            reply_to_id = data.get('replied_to_id')
            print(f"DEBUG: Receiving message from {self.scope['user'].username}: {content} (Reply to: {reply_to_id})")
            
            # 1. Save to DB first
            msg = await self.save_message(content, msg_type, reply_to_id)
            
            # 2. IMMEDIATELY send FCM Push Notification (Synchronous-like via sync_to_async)
            # Fetch receiver FCM token fresh from DB every time (handled inside send_push_notification)
            other_user = await self.get_other_participant()
            if other_user:
                is_reply = reply_to_id is not None
                active_in_room = ChatConsumer.active_users.get(str(self.conversation_id), set())
                if other_user.id not in active_in_room:
                    # We don't await this to keep the WS responsive, but it starts immediately
                    import asyncio
                    asyncio.create_task(self.send_fcm_notification(other_user, content, is_reply=is_reply))
                else:
                    print(f"DEBUG: Skipping FCM for {other_user.username} as they are active in chat.")

            # 3. Broadcast to group
            reply_data = None
            if msg.replied_to:
                reply_data = {
                    'id': msg.replied_to.id,
                    'content': msg.replied_to.content if not msg.replied_to.is_deleted else "Message deleted",
                    'sender_id': msg.replied_to.sender.id,
                }

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
                        'replied_to': reply_data,
                        'is_forwarded': msg.is_forwarded,
                        'is_deleted': msg.is_deleted,
                    },
                    'sender_channel': self.channel_name
                }
            )

            # 4. Notify the other participant via NotificationConsumer for unread badges
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

    async def send_fcm_notification(self, other_user, content, is_reply=False):
        print(f"DEBUG: Entering send_fcm_notification for user {other_user.username}...")
        try:
            from asgiref.sync import sync_to_async
            
            title = self.scope['user'].username
            if is_reply:
                body = f"Replied to a message: {content[:40]}"
            else:
                body = content[:100]

            await sync_to_async(send_push_notification, thread_sensitive=False)(
                other_user,
                title=title,
                body=body,
                data={
                    'type': 'chat',
                    'chat_room_id': str(self.conversation_id),
                    'sender_id': str(self.scope['user'].id),
                    'sender_name': self.scope['user'].username,
                    'is_reply': 'true' if is_reply else 'false'
                }
            )
            print(f"DEBUG: Finished calling send_push_notification for {other_user.username}")
        except Exception as e:
            print(f"DEBUG: ERROR in send_fcm_notification: {str(e)}")
            import traceback
            traceback.print_exc()

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

    async def message_reaction_updated(self, event):
        await self.send(text_data=json.dumps({
            'type': 'reaction_updated',
            'data': event['data']
        }))

    async def message_deleted(self, event):
        await self.send(text_data=json.dumps({
            'type': 'message_deleted',
            'data': event['data']
        }))

    @database_sync_to_async
    def check_participant(self, user):
        return Conversation.objects.filter(id=self.conversation_id, participants=user).exists()

    @database_sync_to_async
    def get_other_participant(self):
        conv = Conversation.objects.get(id=self.conversation_id)
        return conv.participants.exclude(id=self.scope['user'].id).first()

    @database_sync_to_async
    def save_message(self, content, msg_type, reply_to_id=None):
        conv = Conversation.objects.get(id=self.conversation_id)
        replied_to = None
        if reply_to_id:
            try:
                replied_to = ChatMessage.objects.get(id=reply_to_id)
            except ChatMessage.DoesNotExist:
                pass

        msg = ChatMessage.objects.create(
            conversation_id=self.conversation_id,
            sender=self.scope['user'],
            content=content,
            message_type=msg_type,
            replied_to=replied_to,
            is_forwarded=False,
            is_deleted=False
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


class GameConsumer(AsyncWebsocketConsumer):
    # Track connected players per game: game_id -> {user_id: channel_name}
    game_sessions = {}
    # Track who has ever joined the game during this server instance: game_id -> set of user_ids
    joined_players_history = {}

    async def connect(self):
        if self.scope["user"].is_anonymous:
            print(f"GAME DEBUG: REJECTED. Anonymous user attempting to connect to game {self.scope['url_route']['kwargs']['game_id']}")
            await self.close()
            return
            
        self.game_id = self.scope['url_route']['kwargs']['game_id']
        self.room_group_name = f'game_{self.game_id}'
        self.user_id = self.scope['user'].id
        
        print(f"GAME DEBUG: Attempting connect. Game: {self.game_id}, User: {self.user_id}")

        # Verify player is part of the game
        is_player = await self.check_player()
        if not is_player:
            print(f"GAME DEBUG: REJECTED. User {self.user_id} not in game {self.game_id}")
            await self.close()
            return

        # Join room group
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )

        # Check if user was already in history (true reconnection)
        is_reconnect = False
        if self.game_id in GameConsumer.joined_players_history and self.user_id in GameConsumer.joined_players_history[self.game_id]:
            is_reconnect = True
        
        # Update history
        if self.game_id not in GameConsumer.joined_players_history:
            GameConsumer.joined_players_history[self.game_id] = set()
        GameConsumer.joined_players_history[self.game_id].add(self.user_id)

        # Register session
        if self.game_id not in GameConsumer.game_sessions:
            GameConsumer.game_sessions[self.game_id] = {}
        GameConsumer.game_sessions[self.game_id][self.user_id] = self.channel_name

        await self.accept()
        print(f"GAME CONNECT: User {self.user_id} joined game {self.game_id} (Reconnect: {is_reconnect})")

        # ... send sync ...
        game_data = await self.get_game_state_data()
        await self.send(text_data=json.dumps({
            'type': 'game_sync',
            'data': game_data
        }))

        # Notify opponent of reconnection ONLY if they were previously in the session
        if is_reconnect:
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'player_reconnected',
                    'user_id': self.user_id
                }
            )

        # If both players are now connected, signal game start to the GROUP
        if len(GameConsumer.game_sessions[self.game_id]) == 2:
            print(f"GAME START: Both players connected to {self.game_id}. Sending game_start signal.")
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'game_start',
                    'data': {
                        'message': 'Both players are ready!'
                    }
                }
            )
        else:
            print(f"GAME CONNECT: Waiting for opponent. Current players: {len(GameConsumer.game_sessions[self.game_id])}")

    async def disconnect(self, close_code):
        # Leave room group
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

        # Unregister session
        if hasattr(self, 'game_id') and self.game_id in GameConsumer.game_sessions:
            if self.user_id in GameConsumer.game_sessions[self.game_id]:
                del GameConsumer.game_sessions[self.game_id][self.user_id]
            if not GameConsumer.game_sessions[self.game_id]:
                del GameConsumer.game_sessions[self.game_id]

        # Notify opponent of disconnection/quit
        game_data = await self.get_game_state_data()
        if game_data['status'] == 'active':
            # Auto-resign the quitter
            opponent_id = await self.get_opponent_id()
            username = self.scope['user'].username
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'game_over',
                    'reason': 'opponent_quit',
                    'winner_id': opponent_id,
                    'loser_id': self.user_id,
                    'loser_username': username
                }
            )
            color = await self.get_color()
            await self.end_game('black_win' if color == 'white' else 'white_win')
        else:
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'player_disconnected',
                    'user_id': self.user_id
                }
            )
        print(f"GAME DISCONNECT: User {getattr(self, 'user_id', 'unknown')} left game {getattr(self, 'game_id', 'unknown')} (Code: {close_code})")

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
        except:
            return
        action = data.get('action')

        if action == 'move':
            # 🔹 Turn Validation
            game_data = await self.get_game_state_data()
            current_fen = game_data['fen']
            # Simple FEN check: ' w ' means white to move, ' b ' means black to move
            is_white_turn = ' w ' in current_fen
            color = await self.get_color()
            
            if (is_white_turn and color != 'white') or (not is_white_turn and color != 'black'):
                print(f"GAME DEBUG: REJECTED MOVE. Not {color}'s turn. FEN: {current_fen}")
                return

            # Broadcast move to opponent
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'game_move',
                    'move': data.get('move'),
                    'fen': data.get('fen'),
                    'sender_id': self.user_id
                }
            )
            # Update DB state
            await self.update_game_state(data.get('fen'), data.get('move'))

        elif action == 'ping':
            await self.send(text_data=json.dumps({'type': 'pong'}))

        elif action == 'resign':
            opponent_id = await self.get_opponent_id()
            username = self.scope['user'].username
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'game_over',
                    'reason': 'resignation',
                    'winner_id': opponent_id,
                    'loser_id': self.user_id,
                    'loser_username': username
                }
            )
            color = await self.get_color()
            await self.end_game('black_win' if color == 'white' else 'white_win')

        elif action == 'offer_draw':
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'draw_offered_relay',
                    'sender_id': self.user_id,
                    'username': self.scope['user'].username
                }
            )

        elif action == 'decline_draw':
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'draw_declined_relay',
                    'sender_id': self.user_id
                }
            )

        elif action == 'accept_draw':
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'game_over',
                    'reason': 'draw_accepted'
                }
            )
            await self.end_game('draw')

    async def game_move(self, event):
        if self.user_id != event['sender_id']:
            await self.send(text_data=json.dumps({
                'type': 'move',
                'move': event['move'],
                'fen': event['fen']
            }))

    async def game_over(self, event):
        await self.send(text_data=json.dumps({
            'type': 'game_over',
            'reason': event.get('reason'),
            'winner_id': event.get('winner_id'),
            'loser_username': event.get('loser_username')
        }))

    async def draw_offered_relay(self, event):
        if self.user_id != event['sender_id']:
            await self.send(text_data=json.dumps({
                'type': 'draw_offered',
                'username': event.get('username')
            }))

    async def draw_declined_relay(self, event):
        if self.user_id != event['sender_id']:
            await self.send(text_data=json.dumps({
                'type': 'draw_declined'
            }))

    async def player_disconnected(self, event):
        if self.user_id != event['user_id']:
            await self.send(text_data=json.dumps({
                'type': 'opponent_disconnected'
            }))

    async def player_reconnected(self, event):
        if self.user_id != event['user_id']:
            await self.send(text_data=json.dumps({
                'type': 'player_reconnected'
            }))

    async def game_start(self, event):
        """Handler for game_start group message."""
        await self.send(text_data=json.dumps({
            'type': 'game_start',
            'data': event['data']
        }))

    @database_sync_to_async
    def check_player(self):
        try:
            from .models import ChessGame
            game = ChessGame.objects.get(id=self.game_id)
            return game.white_player_id == self.user_id or game.black_player_id == self.user_id
        except:
            return False

    @database_sync_to_async
    def get_opponent_id(self):
        from .models import ChessGame
        game = ChessGame.objects.get(id=self.game_id)
        return game.black_player_id if game.white_player_id == self.user_id else game.white_player_id

    @database_sync_to_async
    def get_color(self):
        from .models import ChessGame
        game = ChessGame.objects.get(id=self.game_id)
        return 'white' if game.white_player_id == self.user_id else 'black'

    @database_sync_to_async
    def update_game_state(self, fen, move):
        from .models import ChessGame
        game = ChessGame.objects.get(id=self.game_id)
        game.fen = fen
        game.pgn += f" {move}"
        game.save()

    @database_sync_to_async
    def get_game_state_data(self):
        from .models import ChessGame
        game = ChessGame.objects.get(id=self.game_id)
        
        opponent_id = game.black_player_id if game.white_player_id == self.user_id else game.white_player_id
        is_opponent_online = False
        if self.game_id in GameConsumer.game_sessions:
            is_opponent_online = opponent_id in GameConsumer.game_sessions[self.game_id]
            
        return {
            'fen': game.fen,
            'status': game.status,
            'pgn': game.pgn,
            'white_player_id': game.white_player_id,
            'black_player_id': game.black_player_id,
            'is_opponent_online': is_opponent_online,
        }

    @database_sync_to_async
    def end_game(self, status):
        from .models import ChessGame
        game = ChessGame.objects.get(id=self.game_id)
        game.status = status
        game.save()
