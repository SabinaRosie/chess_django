import pytest
from rest_framework.test import APIClient
from django.contrib.auth.models import User
from accounts.models import OTPVerification, FCMToken
from django.utils import timezone
from datetime import timedelta

@pytest.fixture
def api_client():
    return APIClient()

@pytest.mark.django_db
def test_signup_api(api_client):
    """Test successful user registration."""
    response = api_client.post('/api/signup', {
        "username": "newplayer",
        "email": "new@player.com",
        "password": "StrongPassword123!"
    })
    assert response.status_code == 200
    assert "access" in response.data
    assert response.data["username"] == "newplayer"
    assert User.objects.filter(username="newplayer").exists()

@pytest.mark.django_db
def test_signup_duplicate_fails(api_client):
    """Test that duplicate registration fails."""
    User.objects.create_user(username="existing", email="old@test.com", password="123")
    
    # Duplicate username
    response = api_client.post('/api/signup', {
        "username": "existing",
        "email": "another@test.com",
        "password": "123"
    })
    assert response.status_code == 400
    assert "error" in response.data

@pytest.mark.django_db
def test_login_api_success(api_client):
    """Test successful login and token generation."""
    User.objects.create_user(username="loginuser", email="test@login.com", password="SafePassword123!")
    
    response = api_client.post('/api/login', {
        "email": "test@login.com",
        "password": "SafePassword123!"
    })
    assert response.status_code == 200
    assert "access" in response.data
    assert "refresh" in response.data

@pytest.mark.django_db
def test_login_api_email_case_insensitive(api_client):
    """Test login works regardless of email casing."""
    User.objects.create_user(username="caseuser", email="MixedCase@Test.com", password="Password123!")
    
    # Login with lowercase email
    response = api_client.post('/api/login', {
        "email": "mixedcase@test.com",
        "password": "Password123!"
    })
    assert response.status_code == 200
    assert response.data["username"] == "caseuser"

@pytest.mark.django_db
def test_forgot_password_and_reset_flow(api_client):
    """Test the full flow: forgot -> get otp -> verify -> reset."""
    email = "reset@test.com"
    user = User.objects.create_user(username="resetuser", email=email, password="OldPassword")
    
    # 1. Forgot password
    response = api_client.post('/api/forgot-password', {"email": email})
    assert response.status_code == 200
    
    # Fetch OTP from DB (simulating reading email)
    otp_record = OTPVerification.objects.get(user=user)
    otp = otp_record.otp
    
    # 2. Verify OTP
    verify_res = api_client.post('/api/verify-otp', {
        "email": email,
        "otp": otp
    })
    assert verify_res.status_code == 200
    
    # 3. Reset Password
    reset_res = api_client.post('/api/reset-password', {
        "email": email,
        "new_password": "NewCoolPassword123!"
    })
    assert reset_res.status_code == 200
    
    # Verify password changed
    user.refresh_from_db()
    assert user.check_password("NewCoolPassword123!") is True

@pytest.mark.django_db
def test_fcm_token_registration(api_client):
    """Test registering FCM token requires authentication."""
    user = User.objects.create_user(username="fcmuser", password="123")
    
    # Unauthenticated should fail
    response = api_client.post('/api/register-fcm-token', {"token": "test_token"})
    assert response.status_code == 401
    
    # Authenticated
    api_client.force_authenticate(user=user)
    response = api_client.post('/api/register-fcm-token', {
        "token": "valid_token_123",
        "device_id": "phone_a"
    })
    assert response.status_code == 200
    assert FCMToken.objects.filter(user=user, token="valid_token_123").exists()
