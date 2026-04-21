from django.shortcuts import render

# Create your views here.
from django.contrib.auth.models import User
from django.contrib.auth import authenticate
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken


@api_view(['POST'])
def signup(request):
    username = request.data.get('username')
    email = request.data.get('email')
    password = request.data.get('password')

    if not username or not email or not password:
        return Response({"error": "All fields required"}, status=400)

    if User.objects.filter(username=username).exists():
        return Response({"error": "User already exists"}, status=400)

    user = User.objects.create_user(
        username=username,
        email=email,
        password=password
    )

    refresh = RefreshToken.for_user(user)

    return Response({
        "message": "User created successfully",
        "access": str(refresh.access_token),
        "refresh": str(refresh),
    })


@api_view(['POST'])
def login(request):
    username = request.data.get('username')
    password = request.data.get('password')

    user = authenticate(username=username, password=password)

    if user is None:
        return Response({"error": "Invalid credentials"}, status=401)

    refresh = RefreshToken.for_user(user)

    return Response({
        "access": str(refresh.access_token),
        "refresh": str(refresh),
    })


import random
from django.core.mail import send_mail
from .models import OTPVerification
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import permission_classes

@api_view(['POST'])
def forgot_password(request):
    email = request.data.get('email')
    if not email:
        return Response({"error": "Email is required"}, status=400)
    
    try:
        user = User.objects.get(email=email)
    except User.DoesNotExist:
        return Response({"error": "User with this email does not exist"}, status=404)
        
    otp = str(random.randint(100000, 999999))
    
    OTPVerification.objects.update_or_create(
        user=user,
        defaults={'otp': otp, 'is_verified': False}
    )
    
    send_mail(
        'Password Reset OTP',
        f'Your OTP for password reset is {otp}',
        'noreply@chessapp.com',
        [email],
        fail_silently=False,
    )
    
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
        
    otp_record.is_verified = True
    otp_record.save()
    
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