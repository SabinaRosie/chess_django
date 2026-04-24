import random
import requests as http_requests
from django.core.mail import send_mail
from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.permissions import IsAuthenticated
from .models import OTPVerification

from django.conf import settings
from django.utils import timezone


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