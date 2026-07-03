import logging
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.contrib.auth.models import User
from accounts.models import CallRoom, CallSignal, RecordedCall
from django.conf import settings
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
import requests as http_requests

logger = logging.getLogger(__name__)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_call(request):
    """Create a new call room and notify the callee."""
    try:
        callee_username = request.data.get('callee_username')
        call_type = request.data.get('call_type', 'audio')

        if not callee_username:
            return Response({"error": "callee_username is required"}, status=400)

        if call_type not in ('audio', 'video'):
            return Response({"error": "call_type must be 'audio' or 'video'"}, status=400)

        try:
            callee = User.objects.get(username=callee_username)
        except User.DoesNotExist:
            return Response({"error": "User not found"}, status=404)

        if callee == request.user:
            return Response({"error": "Cannot call yourself"}, status=400)

        # End any existing pending calls from this caller
        CallRoom.objects.filter(caller=request.user, status='pending').update(status='ended')

        room = CallRoom.objects.create(
            caller=request.user,
            callee=callee,
            call_type=call_type,
        )

        # Notify callee via WebSocket
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            f'user_{callee.id}'.replace(' ', '_'),
            {
                'type': 'incoming_call',
                'data': {
                    'room_id': str(room.room_id),
                    'caller': request.user.username,
                    'call_type': call_type,
                }
            }
        )

        # 🔹 Trigger FCM push notification for background/terminated wake-up
        try:
            from accounts.notifications.utils import send_push_notification
            fcm_data = {
                'type': 'incoming_call',
                'room_id': str(room.room_id),
                'caller': request.user.username,
                'call_type': call_type,
            }
            send_push_notification(
                user=callee,
                title=f"Incoming {call_type.capitalize()} Call",
                body=f"{request.user.username} is calling you",
                data=fcm_data,
                channel_id='high_importance_channel',
                sender=request.user
            )
            logger.info("CALL: FCM sent to %s from %s", callee.username, request.user.username)
        except Exception as fcm_err:
            logger.warning("CALL: FCM warning in create_call", exc_info=fcm_err)

        return Response({
            "room_id": str(room.room_id),
            "caller": request.user.username,
            "callee": callee_username,
            "call_type": call_type,
            "status": room.status,
        })
    except Exception as e:
        return Response({"error": str(e)}, status=500)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def check_incoming(request):
    """Check if there are any incoming calls for the current user."""
    try:
        # Find pending calls for this user, expire old ones
        pending_calls = CallRoom.objects.filter(
            callee=request.user,
            status='pending',
        ).order_by('-created_at')

        for call in pending_calls:
            if call.is_expired():
                call.status = 'ended'
                call.save()

        # Get the most recent non-expired pending call
        active_call = CallRoom.objects.filter(
            callee=request.user,
            status='pending',
        ).order_by('-created_at').first()

        if active_call:
            return Response({
                "has_incoming": True,
                "room_id": str(active_call.room_id),
                "caller": active_call.caller.username,
                "call_type": active_call.call_type,
            })

        return Response({"has_incoming": False})
    except Exception as e:
        return Response({"error": str(e)}, status=500)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def answer_call(request):
    """Accept or reject an incoming call."""
    try:
        room_id = request.data.get('room_id')
        action = request.data.get('action')  # 'accept' or 'reject'

        if not room_id or not action:
            return Response({"error": "room_id and action required"}, status=400)

        try:
            room = CallRoom.objects.get(room_id=room_id, callee=request.user)
        except CallRoom.DoesNotExist:
            return Response({"error": "Call not found"}, status=404)

        if action == 'accept':
            room.status = 'active'
            room.save()
            return Response({
                "status": "active",
                "room_id": str(room.room_id),
                "call_type": room.call_type,
                "caller": room.caller.username,
            })
        elif action == 'reject':
            room.status = 'rejected'
            room.save()
            return Response({"status": "rejected"})
        else:
            return Response({"error": "action must be 'accept' or 'reject'"}, status=400)
    except Exception as e:
        return Response({"error": str(e)}, status=500)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def send_signal(request):
    """Send an SDP offer/answer or ICE candidate."""
    try:
        room_id = request.data.get('room_id')
        signal_type = request.data.get('signal_type')
        data = request.data.get('data')

        if not room_id or not signal_type or data is None:
            return Response({"error": "room_id, signal_type, and data required"}, status=400)

        if signal_type not in ('offer', 'answer', 'candidate'):
            return Response({"error": "Invalid signal_type"}, status=400)

        try:
            room = CallRoom.objects.get(room_id=room_id)
        except CallRoom.DoesNotExist:
            return Response({"error": "Call room not found"}, status=404)

        # Verify user is part of this call
        if request.user not in (room.caller, room.callee):
            return Response({"error": "Not authorized for this call"}, status=403)

        CallSignal.objects.create(
            room=room,
            sender=request.user,
            signal_type=signal_type,
            data=data,
        )

        return Response({"status": "signal_sent"})
    except Exception as e:
        return Response({"error": str(e)}, status=500)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_signals(request):
    """Get pending signals for a call room (for the current user)."""
    try:
        room_id = request.GET.get('room_id')
        if not room_id:
            return Response({"error": "room_id is required"}, status=400)

        try:
            room = CallRoom.objects.get(room_id=room_id)
        except CallRoom.DoesNotExist:
            return Response({"error": "Call room not found"}, status=404)

        if request.user not in (room.caller, room.callee):
            return Response({"error": "Not authorized"}, status=403)

        # Get unread signals NOT sent by the current user
        signals = CallSignal.objects.filter(
            room=room,
            is_read=False,
        ).exclude(sender=request.user).order_by('created_at')

        signal_list = []
        for sig in signals:
            signal_list.append({
                "signal_type": sig.signal_type,
                "data": sig.data,
                "sender": sig.sender.username,
            })
            sig.is_read = True
            sig.save()

        # Also check if the call has been ended/rejected by the other party
        return Response({
            "signals": signal_list,
            "room_status": room.status,
        })
    except Exception as e:
        return Response({"error": str(e)}, status=500)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def end_call(request):
    """End an active or pending call."""
    try:
        room_id = request.data.get('room_id')
        if not room_id:
            return Response({"error": "room_id is required"}, status=400)

        try:
            room = CallRoom.objects.get(room_id=room_id)
        except CallRoom.DoesNotExist:
            return Response({"error": "Call room not found"}, status=404)

        if request.user not in (room.caller, room.callee):
            return Response({"error": "Not authorized"}, status=403)

        room.status = 'ended'
        room.save()

        # Notify the other party about the cancellation if it was pending
        other_user = room.callee if request.user == room.caller else room.caller
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            f'user_{other_user.id}'.replace(' ', '_'),
            {
                'type': 'call_cancelled',
                'data': {'room_id': str(room.room_id)}
            }
        )

        # Clean up signals
        CallSignal.objects.filter(room=room).delete()

        return Response({"status": "ended"})
    except Exception as e:
        return Response({"error": str(e)}, status=500)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_turn_credentials(request):
    """Generate TURN credentials dynamically.
    Fetches temporary TURN credentials using the Metered REST API if METERED_API_KEY is set.
    """
    domain = 'sabina-chess.metered.live'
    api_key = getattr(settings, 'METERED_API_KEY', None)

    if api_key:
        try:
            # Fetch dynamic credentials from Metered API
            resp = http_requests.get(f"https://{domain}/api/v1/turn/credentials?apiKey={api_key}", timeout=5)
            if resp.status_code == 200:
                # Metered returns exactly the array of ICE servers we need to pass to the client
                metered_servers = resp.json()
                stun_servers = [
                    {'urls': 'stun:stun.l.google.com:19302'},
                    {'urls': 'stun:stun1.l.google.com:19302'},
                    {'urls': 'stun:stun2.l.google.com:19302'},
                    {'urls': 'stun:stun3.l.google.com:19302'},
                    {'urls': 'stun:stun4.l.google.com:19302'},
                    {'urls': 'stun:stun.cloudflare.com:3478'},
                ]
                return Response({'ice_servers': stun_servers + metered_servers})
            else:
                logger.warning("CALL: Failed to fetch TURN credentials, status %d: %s", resp.status_code, resp.text)
        except Exception as e:
            logger.warning("CALL: Error calling Metered API", exc_info=e)

    # 🔹 Fallback: STUN + Open Relay TURN servers for cross-network calls
    ice_servers = [
        {'urls': 'stun:stun.l.google.com:19302'},
        {'urls': 'stun:stun1.l.google.com:19302'},
        {'urls': 'stun:stun2.l.google.com:19302'},
        {'urls': 'stun:stun3.l.google.com:19302'},
        {'urls': 'stun:stun4.l.google.com:19302'},
        {
            'urls': 'turn:openrelay.metered.ca:80',
            'username': 'openrelayproject',
            'credential': 'openrelayproject',
        },
        {
            'urls': 'turn:openrelay.metered.ca:443',
            'username': 'openrelayproject',
            'credential': 'openrelayproject',
        },
        {
            'urls': 'turn:openrelay.metered.ca:443?transport=tcp',
            'username': 'openrelayproject',
            'credential': 'openrelayproject',
        },
        {
            'urls': 'turns:openrelay.metered.ca:443',
            'username': 'openrelayproject',
            'credential': 'openrelayproject',
        },
    ]

    return Response({'ice_servers': ice_servers})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def save_recording(request):
    """Save call recording to the database.
    Accepts: caller_username, callee_username, call_type, recording_file.
    """
    try:
        caller_username = request.data.get('caller_username')
        callee_username = request.data.get('callee_username')
        call_type = request.data.get('call_type', 'unknown')
        recording_file = request.FILES.get('recording_file')

        logger.debug("[RECORDING] Request: caller=%s, callee=%s, type=%s, file=%s", caller_username, callee_username, call_type, recording_file)

        if not recording_file:
            logger.error("[RECORDING] No recording_file in request.FILES. FILES=%s, DATA=%s", list(request.FILES.keys()), list(request.data.keys()))
            return Response({'success': False, 'error': 'No recording file provided'}, status=400)

        caller = None
        callee = None

        if caller_username:
            caller = User.objects.filter(username=caller_username).first()
            if not caller:
                logger.warning("[RECORDING] caller '%s' not found in DB", caller_username)
        if callee_username:
            callee = User.objects.filter(username=callee_username).first()
            if not callee:
                logger.warning("[RECORDING] callee '%s' not found in DB", callee_username)

        logger.debug("[RECORDING] Creating entry: caller=%s, callee=%s, file=%s, size=%s", caller, callee, recording_file.name, recording_file.size)

        recorded_call = RecordedCall.objects.create(
            caller=caller,
            callee=callee,
            call_type=call_type,
            recording_file=recording_file
        )

        file_url = recorded_call.recording_file.url if recorded_call.recording_file else None
        logger.info("[RECORDING] SUCCESS: RecordedCall #%s saved. URL: %s", recorded_call.id, file_url)

        return Response({
            'success': True,
            'message': 'Recording saved successfully',
            'data': {
                'id': recorded_call.id,
                'caller': caller.username if caller else None,
                'callee': callee.username if callee else None,
                'call_type': recorded_call.call_type,
                'recording_file': file_url
            }
        })
    except Exception as e:
        import traceback
        logger.error("[RECORDING] EXCEPTION", exc_info=e)
        logger.error(traceback.format_exc())
        return Response({'success': False, 'error': str(e)}, status=500)




