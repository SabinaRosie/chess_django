import sys
import os
import django

sys.path.append(os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'sabina_chess.settings')
django.setup()

from django.contrib.auth.models import User
from django.db.models import Count

duplicates = User.objects.values('email').annotate(email_count=Count('email')).filter(email_count__gt=1)

if duplicates.exists():
    print("Users with duplicate emails found:")
    for entry in duplicates:
        email = entry['email']
        count = entry['email_count']
        users = User.objects.filter(email=email)
        print(f"Email: {email}, Count: {count}")
        for u in users:
            print(f"  - Username: {u.username}")
else:
    print("No duplicate emails found.")
