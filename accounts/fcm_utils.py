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
