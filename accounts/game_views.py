from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.contrib.auth.models import User
from django.utils import timezone
from django.db.models import Q
from .models import GameInvitation, ChessGame, FCMToken
from .fcm_utils import send_push_notification
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
import random

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_users(request):
    """List all users except the current one, with online status."""
    users = User.objects.exclude(id=request.user.id)
    # For now, let's just return basic info. If profile photo exists, use it.
    from .consumers import NotificationConsumer
    
    data = []
    for user in users:
        # Check if user is truly connected to the Notification WS
        is_online = user.id in NotificationConsumer.online_users
        
        data.append({
            'id': user.id,
            'username': user.username,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'is_online': is_online,
            'photo_url': getattr(user, 'profile_photo_url', None),
        })
    return Response(data)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def send_invitation(request):
    """Create a game invitation and notify the receiver."""
    receiver_id = request.data.get('receiver_id')
    try:
        receiver = User.objects.get(id=receiver_id)
    except User.DoesNotExist:
        return Response({"error": "User not found"}, status=404)

    # Cancel any existing pending invitations from this sender to this receiver
    GameInvitation.objects.filter(sender=request.user, receiver=receiver, status='pending').update(status='cancelled')

    invitation = GameInvitation.objects.create(
        sender=request.user,
        receiver=receiver,
        status='pending'
    )

    # 1. Send WebSocket event to receiver's global user group
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        f'user_{receiver.id}'.replace(' ', '_'),
        {
            'type': 'game_invitation',
            'data': {
                'invitation_id': invitation.id,
                'sender_id': request.user.id,
                'sender_username': request.user.username,
                'created_at': invitation.created_at.isoformat(),
            }
        }
    )

    # 2. Send FCM Push Notification (AFTER record is saved)
    try:
        send_push_notification(
            receiver,
            title=request.user.username,
            body="Invited you to play chess!",
            data={
                'type': 'game_invitation',
                'invitation_id': str(invitation.id),
                'sender_id': str(request.user.id),
                'sender_name': request.user.username,
            }
        )
    except Exception as e:
        print(f"DEBUG: Invitation FCM failed: {e}")

    return Response({
        "status": "success",
        "invitation_id": invitation.id
    })

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def respond_invitation(request):
    """Accept or decline a game invitation."""
    invitation_id = request.data.get('invitation_id')
    response_status = request.data.get('status') # 'accepted' or 'declined'

    try:
        invitation = GameInvitation.objects.get(id=invitation_id, receiver=request.user)
    except GameInvitation.DoesNotExist:
        return Response({"error": "Invitation not found"}, status=404)

    if invitation.status != 'pending':
        return Response({"error": "Invitation already handled"}, status=400)

    if response_status == 'accepted':
        invitation.status = 'accepted'
        invitation.save()

        # Determine colors (sender white, receiver black as per requirements)
        game = ChessGame.objects.create(
            white_player=invitation.sender,
            black_player=invitation.receiver,
            status='active'
        )

        # Notify BOTH players via WebSocket to start the game
        channel_layer = get_channel_layer()
        # Notify Sender
        async_to_sync(channel_layer.group_send)(
            f'user_{invitation.sender.id}'.replace(' ', '_'),
            {
                'type': 'invitation_accepted',
                'data': {
                    'game_id': str(game.id),
                    'opponent_id': request.user.id,
                    'opponent_username': request.user.username,
                    'color': 'white'
                }
            }
        )
        # Notify Receiver (Self)
        async_to_sync(channel_layer.group_send)(
            f'user_{request.user.id}'.replace(' ', '_'),
            {
                'type': 'invitation_accepted',
                'data': {
                    'game_id': str(game.id),
                    'opponent_id': invitation.sender.id,
                    'opponent_username': invitation.sender.username,
                    'color': 'black'
                }
            }
        )

        return Response({"status": "accepted", "game_id": str(game.id)})

    elif response_status == 'declined':
        invitation.status = 'declined'
        invitation.save()

        # Notify Sender via WebSocket
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            f'user_{invitation.sender.id}'.replace(' ', '_'),
            {
                'type': 'invitation_declined',
                'data': {
                    'opponent_username': request.user.username,
                }
            }
        )

        # Notify Sender via FCM
        try:
            send_push_notification(
                invitation.sender,
                title=request.user.username,
                body=f"{request.user.username} declined your invitation",
                data={'type': 'game_decline'}
            )
        except Exception as e:
            print(f"DEBUG: Decline notification failed: {e}")

        return Response({"status": "declined"})

    return Response({"error": "Invalid status"}, status=400)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def cancel_invitation(request):
    """Cancel a pending invitation."""
    invitation_id = request.data.get('invitation_id')
    try:
        invitation = GameInvitation.objects.get(id=invitation_id, sender=request.user, status='pending')
        invitation.status = 'cancelled'
        invitation.save()
        return Response({"status": "cancelled"})
    except GameInvitation.DoesNotExist:
        return Response({"error": "Invitation not found or not pending"}, status=404)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_pending_invitations(request):
    """List all pending invitations received by the current user."""
    invitations = GameInvitation.objects.filter(receiver=request.user, status='pending').order_by('-created_at')
    
    data = []
    for inv in invitations:
        data.append({
            'id': inv.id,
            'sender': {
                'id': inv.sender.id,
                'username': inv.sender.username,
                'photo_url': getattr(inv.sender, 'profile_photo_url', None),
            },
            'created_at': inv.created_at,
        })
    return Response(data)
