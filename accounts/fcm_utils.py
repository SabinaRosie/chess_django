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
    """Send a push notification to all devices registered for a user synchronously."""
    # Re-fetch tokens freshly to ensure we have the latest
    tokens = list(FCMToken.objects.filter(user=user).values_list('token', flat=True))
    if not tokens:
        print(f"FCM ERROR: No tokens found for user {user.username} (ID: {user.id})")
        return False

    if not firebase_admin._apps:
        print(f"FCM ERROR: Firebase not initialized. Cannot send to {user.username}")
        return False

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
        if response.failure_count > 0:
            print(f"FCM WARNING: Sent to {user.username}. Success: {response.success_count}, Failure: {response.failure_count}")
            # Log specific failures if needed (e.g. invalid tokens)
            for idx, resp in enumerate(response.responses):
                if not resp.success:
                    print(f"FCM TOKEN FAILURE: Token {tokens[idx][:10]}... failed with error: {resp.exception}")
        else:
            print(f"FCM SUCCESS: Sent to {user.username} ({response.success_count} devices)")
        return response.success_count > 0
    except Exception as e:
        print(f"FCM CRITICAL ERROR for {user.username}: {str(e)}")
        import traceback
        traceback.print_exc()
        return False
