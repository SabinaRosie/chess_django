from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.db.models import Q
from .models import Conversation, ChatMessage, MessageReaction
from django.contrib.auth.models import User
from django.utils import timezone
from django.db.models import Q, Count
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from .fcm_utils import send_push_notification

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_conversations(request):
    """List all conversations for the authenticated user."""
    conversations = request.user.conversations.annotate(
        unread=Count(
            'messages',
            filter=Q(messages__status__in=['sent', 'delivered']) & ~Q(messages__sender=request.user)
        )
    ).prefetch_related('participants').order_by('-last_message_time')
    
    data = []
    for conv in conversations:
        # Since we prefetched participants, this is now efficient
        participants = list(conv.participants.all())
        other_user = next((u for u in participants if u.id != request.user.id), None)
        
        if not other_user:
            continue
            
        data.append({
            'id': str(conv.id),
            'other_user': {
                'id': other_user.id,
                'username': other_user.username,
            },
            'last_message': conv.last_message_content,
            'last_message_time': conv.last_message_time,
            'unread_count': conv.unread
        })
    return Response(data)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_messages(request, conversation_id):
    """Fetch messages for a conversation with cursor-based pagination."""
    try:
        conversation = Conversation.objects.get(id=conversation_id, participants=request.user)
    except Conversation.DoesNotExist:
        return Response({"error": "Conversation not found"}, status=404)

    # Simple cursor-based pagination using 'before' timestamp
    before = request.query_params.get('before')
    limit = int(request.query_params.get('limit', 20))
    
    messages = conversation.messages.all()
    if before:
        messages = messages.filter(created_at__lt=before)
    
    # We order by -created_at for fetching, but return them in ascending order for the UI
    # Convert QuerySet to list before reversing to avoid re-querying or issues with slices
    messages_list = list(messages.order_by('-created_at').prefetch_related('reactions')[:limit])
    
    data = []
    for msg in reversed(messages_list):
        # Aggregate reactions for this message
        reactions_data = []
        emoji_groups = msg.reactions.values('emoji').annotate(count=Count('emoji'))
        for group in emoji_groups:
            user_ids = list(msg.reactions.filter(emoji=group['emoji']).values_list('user_id', flat=True))
            reactions_data.append({
                'emoji': group['emoji'],
                'count': group['count'],
                'userIds': user_ids
            })

        reply_data = None
        if msg.replied_to:
            reply_data = {
                'id': msg.replied_to.id,
                'content': msg.replied_to.content if not msg.replied_to.is_deleted else "Message deleted",
                'sender_id': msg.replied_to.sender.id,
            }

        data.append({
            'id': msg.id,
            'sender_id': msg.sender.id,
            'content': msg.content,
            'message_type': msg.message_type,
            'status': msg.status,
            'created_at': msg.created_at,
            'reactions': reactions_data,
            'replied_to': reply_data,
            'is_deleted': msg.is_deleted,
            'is_forwarded': msg.is_forwarded,
        })
    
    return Response({
        'messages': data,
        'has_more': len(messages_list) == limit
    })

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def start_conversation(request):
    """Start or get a conversation with another user."""
    other_user_id = request.data.get('user_id')
    if not other_user_id:
        return Response({"error": "user_id required"}, status=400)
        
    try:
        other_user = User.objects.get(id=other_user_id)
    except User.DoesNotExist:
        return Response({"error": "User not found"}, status=404)

    if other_user == request.user:
        return Response({"error": "Cannot chat with yourself"}, status=400)

    # Check if conversation already exists between these two users
    conversation = Conversation.objects.filter(participants=request.user).filter(participants=other_user).first()
    
    if not conversation:
        conversation = Conversation.objects.create()
        conversation.participants.add(request.user, other_user)
        conversation.save()
        
    return Response({
        'id': str(conversation.id),
        'other_user': {
            'id': other_user.id,
            'username': other_user.username,
        }
    })

@api_view(['POST', 'DELETE'])
@permission_classes([IsAuthenticated])
def toggle_reaction(request, message_id):
    """Add or remove a reaction from a message."""
    try:
        message = ChatMessage.objects.get(id=message_id)
        # Check if user is participant in the conversation
        if not message.conversation.participants.filter(id=request.user.id).exists():
            return Response({"error": "Unauthorized"}, status=403)
        
        if message.is_deleted:
            return Response({"error": "Cannot react to deleted message"}, status=400)
            
    except ChatMessage.DoesNotExist:
        return Response({"error": "Message not found"}, status=404)

    emoji = request.data.get('emoji')
    if not emoji:
        return Response({"error": "emoji required"}, status=400)

    reaction_deleted = False
    created = False
    if request.method == 'POST':
        # Add reaction (toggle behavior is handled by frontend, but we ensure uniqueness here)
        reaction, created = MessageReaction.objects.get_or_create(
            message=message,
            user=request.user,
            emoji=emoji
        )
    elif request.method == 'DELETE':
        # Remove reaction
        reactions = MessageReaction.objects.filter(
            message=message,
            user=request.user,
            emoji=emoji
        )
        reaction_deleted = reactions.exists()
        if reaction_deleted:
            reactions.delete()

    # Broadcast update via WebSockets immediately
    broadcast_reaction_update(message)

    # Then send slower FCM push notifications
    if request.method == 'POST' and created:
        send_reaction_notification(message, request.user, emoji, "added")
    elif request.method == 'DELETE' and reaction_deleted:
        send_reaction_notification(message, request.user, emoji, "removed")
    
    return Response({"status": "success"})

