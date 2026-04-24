import sys
import os
import django

sys.path.append(os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'sabina_chess.settings')
django.setup()

from django.contrib.auth.models import User
from django.db.models.functions import Lower
from django.db.models import Count

duplicates = User.objects.annotate(email_lower=Lower('email')).values('email_lower').annotate(count=Count('id')).filter(count__gt=1)

if duplicates.exists():
    print("Duplicate emails found (case-insensitive):")
    for d in duplicates:
        print(f"Email: {d['email_lower']}, Count: {d['count']}")
        users = User.objects.filter(email__iexact=d['email_lower'])
        for u in users:
            print(f"  - Username: {u.username}, Email in DB: {u.email}")
else:
    print("No duplicates found.")
