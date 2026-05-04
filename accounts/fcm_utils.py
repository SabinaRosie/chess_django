import os
import firebase_admin
from firebase_admin import credentials, messaging
from django.conf import settings
from .models import FCMToken

import json
# ...
FIREBASE_CREDENTIALS_PATH = os.path.join(settings.BASE_DIR, 'serviceAccountKey.json')

def initialize_firebase():
    if firebase_admin._apps:
        return
    
    # 1. Try environment variable (Best for HF Secrets)
    env_creds = os.environ.get('FIREBASE_CREDENTIALS')
    if env_creds:
        try:
            cred_dict = json.loads(env_creds)
            cred = credentials.Certificate(cred_dict)
            firebase_admin.initialize_app(cred)
            print("FCM: Initialized via environment variable.")
            return
        except Exception as e:
            print(f"ERROR: Failed to parse FIREBASE_CREDENTIALS secret: {e}")

    # 2. Try local file
    if os.path.exists(FIREBASE_CREDENTIALS_PATH):
        cred = credentials.Certificate(FIREBASE_CREDENTIALS_PATH)
        firebase_admin.initialize_app(cred)
        print("FCM: Initialized via local file.")
    else:
        print("WARNING: Firebase credentials not found. Push notifications disabled.")

# Call initialization
initialize_firebase()

def send_push_notification(user, title, body, data=None):
    """Send a push notification to all devices registered for a user with retry logic."""
    def _attempt_send():
        # Re-fetch tokens freshly to ensure we have the latest
        tokens = list(FCMToken.objects.filter(user=user).values_list('token', flat=True))
        if not tokens:
            print(f"FCM DEBUG: No tokens found for {user.username}")
            return False, "no_tokens"
        
        if not firebase_admin._apps:
            return False, "not_initialized"

        message_payload = messaging.MulticastMessage(
            notification=messaging.Notification(title=title, body=body),
            android=messaging.AndroidConfig(
                priority='high',
                notification=messaging.AndroidNotification(
                    channel_id='high_importance_channel',
                    priority='max', 
                    default_vibrate_timings=True,
                    default_sound=True,
                ),
            ),
            data=data or {},
            tokens=tokens,
        )
        
        try:
            response = messaging.send_each_for_multicast(message_payload)
            print(f"FCM DEBUG: Sent to {user.username}. Success: {response.success_count}, Failure: {response.failure_count}")
            return response.failure_count < len(tokens), "partial_or_full_success"
        except Exception as e:
            print(f"FCM DEBUG: Error: {str(e)}")
            return False, str(e)

    # First attempt
    success, reason = _attempt_send()
    if not success and reason != "no_tokens":
        # Immediate retry once if it wasn't just a "no tokens" issue
        print(f"FCM DEBUG: Retrying send to {user.username}...")
        _attempt_send()
