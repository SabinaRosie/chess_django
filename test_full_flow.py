import requests
import json
import time

BASE_URL = "http://127.0.0.1:8000/api"

def test_full_auth_flow():
    email = "niraulasabina08@gmail.com"
    username = f"testuser_{int(time.time())}"
    password = "SafePassword123!"

    print(f"--- 1. Testing Signup for {username} ---")
    signup_res = requests.post(f"{BASE_URL}/signup", json={
        "username": username,
        "email": email,
        "password": password
    })
    print(f"Signup Response: {signup_res.status_code} - {signup_res.json()}")
    
    if signup_res.status_code != 200:
        print("Signup failed. Check if server is running.")
        return

    print("\n--- 2. Please check your console/email for the OTP ---")
    # In a real test, we'd need to fetch the OTP from the DB since we can't read the console
    # But since I have access to the DB, I can query it!
    
    print("\n--- 3. Fetching OTP from Database for verification ---")
    import os
    import django
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'sabina_chess.settings')
    django.setup()
    from accounts.models import OTPVerification, User
    
    user = User.objects.get(username=username)
    otp_record = OTPVerification.objects.get(user=user)
    otp = otp_record.otp
    print(f"Extracted OTP: {otp}")

    print("\n--- 4. Testing OTP Verification ---")
    verify_res = requests.post(f"{BASE_URL}/verify-otp", json={
        "email": email,
        "otp": otp
    })
    print(f"Verify Response: {verify_res.status_code} - {verify_res.json()}")

    print("\n--- 5. Testing Login ---")
    login_res = requests.post(f"{BASE_URL}/login", json={
        "username": username,
        "password": password
    })
    print(f"Login Response: {login_res.status_code} - {login_res.json()}")

    if login_res.status_code == 200:
        print("\n✅ SUCCESS: Full Auth Flow (Signup -> Verify -> Login) is WORKING!")
    else:
        print("\n❌ FAILURE: Login failed after verification.")

if __name__ == "__main__":
    test_full_auth_flow()
