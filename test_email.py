import os
import django
from django.core.mail import send_mail

# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'sabina_chess.settings')
django.setup()

def test_email():
    try:
        print("Starting email test...")
        send_mail(
            'Test Email from Sabina Chess',
            'Congratulations! Your SMTP configuration is working perfectly.',
            None, # Uses DEFAULT_FROM_EMAIL
            ['niraulasabina08@gmail.com'],
            fail_silently=False,
        )
        print("SUCCESS: Email sent successfully! Please check your inbox.")
    except Exception as e:
        print(f"ERROR: Failed to send email: {e}")

if __name__ == "__main__":
    test_email()
