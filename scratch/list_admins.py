import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'sabina_chess.settings')
django.setup()

from django.contrib.auth.models import User

admin_users = User.objects.filter(is_superuser=True)
if admin_users.exists():
    print("Admin accounts found:")
    for u in admin_users:
        print(f" - Username: {u.username}")
else:
    print("No admin accounts found.")
