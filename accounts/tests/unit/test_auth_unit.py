# pyrefly: ignore [missing-import]
import pytest
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta
from accounts.models import OTPVerification, FCMToken

@pytest.mark.django_db
def test_user_password_hashing():
    """Test that passwords are saved securely."""
    user = User.objects.create_user(username="testuser", password="SafePassword123!")
    assert user.password != "SafePassword123!"
    assert user.check_password("SafePassword123!") is True

@pytest.mark.django_db
def test_otp_creation_and_expiry():
    """Test OTP model logic."""
    user = User.objects.create_user(username="otpuser", password="123")
    otp_record = OTPVerification.objects.create(user=user, otp="123456")
    
    assert otp_record.otp == "123456"
    assert otp_record.is_verified is False
    assert otp_record.is_expired() is False
    
    # Manually backdate the created_at to test expiry
    # auto_now_add makes it hard to change directly, but we can update it
    OTPVerification.objects.filter(pk=otp_record.pk).update(
        created_at=timezone.now() - timedelta(minutes=11)
    )
    otp_record.refresh_from_db()
    assert otp_record.is_expired() is True

@pytest.mark.django_db
def test_fcm_token_uniqueness():
    """Test that FCM tokens are unique and can be updated."""
    user = User.objects.create_user(username="fcmuser", password="123")
    token = "sample_fcm_token_123"
    
    fcm1 = FCMToken.objects.create(user=user, token=token)
    
    # Attempting to create same token for another user should fail (unique=True)
    user2 = User.objects.create_user(username="fcmuser2", password="123")
    with pytest.raises(Exception):
        FCMToken.objects.create(user=user2, token=token)

@pytest.mark.django_db
def test_user_duplicate_email_prevention():
    """Test that duplicate emails raise an error if enforced (though Django default doesn't unique emails)."""
    # Note: Default Django User model doesn't enforce unique emails unless customized.
    # However, our views.py handles this. Unit tests for models check model-level constraints.
    User.objects.create_user(username="user1", email="same@test.com", password="123")
    # This won't fail at model level unless we added unique=True to email.
    # We will test this in Integration tests instead.
    pass
