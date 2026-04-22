import random
from django.core.mail import send_mail
from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.permissions import IsAuthenticated
from .models import OTPVerification

def _send_otp_email(user):
    otp = str(random.randint(100000, 999999))
    OTPVerification.objects.update_or_create(
        user=user,
        defaults={'otp': otp, 'is_verified': False}
    )
    
    send_mail(
        'Your Verification Code',
        f'Your verification code is {otp}. It will expire in 10 minutes.',
        'noreply@chessapp.com',
        [user.email],
        fail_silently=False,
    )

@api_view(['POST'])
def signup(request):
    username = request.data.get('username')
    email = request.data.get('email')
    password = request.data.get('password')

    if not username or not email or not password:
        return Response({"error": "All fields required"}, status=400)

    if User.objects.filter(username=username).exists():
        return Response({"error": "Username already exists"}, status=400)
    
    if User.objects.filter(email=email).exists():
        return Response({"error": "Email already exists"}, status=400)

    # Create inactive user
    user = User.objects.create_user(
        username=username,
        email=email,
        password=password,
        is_active=False
    )

    _send_otp_email(user)

    return Response({
        "message": "User created. Please verify your email with the OTP sent.",
        "step": "verify"
    })

@api_view(['POST'])
def login(request):
    username = request.data.get('username')
    password = request.data.get('password')

    # Note: authenticate() checks for is_active by default and returns None if False
    user = authenticate(username=username, password=password)

    if user is None:
        # Check if user exists but is inactive
        try:
            temp_user = User.objects.get(username=username)
            if not temp_user.is_active:
                return Response({"error": "Account not verified. Please verify your email."}, status=403)
        except User.DoesNotExist:
            pass
        return Response({"error": "Invalid credentials"}, status=401)

    refresh = RefreshToken.for_user(user)
    return Response({
        "access": str(refresh.access_token),
        "refresh": str(refresh),
        "username": user.username,
        "email": user.email
    })

@api_view(['POST'])
def forgot_password(request):
    email = request.data.get('email')
    if not email:
        return Response({"error": "Email is required"}, status=400)
    
    try:
        user = User.objects.get(email=email)
    except User.DoesNotExist:
        return Response({"error": "User with this email does not exist"}, status=404)
        
    _send_otp_email(user)
    return Response({"message": "OTP sent to email"})

@api_view(['POST'])
def verify_otp(request):
    email = request.data.get('email')
    otp = request.data.get('otp')
    
    try:
        user = User.objects.get(email=email)
        otp_record = OTPVerification.objects.get(user=user, otp=otp)
    except (User.DoesNotExist, OTPVerification.DoesNotExist):
        return Response({"error": "Invalid email or OTP"}, status=400)
        
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

@api_view(['POST'])
def reset_password(request):
    email = request.data.get('email')
    new_password = request.data.get('new_password')
    
    try:
        user = User.objects.get(email=email)
        otp_record = OTPVerification.objects.get(user=user)
    except (User.DoesNotExist, OTPVerification.DoesNotExist):
        return Response({"error": "Invalid request"}, status=400)
        
    if not otp_record.is_verified:
        return Response({"error": "OTP not verified"}, status=400)
        
    if otp_record.is_expired():
        return Response({"error": "Verification session expired. Please request a new OTP."}, status=400)
        
    user.set_password(new_password)
    user.save()
    otp_record.delete()
    
    return Response({"message": "Password reset successful"})

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def user_profile(request):
    user = request.user
    return Response({
        "username": user.username,
        "email": user.email,
    })

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