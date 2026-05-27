# Re-export from the new location for backward compatibility.
# The original fcm_utils.py was moved to accounts/notifications/utils.py during refactoring.
from .notifications.utils import send_push_notification

__all__ = ['send_push_notification']
