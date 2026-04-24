import sys
import os
import django

sys.path.append(os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'sabina_chess.settings')
django.setup()

from rest_framework.test import APIRequestFactory
from rest_framework.response import Response
from accounts.views import forgot_password
from django.contrib.auth.models import User

def test_forgot_password_logic():
    factory = APIRequestFactory()
    
    # Use an existing email from the DB
    # Based on our dump: niraulasabina08@gmail.com
    email = "niraulasabina08@gmail.com"
    
    print(f"Testing forgot_password with email: {email}")
    request = factory.post('/api/forgot-password', {'email': email}, format='json')
    
    try:
        response = forgot_password(request)
        print(f"Status Code: {response.status_code}")
        print(f"Data: {response.data}")
    except Exception as e:
        print(f"CAUGHT EXCEPTION: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_forgot_password_logic()
