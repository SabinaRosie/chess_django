import sys
import os
import django
import time

sys.path.append(os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'sabina_chess.settings')
django.setup()

from rest_framework.test import APIRequestFactory
from accounts.views import signup
from django.contrib.auth.models import User

def test_signup_logic():
    factory = APIRequestFactory()
    username = f"repro_user_{int(time.time())}"
    email = "niraulasabina08@gmail.com"
    password = "ReproPassword123!"
    
    print(f"Testing signup with username: {username}")
    
    # Clean up if user exists from previous failed run
    User.objects.filter(username=username).delete()
    User.objects.filter(email=email).delete() # Caution: this deletes other test users too
    
    request = factory.post('/api/signup', {
        'username': username,
        'email': email,
        'password': password
    }, format='json')
    
    try:
        response = signup(request)
        print(f"Status Code: {response.status_code}")
        print(f"Data: {response.data}")
    except Exception as e:
        print(f"CAUGHT EXCEPTION: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_signup_logic()
