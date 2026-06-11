import os
import firebase_admin
from firebase_admin import credentials, messaging
from django.conf import settings
from ..models import FCMToken, NotificationLog

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

import threading

def send_push_notification(user, title, body, data=None, async_send=True, channel_id='normal_channel'):
    """Send a push notification to all devices registered for a user."""
    
    notification_type = data.get('type', 'general') if data else 'general'
    
    # Check user preferences
    profile = getattr(user, 'profile', None)
    if profile:
        is_blocked = False
        if notification_type == 'incoming_call' and not profile.allow_calls:
            is_blocked = True
        elif notification_type in ['chat_notification', 'chat'] and not profile.allow_messages:
            is_blocked = True
        elif 'invitation' in notification_type and not profile.allow_invitations:
            is_blocked = True
        elif channel_id == 'high_importance_channel' and not profile.allow_sticky:
            is_blocked = True
            
        if is_blocked:
            NotificationLog.objects.create(
                user=user,
                title=title,
                notification_type=notification_type,
                status='blocked'
            )
            print(f"FCM BLOCKED: '{notification_type}' blocked by {user.username} preferences.")
            return False

    # Create notification log synchronously before async sending
    log_entry = NotificationLog.objects.create(
        user=user,
        title=title,
        notification_type=notification_type,
        status='sent'
    )
    
    # Inject tracking ID into data
    if data is None:
        data = {}
    data['notification_id'] = str(log_entry.id)
    
    def _send():
        import time
        # Re-fetch tokens freshly to ensure we have the latest
        tokens = list(FCMToken.objects.filter(user=user).values_list('token', flat=True))
        if not tokens:
            print(f"FCM ERROR: No tokens found for user {user.username} (ID: {user.id}). Cannot send '{title}'")
            return

        print(f"FCM DEBUG: Found {len(tokens)} tokens for {user.username}. Sending '{title}'...")
        for i, t in enumerate(tokens):
            print(f"  Token {i+1}: {t[:15]}...")

        if not firebase_admin._apps:
            print(f"FCM ERROR: Firebase not initialized. Cannot send to {user.username}")
            return

        # 🔹 Ensure all data values are strings (FCM requirement)
        safe_data = {}
        if data:
            for k, v in data.items():
                safe_data[str(k)] = str(v) if v is not None else ""

        message_payload = messaging.MulticastMessage(
            notification=messaging.Notification(title=title, body=body),
            android=messaging.AndroidConfig(
                priority='high' if channel_id == 'high_importance_channel' else 'normal',
                notification=messaging.AndroidNotification(
                    channel_id=channel_id,
                    priority='max' if channel_id == 'high_importance_channel' else 'default', 
                    default_vibrate_timings=True,
                    default_sound=True,
                ),
            ),
            data=safe_data,
            tokens=tokens,
        )
        
        success = False
        attempts = 0
        while not success and attempts < 2:
            try:
                attempts += 1
                response = messaging.send_each_for_multicast(message_payload)
                if response.failure_count > 0:
                    # Log specific failures and cleanup invalid tokens
                    for idx, resp in enumerate(response.responses):
                        if not resp.success:
                            error_code = getattr(resp.exception, 'code', str(resp.exception))
                            print(f"FCM TOKEN FAILURE: Token {tokens[idx][:10]}... Error: {error_code}")
                            
                            # Cleanup stale/invalid tokens
                            if 'invalid-registration' in str(error_code).lower() or 'not-registered' in str(error_code).lower():
                                bad_token = tokens[idx]
                                FCMToken.objects.filter(token=bad_token).delete()
                                print(f"FCM CLEANUP: Deleted stale token: {bad_token[:15]}...")
                    
                    if response.success_count > 0:
                        success = True # At least one device received it
                    else:
                        print(f"FCM FAILURE: All devices failed for {user.username}")
                else:
                    print(f"FCM SUCCESS: Sent to {user.username} ({response.success_count} devices)")
                    success = True
                
                if not success and attempts == 1:
                    print(f"FCM RETRY: First attempt failed for {user.username}, retrying in 1s...")
                    time.sleep(1)
            except Exception as e:
                print(f"FCM CRITICAL ERROR for {user.username} (Attempt {attempts}): {str(e)}")
                if attempts == 1:
                    time.sleep(1)

    if async_send:
        thread = threading.Thread(target=_send)
        thread.start()
        return True
    else:
        _send()
        return True
