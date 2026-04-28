import random
import requests as http_requests
from django.core.mail import send_mail
from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.permissions import IsAuthenticated
from .models import OTPVerification, CallRoom, CallSignal

from django.conf import settings
from django.utils import timezone
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer


def _send_email_brevo(to_email, subject, body):
    """Send email via Brevo HTTP API (works on HF Spaces where SMTP is blocked)."""
    api_key = settings.BREVO_API_KEY
    if not api_key:
        return False, "BREVO_API_KEY not set"

    resp = http_requests.post(
        "https://api.brevo.com/v3/smtp/email",
        headers={
            "api-key": api_key,
            "Content-Type": "application/json",
        },
        json={
            "sender": {"name": "Sabina Chess", "email": settings.EMAIL_HOST_USER},
            "to": [{"email": to_email}],
            "subject": subject,
            "textContent": body,
        },
        timeout=15,
    )

    if resp.status_code in (200, 201):
        return True, None
    else:
        return False, f"Brevo API error {resp.status_code}: {resp.text}"


def _send_otp_email(user):
    otp = str(random.randint(100000, 999999))

    # update_or_create to ensure one OTP per user
    otp_record, created = OTPVerification.objects.update_or_create(
        user=user,
        defaults={'otp': otp, 'is_verified': False}
    )

    # If updating existing record, reset the expiry timestamp
    if not created:
        OTPVerification.objects.filter(pk=otp_record.pk).update(created_at=timezone.now())

    print(f"DEBUG: sending OTP {otp} to {user.email}")

    # Use Brevo API if key is set, otherwise fall back to SMTP (for local dev)
    if settings.BREVO_API_KEY:
        success, error = _send_email_brevo(
            user.email,
            "Your Verification Code",
            f"Your verification code is {otp}. It will expire in 10 minutes.",
        )
        if success:
            print(f"DEBUG: OTP email sent via Brevo to {user.email}")
        else:
            print(f"WARNING: Brevo email failed: {error}")
        return success, error
    else:
        try:
            send_mail(
                'Your Verification Code',
                f'Your verification code is {otp}. It will expire in 10 minutes.',
                settings.DEFAULT_FROM_EMAIL,
                [user.email],
                fail_silently=False,
            )
            print(f"DEBUG: OTP email sent via SMTP to {user.email}")
            return True, None
        except Exception as e:
            error_msg = str(e)
            print(f"WARNING: SMTP email failed: {error_msg}")
            return False, error_msg

@api_view(['POST'])
def signup(request):
    try:
        username = request.data.get('username')
        email = request.data.get('email')
        password = request.data.get('password')

        if not username or not email or not password:
            return Response({"error": "All fields required"}, status=400)

        if User.objects.filter(username=username).exists():
            return Response({"error": "Username already exists"}, status=400)

        if User.objects.filter(email=email).exists():
            return Response({"error": "Email already exists"}, status=400)

        # Create active user (verification removed)
        user = User.objects.create_user(
            username=username,
            email=email,
            password=password,
            is_active=True
        )

        refresh = RefreshToken.for_user(user)
        return Response({
            "message": "User created successfully!",
            "access": str(refresh.access_token),
            "refresh": str(refresh),
            "username": user.username,
            "email": user.email
        })
    except Exception as e:
        print(f"DEBUG: signup error: {str(e)}")
        import traceback
        traceback.print_exc()
        return Response({"error": f"Signup failed: {str(e)}"}, status=500)

@api_view(['POST'])
def login(request):
    try:
        username_or_email = request.data.get('username')
        password = request.data.get('password')

        if not username_or_email or not password:
            return Response({"error": "Username/email and password required"}, status=400)

        # 1. Try traditional authentication
        user = authenticate(username=username_or_email, password=password)

        # 2. If it fails, check if input was an email
        if user is None:
            try:
                user_obj = User.objects.get(email=username_or_email)
                user = authenticate(username=user_obj.username, password=password)
            except (User.DoesNotExist, User.MultipleObjectsReturned):
                pass

        if user is None:
            # Check if user exists but is inactive
            try:
                # Try finding by username OR email
                from django.db.models import Q
                temp_user = User.objects.filter(Q(username=username_or_email) | Q(email=username_or_email)).first()
                if temp_user and not temp_user.is_active:
                    return Response({"error": "Account not verified. Please check your email for the OTP."}, status=403)
            except Exception:
                pass
            return Response({"error": "Invalid credentials"}, status=401)

        refresh = RefreshToken.for_user(user)
        return Response({
            "access": str(refresh.access_token),
            "refresh": str(refresh),
            "username": user.username,
            "email": user.email
        })
    except Exception as e:
        print(f"DEBUG: login error: {str(e)}")
        return Response({"error": f"Login failed: {str(e)}"}, status=500)

@api_view(['POST'])
def forgot_password(request):
    try:
        email = request.data.get('email')
        if not email:
            return Response({"error": "Email is required"}, status=400)

        try:
            # Case-insensitive email lookup
            user = User.objects.get(email__iexact=email)
        except User.DoesNotExist:
            return Response({"error": "User with this email does not exist"}, status=404)
        except User.MultipleObjectsReturned:
            # If multiple, get the most recently active one or first
            user = User.objects.filter(email__iexact=email).order_by('-last_login').first()

        email_sent, email_error = _send_otp_email(user)
        if email_sent:
            return Response({"message": "OTP sent to your email. Please check your inbox (and spam)."})
        else:
            return Response({
                "message": "OTP created but email delivery failed. Please try again.",
                "email_error": email_error
            }, status=200)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return Response({"error": f"Failed to send OTP: {str(e)}"}, status=500)

