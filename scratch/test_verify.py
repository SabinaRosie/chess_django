import sys
import os
import django
from rest_framework.test import APIRequestFactory

sys.path.append(os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'sabina_chess.settings')
django.setup()

import pytest
from accounts.views import verify_otp
from accounts.models import OTPVerification, User

@pytest.mark.django_db
def test_verify_repro():
    email = "niraulasabina08@gmail.com"
    # Create test data since pytest uses an empty database
    user = User.objects.create_user(username='repro_user_99', email=email, password='password123')
    otp_rec = OTPVerification.objects.create(user=user, otp='123456')
    otp = otp_rec.otp
    
    print(f"Attempting to verify {email} with OTP {otp}...")
    
    factory = APIRequestFactory()
    request = factory.post('/api/verify-otp', {
        'email': email,
        'otp': otp
    }, format='json')
    
    response = verify_otp(request)
    print(f"Status: {response.status_code}")
    print(f"Data: {response.data}")
    
    user.refresh_from_db()
    print(f"User Active: {user.is_active}")

if __name__ == "__main__":
    test_verify_repro()
