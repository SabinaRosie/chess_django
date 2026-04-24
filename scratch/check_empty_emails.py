import sys
import os
import django

sys.path.append(os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'sabina_chess.settings')
django.setup()

from django.contrib.auth.models import User

users_no_email = User.objects.filter(email='')
print(f"Users with empty email: {users_no_email.count()}")
for u in users_no_email:
    print(f"  - Username: {u.username}")

users_null_email = User.objects.filter(email__isnull=True)
print(f"Users with null email: {users_null_email.count()}")
for u in users_null_email:
    print(f"  - Username: {u.username}")
