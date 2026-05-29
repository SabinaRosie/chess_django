from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from accounts.models import FCMToken

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

