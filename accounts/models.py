from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta
import uuid

class OTPVerification(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    otp = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    is_verified = models.BooleanField(default=False)

    def is_expired(self):
        # OTP expires after 10 minutes
        return timezone.now() > self.created_at + timedelta(minutes=10)

    def __str__(self):
        return f"{self.user.username} - {self.otp}"


class CallRoom(models.Model):
    CALL_TYPES = [('audio', 'Audio'), ('video', 'Video')]
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('active', 'Active'),
        ('ended', 'Ended'),
        ('rejected', 'Rejected'),
    ]

    room_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    caller = models.ForeignKey(User, on_delete=models.CASCADE, related_name='calls_made')
    callee = models.ForeignKey(User, on_delete=models.CASCADE, related_name='calls_received')
    call_type = models.CharField(max_length=5, choices=CALL_TYPES, default='audio')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)

    def is_expired(self):
        # Call room expires after 2 minutes if not answered
        return self.status == 'pending' and timezone.now() > self.created_at + timedelta(minutes=2)

    def __str__(self):
        return f"{self.caller.username} -> {self.callee.username} ({self.call_type})"


class CallSignal(models.Model):
    SIGNAL_TYPES = [
        ('offer', 'Offer'),
        ('answer', 'Answer'),
        ('candidate', 'ICE Candidate'),
    ]

    room = models.ForeignKey(CallRoom, on_delete=models.CASCADE, related_name='signals')
    sender = models.ForeignKey(User, on_delete=models.CASCADE)
    signal_type = models.CharField(max_length=10, choices=SIGNAL_TYPES)
    data = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.sender.username} - {self.signal_type} in {self.room.room_id}"

