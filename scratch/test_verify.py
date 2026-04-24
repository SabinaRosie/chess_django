import sys
import os
import django
from rest_framework.test import APIRequestFactory

sys.path.append(os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'sabina_chess.settings')
django.setup()

from accounts.views import verify_otp
from accounts.models import OTPVerification, User

def test_verify_repro():
    email = "niraulasabina08@gmail.com"
    user = User.objects.get(email=email, username__startswith='repro_user')
    otp_rec = OTPVerification.objects.get(user=user)
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
