import sys
import os
import django

sys.path.append(os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'sabina_chess.settings')
django.setup()

from accounts.models import OTPVerification

print(f"Total OTPVerification records: {OTPVerification.objects.count()}")
for record in OTPVerification.objects.all():
    print(f"User: {record.user.email}, OTP: {record.otp}, Verified: {record.is_verified}, Created: {record.created_at}")
