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
    """Send a push notification to all devices registered for a user."""
    tokens = FCMToken.objects.filter(user=user).values_list('token', flat=True)
    if not tokens:
        return
    
    if not firebase_admin._apps:
        print("ERROR: Firebase Admin SDK not initialized.")
        return

    print(f"FCM DEBUG: Preparing message for tokens: {list(tokens)}")
    message_payload = messaging.MulticastMessage(
        notification=messaging.Notification(
            title=title,
            body=body,
        ),
        android=messaging.AndroidConfig(
            priority='high',
            notification=messaging.AndroidNotification(
                channel_id='high_importance_channel',
                # Priority can be 'min', 'low', 'default', 'high', 'max'
                priority='max', 
                default_vibrate_timings=True,
                default_sound=True,
            ),
        ),
        data=data or {},
        tokens=list(tokens),
    )
    
    try:
        print("FCM DEBUG: Calling messaging.send_each_for_multicast...")
        response = messaging.send_each_for_multicast(message_payload)
        print(f"FCM DEBUG: Response received! Success: {response.success_count}, Failure: {response.failure_count}")
        
        if response.failure_count > 0:
            for index, result in enumerate(response.responses):
                if not result.success:
                    print(f"FCM DEBUG: Token {index} failed with error: {result.exception}")
            
    except Exception as e:
        print(f"FCM DEBUG: CRITICAL ERROR sending FCM message: {str(e)}")
        import traceback
        traceback.print_exc()
