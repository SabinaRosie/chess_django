from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.db.models import Q
from .models import Conversation, ChatMessage
from django.contrib.auth.models import User
from django.utils import timezone

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_conversations(request):
    """List all conversations for the authenticated user."""
    conversations = request.user.conversations.all().order_by('-last_message_time')
    data = []
    for conv in conversations:
        other_user = conv.participants.exclude(id=request.user.id).first()
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
            'unread_count': conv.messages.filter(status__in=['sent', 'delivered']).exclude(sender=request.user).count()
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
    
    messages = conversation.messages.filter(is_deleted=False)
    if before:
        messages = messages.filter(created_at__lt=before)
    
    # We order by -created_at for fetching, but return them in ascending order for the UI
    messages = messages.order_by('-created_at')[:limit]
    
    data = []
    for msg in reversed(messages):
        data.append({
            'id': msg.id,
            'sender_id': msg.sender.id,
            'content': msg.content,
            'message_type': msg.message_type,
            'status': msg.status,
            'created_at': msg.created_at,
        })
    
    return Response({
        'messages': data,
        'has_more': len(messages) == limit
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

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def mark_as_seen(request, conversation_id):
    """Mark all messages from the other user in this conversation as seen."""
    ChatMessage.objects.filter(
        conversation_id=conversation_id,
        status__in=['sent', 'delivered']
    ).exclude(sender=request.user).update(status='seen')
    
    return Response({"status": "success"})