def broadcast_reaction_update(message):
    """Helper to broadcast reaction changes via WebSockets."""
    channel_layer = get_channel_layer()
    
    reactions_data = []
    emoji_groups = message.reactions.values('emoji').annotate(count=Count('emoji'))
    for group in emoji_groups:
        user_ids = list(message.reactions.filter(emoji=group['emoji']).values_list('user_id', flat=True))
        reactions_data.append({
            'emoji': group['emoji'],
            'count': group['count'],
            'userIds': user_ids
        })
    
    async_to_sync(channel_layer.group_send)(
        f'chat_{message.conversation.id}',
        {
            'type': 'message_reaction_updated',
            'data': {
                'messageId': message.id,
                'reactions': reactions_data
            }
        }
    )

def send_reaction_notification(message, sender, emoji, action):
    """Helper to send FCM for reactions."""
    from .consumers import ChatConsumer
    other_participants = message.conversation.participants.exclude(id=sender.id)
    title = sender.username
    if action == "added":
        body = f"Reacted {emoji} to a message"
    else:
        body = f"Removed reaction {emoji} from a message"

    for user in other_participants:
        # Check if user is active in this chat room to suppress FCM
        active_in_room = ChatConsumer.active_users.get(str(message.conversation.id), set())
        if user.id in active_in_room:
            print(f"DEBUG: Skipping reaction FCM for {user.username} (active in chat)")
            continue

        try:
            send_push_notification(
                user,
                title=title,
                body=body,
                data={
                    'type': 'chat',
                    'chat_room_id': str(message.conversation.id),
                    'sender_id': str(sender.id),
                    'sender_name': sender.username,
                    'is_reaction': 'true',
                    'emoji': emoji
                }
            )
        except Exception as e:
            print(f"DEBUG: Reaction notification failed for {user.username}: {e}")

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def mark_as_seen(request, conversation_id):
    """Mark all messages from the other user in this conversation as seen."""
    ChatMessage.objects.filter(
        conversation_id=conversation_id,
        status__in=['sent', 'delivered']
    ).exclude(sender=request.user).update(status='seen')
    
    return Response({"status": "success"})

@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def delete_message(request, message_id):
    """Soft delete a message."""
    try:
        message = ChatMessage.objects.get(id=message_id, sender=request.user)
        message.is_deleted = True
        message.content = "This message was deleted"
        message.save()
        
        # Broadcast deletion
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            f'chat_{message.conversation.id}',
            {
                'type': 'message_deleted',
                'data': {
                    'messageId': message.id
                }
            }
        )
        
        return Response({"status": "success"})
    except ChatMessage.DoesNotExist:
        return Response({"error": "Message not found or unauthorized"}, status=404)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def forward_message(request):
    """Forward a message to another conversation."""
    message_id = request.data.get('message_id')
    target_conversation_id = request.data.get('conversation_id')
    
    if not message_id or not target_conversation_id:
        return Response({"error": "message_id and conversation_id required"}, status=400)
        
    try:
        original_msg = ChatMessage.objects.get(id=message_id)
        # Verify user is a participant in the original message's conversation
        if not original_msg.conversation.participants.filter(id=request.user.id).exists():
            return Response({"error": "Unauthorized to forward this message"}, status=403)
            
        target_conv = Conversation.objects.get(id=target_conversation_id, participants=request.user)
    except (ChatMessage.DoesNotExist, Conversation.DoesNotExist):
        return Response({"error": "Message or target conversation not found"}, status=404)

    # Create new message in target conversation
    new_msg = ChatMessage.objects.create(
        conversation=target_conv,
        sender=request.user,
        content=original_msg.content,
        message_type=original_msg.message_type,
        is_forwarded=True,
        is_deleted=False
    )
    
    target_conv.last_message_content = new_msg.content
    target_conv.last_message_time = timezone.now()
    target_conv.save()

    # Broadcast to target group
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        f'chat_{target_conv.id}',
        {
            'type': 'chat_message_relay',
            'message': {
                'id': new_msg.id,
                'sender_id': new_msg.sender.id,
                'content': new_msg.content,
                'message_type': new_msg.message_type,
                'status': new_msg.status,
                'created_at': new_msg.created_at.isoformat(),
                'replied_to': None,
                'is_forwarded': True,
                'is_deleted': False,
            },
            'sender_channel': 'api_request'
        }
    )

    # Send Push Notification to other user
    other_user = target_conv.participants.exclude(id=request.user.id).first()
    if other_user:
        # Also send global notification via WebSocket for unread badges
        try:
            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                f'user_{other_user.id}'.replace(' ', '_'),
                {
                    'type': 'chat_notification',
                    'data': {
                        'sender': request.user.username,
                        'content': f"Forwarded: {new_msg.content[:50]}",
                        'conversation_id': str(target_conv.id)
                    }
                }
            )
        except Exception as e:
            print(f"DEBUG: Global notification failed: {e}")

        # Check if user is active in this chat room to suppress FCM
        from .consumers import ChatConsumer
        active_in_room = ChatConsumer.active_users.get(str(target_conv.id), set())
        if other_user.id not in active_in_room:
            try:
                send_push_notification(
                    other_user,
                    title=request.user.username,
                    body="Forwarded a message to you",
                    data={
                        'type': 'chat',
                        'chat_room_id': str(target_conv.id),
                        'sender_id': str(request.user.id),
                        'sender_name': request.user.username,
                        'is_forwarded': 'true'
                    }
                )
            except Exception as e:
                print(f"DEBUG: Notification failed: {e}")
        else:
            print(f"DEBUG: Skipping forward FCM for {other_user.username} as they are active in chat.")

    return Response({"status": "success", "message_id": new_msg.id})
