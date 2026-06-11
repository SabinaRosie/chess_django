from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from accounts.models import FCMToken, NotificationLog

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def register_fcm_token(request):
    """Register or update an FCM token for the current user."""
    token = request.data.get('token')
    device_id = request.data.get('device_id')

    if not token:
        return Response({"error": "token is required"}, status=400)

    # Update or create the token entry
    print(f"DEBUG: Registering FCM token for user: {request.user.username} (ID: {request.user.id})")
    fcm_token, created = FCMToken.objects.update_or_create(
        token=token,
        defaults={
            'user': request.user,
            'device_id': device_id,
        }
    )
    print(f"DEBUG: Token registration result - Created: {created}")

    return Response({
        "message": "Token registered successfully",
        "created": created
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def track_notification(request):
    """Track the status of a notification (delivered, opened, dismissed)."""
    notification_id = request.data.get('notification_id')
    status = request.data.get('status')

    if not notification_id or not status:
        return Response({"error": "notification_id and status are required"}, status=400)

    # Valid statuses from models.py
    valid_statuses = ['sent', 'delivered', 'opened', 'dismissed']
    if status not in valid_statuses:
        return Response({"error": "Invalid status"}, status=400)

    try:
        log_entry = NotificationLog.objects.get(id=notification_id, user=request.user)
        log_entry.status = status
        log_entry.save()
        return Response({"message": f"Notification marked as {status}"})
    except NotificationLog.DoesNotExist:
        return Response({"error": "Notification not found or not owned by user"}, status=404)

@api_view(['GET', 'PUT'])
@permission_classes([IsAuthenticated])
def notification_settings(request):
    """Get or update user notification preferences."""
    profile = request.user.profile
    if request.method == 'GET':
        return Response({
            'allow_calls': profile.allow_calls,
            'allow_messages': profile.allow_messages,
            'allow_invitations': profile.allow_invitations,
            'allow_sticky': profile.allow_sticky,
        })
    elif request.method == 'PUT':
        profile.allow_calls = request.data.get('allow_calls', profile.allow_calls)
        profile.allow_messages = request.data.get('allow_messages', profile.allow_messages)
        profile.allow_invitations = request.data.get('allow_invitations', profile.allow_invitations)
        profile.allow_sticky = request.data.get('allow_sticky', profile.allow_sticky)
        profile.save()
        return Response({'message': 'Notification settings updated successfully'})

