import sys
import os
import django

sys.path.append(os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'sabina_chess.settings')
django.setup()

from django.contrib.auth.models import User

users = User.objects.filter(username__in=['Sabina', 'Savyata'])
if not users.exists():
    print("Neither Sabina nor Savyata found.")
else:
    for u in users:
        print(f"User: {u.username}, Is Superuser: {u.is_superuser}, Is Staff: {u.is_staff}")
