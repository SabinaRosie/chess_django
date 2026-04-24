import sys
import os
import django

sys.path.append(os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'sabina_chess.settings')
django.setup()

from rest_framework.test import APIRequestFactory
from accounts.views import signup

def test_signup_repro():
    factory = APIRequestFactory()
    # Try a username that we know doesn't exist (since we just deleted everyone)
    data = {
        'username': 'Savyata_New',
        'email': 'savyata308@gmail.com',
        'password': 'Password123!'
    }
    print(f"Attempting signup with {data}...")
    
    request = factory.post('/api/signup', data, format='json')
    response = signup(request)
    
    print(f"Status: {response.status_code}")
    print(f"Data: {response.data}")

if __name__ == "__main__":
    test_signup_repro()
