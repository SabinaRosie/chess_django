from rest_framework import serializers

class LoginSerializer(serializers.Serializer):
    username = serializers.CharField(help_text="Username or Email", default="your_username_or_email")
    password = serializers.CharField(write_only=True, default="your_password")

class SignupSerializer(serializers.Serializer):
    username = serializers.CharField(default="new_user")
    email = serializers.EmailField(default="user@example.com")
    password = serializers.CharField(write_only=True, default="password123")

class OTPVerifySerializer(serializers.Serializer):
    email = serializers.EmailField(default="user@example.com")
    otp = serializers.CharField(default="123456")

class ResetPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField(default="user@example.com")
    new_password = serializers.CharField(default="new_password123")

class ForgotPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField(default="user@example.com")
