import os
import firebase_admin
from firebase_admin import credentials, messaging
from django.conf import settings
from .models import FCMToken

# Initialize Firebase Admin SDK
# You need to place your serviceAccountKey.json in the project root or set the path
FIREBASE_CREDENTIALS_PATH = os.path.join(settings.BASE_DIR, 'serviceAccountKey.json')

if not firebase_admin._apps:
    if os.path.exists(FIREBASE_CREDENTIALS_PATH):
        cred = credentials.Certificate(FIREBASE_CREDENTIALS_PATH)
        firebase_admin.initialize_app(cred)
    else:
        # Fallback for environments where the key is provided via env var or other means
        # In production (e.g. HF Spaces), you might want to use environment variables
        print("WARNING: Firebase serviceAccountKey.json not found. Push notifications will not be sent.")

def send_push_notification(user, title, body, data=None):
    """Send a push notification to all devices registered for a user."""
    tokens = FCMToken.objects.filter(user=user).values_list('token', flat=True)
    if not tokens:
        return
    
    if not firebase_admin._apps:
        print("ERROR: Firebase Admin SDK not initialized.")
        return

    message_payload = messaging.MulticastMessage(
        notification=messaging.Notification(
            title=title,
            body=body,
        ),
        data=data or {},
        tokens=list(tokens),
    )
    
    try:
        response = messaging.send_multicast(message_payload)
        print(f"Successfully sent {response.success_count} notifications; {response.failure_count} failed.")
        
        # Optionally clean up invalid tokens
        if response.failure_count > 0:
            # Logic to remove stale tokens could go here
            pass
            
    except Exception as e:
        print(f"Error sending FCM message: {e}")
