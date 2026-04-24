import sys
import os
import django

sys.path.append(os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'sabina_chess.settings')
django.setup()

from django.contrib.auth.models import User
from accounts.models import OTPVerification

print("--- Users in DB ---")
for u in User.objects.all().order_by('-date_joined')[:10]:
    otp_rec = OTPVerification.objects.filter(user=u).first()
    otp_str = otp_rec.otp if otp_rec else "NONE"
    print(f"Username: {u.username}, Email: {u.email}, Active: {u.is_active}, OTP: {otp_str}, Joined: {u.date_joined}")
