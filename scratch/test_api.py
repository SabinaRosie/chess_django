import requests
import json

BASE_URL = "http://127.0.0.1:8001/api"

def test_forgot_password():
    email = "niraulasabina08@gmail.com"
    print(f"Testing /forgot-password with {email}...")
    try:
        response = requests.post(f"{BASE_URL}/forgot-password", json={"email": email})
        print(f"Status: {response.status_code}")
        print(f"Body: {response.text}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_forgot_password()