@api_view(['POST'])
def verify_otp(request):
    try:
        email = request.data.get('email')
        otp = request.data.get('otp')

        if not email or not otp:
            return Response({"error": "Email and OTP are required"}, status=400)

        try:
            # Case-insensitive email lookup for flexibility
            user = User.objects.filter(email__iexact=email).first()
            if not user:
                return Response({"error": "No user found with this email"}, status=404)

            # Ensure otp is treated as string and trimmed
            otp_str = str(otp).strip()
            otp_record = OTPVerification.objects.get(user=user, otp=otp_str)
        except OTPVerification.DoesNotExist:
            return Response({"error": "Invalid OTP. Please check your email again."}, status=400)
        except Exception as e:
            return Response({"error": f"Verification error: {str(e)}"}, status=400)

        if otp_record.is_expired():
            return Response({"error": "OTP has expired. Please request a new one."}, status=400)

        otp_record.is_verified = True
        otp_record.save()

        # If it was a signup OTP, activate the user
        if not user.is_active:
            user.is_active = True
            user.save()
            refresh = RefreshToken.for_user(user)
            return Response({
                "message": "Email verified and account activated!",
                "access": str(refresh.access_token),
                "refresh": str(refresh)
            })

        return Response({"message": "OTP verified successfully"})
    except Exception as e:
        print(f"DEBUG: verify_otp error: {str(e)}")
        return Response({"error": f"Verification error: {str(e)}"}, status=500)

@api_view(['POST'])
def reset_password(request):
    try:
        email = request.data.get('email')
        new_password = request.data.get('new_password')

        if not email or not new_password:
            return Response({"error": "Email and new password are required"}, status=400)

        try:
            user = User.objects.filter(email__iexact=email).first()
            if not user:
                return Response({"error": "User not found"}, status=404)
            otp_record = OTPVerification.objects.get(user=user)
        except OTPVerification.DoesNotExist:
            return Response({"error": "No OTP verification record found for this user"}, status=400)

        if not otp_record.is_verified:
            return Response({"error": "OTP not verified"}, status=400)

        if otp_record.is_expired():
            return Response({"error": "Verification session expired. Please request a new OTP."}, status=400)

        user.set_password(new_password)
        user.save()
        otp_record.delete()

        return Response({"message": "Password reset successful"})
    except Exception as e:
        print(f"DEBUG: reset_password error: {str(e)}")
        return Response({"error": f"Reset password failed: {str(e)}"}, status=500)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def user_profile(request):
    user = request.user
    return Response({
        "username": user.username,
        "email": user.email,
    })

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_users(request):
    users = User.objects.all().values('username', 'email')
    return Response(list(users))

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def logout_view(request):
    try:
        refresh_token = request.data.get("refresh")
        if refresh_token:
            token = RefreshToken(refresh_token)
            token.blacklist()
        return Response({"message": "Logged out successfully"})
    except Exception as e:
        return Response({"message": "Logged out (token local clear)"})

@api_view(['GET'])
def test_email(request):
    """Diagnostic endpoint to test email configuration."""
    config = {
        "EMAIL_HOST_USER": settings.EMAIL_HOST_USER,
        "BREVO_API_KEY_SET": bool(settings.BREVO_API_KEY),
        "method": "brevo" if settings.BREVO_API_KEY else "smtp",
    }

    # Test with Brevo if available, otherwise SMTP
    if settings.BREVO_API_KEY:
        success, error = _send_email_brevo(
            settings.EMAIL_HOST_USER,
            "Test Email from Sabina Chess",
            "If you receive this, Brevo email is working!",
        )
        config["test_result"] = "SUCCESS" if success else f"FAILED: {error}"
    else:
        config["test_result"] = "BREVO_API_KEY not set - cannot test"

    return Response(config)


# ─────────────────────────────────────────────────────
# WebRTC Call Signaling Endpoints
# ─────────────────────────────────────────────────────

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
    """Generate ephemeral TURN credentials using HMAC-SHA1 shared secret.
    Uses Metered Open Relay's static auth (no signup required).
    Credentials are valid for 24 hours.
    """
    import hmac
    import hashlib
    import base64
    import time

    # Metered Open Relay static auth secret (public, no signup needed)
    turn_secret = 'openrelayprojectsecret'
    turn_server = 'staticauth.openrelay.metered.ca'

    # Generate time-limited credentials (valid for 24 hours)
    ttl = 24 * 3600  # 24 hours
    expiry = int(time.time()) + ttl
    username = f'{expiry}:{request.user.username}'
    
    # HMAC-SHA1 of the username with the shared secret
    hmac_digest = hmac.new(
        turn_secret.encode('utf-8'),
        username.encode('utf-8'),
        hashlib.sha1
    ).digest()
    credential = base64.b64encode(hmac_digest).decode('utf-8')

    ice_servers = [
        {'urls': 'stun:stun.l.google.com:19302'},
        {'urls': 'stun:stun1.l.google.com:19302'},
        {
            'urls': f'turn:{turn_server}:80',
            'username': username,
            'credential': credential,
        },
        {
            'urls': f'turn:{turn_server}:80?transport=tcp',
            'username': username,
            'credential': credential,
        },
        {
            'urls': f'turn:{turn_server}:443',
            'username': username,
            'credential': credential,
        },
        {
            'urls': f'turn:{turn_server}:443?transport=tcp',
            'username': username,
            'credential': credential,
        },
        {
            'urls': f'turns:{turn_server}:443?transport=tcp',
            'username': username,
            'credential': credential,
        },
    ]

    return Response({'ice_servers': ice_servers})