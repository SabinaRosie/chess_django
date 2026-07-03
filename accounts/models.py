from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta
import uuid

class OTPVerification(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='otp_records')
    otp = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    is_verified = models.BooleanField(default=False)
    used_at = models.DateTimeField(null=True, blank=True)  # Set when OTP is consumed

    def is_expired(self):
        # OTP expires after 10 minutes
        return timezone.now() > self.created_at + timedelta(minutes=10)

    def __str__(self):
        status = 'Used' if self.used_at else ('Verified' if self.is_verified else 'Pending')
        return f"{self.user.username} - {self.otp} [{status}]"


class CallRoom(models.Model):
    CALL_TYPES = [('audio', 'Audio'), ('video', 'Video')]
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('active', 'Active'),
        ('ended', 'Ended'),
        ('rejected', 'Rejected'),
    ]

    room_id = models.UUIDField(default=uuid.uuid4, unique=True)
    caller = models.ForeignKey(User, on_delete=models.CASCADE, related_name='calls_made')
    callee = models.ForeignKey(User, on_delete=models.CASCADE, related_name='calls_received')
    call_type = models.CharField(max_length=5, choices=CALL_TYPES, default='audio')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    offer_sdp = models.JSONField(null=True, blank=True)
    answer_sdp = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def is_expired(self):
        # Call room expires after 2 minutes if not answered
        return self.status == 'pending' and timezone.now() > self.created_at + timedelta(minutes=2)

    def __str__(self):
        return f"{self.caller.username} -> {self.callee.username} ({self.call_type})"

class RecordedCall(models.Model):
    caller = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='recorded_calls_made')
    callee = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='recorded_calls_received')
    date_time = models.DateTimeField(auto_now_add=True)
    recording_file = models.FileField(upload_to='call_recordings/', null=True, blank=True)
    call_type = models.CharField(max_length=50, default='unknown')

    def __str__(self):
        caller_name = self.caller.username if self.caller else "Unknown"
        callee_name = self.callee.username if self.callee else "Unknown"
        return f"{caller_name} - {callee_name} ({self.date_time})"


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


class Conversation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    participants = models.ManyToManyField(User, related_name='conversations')
    last_message_content = models.TextField(null=True, blank=True)
    last_message_time = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['last_message_time']),
        ]

    def __str__(self):
        return f"Conversation {self.id}"


class ChatMessage(models.Model):
    STATUS_CHOICES = [
        ('sent', 'Sent'),
        ('delivered', 'Delivered'),
        ('seen', 'Seen'),
    ]
    MESSAGE_TYPES = [
        ('text', 'Text'),
        ('image', 'Image'),
        ('video', 'Video'),
        ('file', 'File'),
    ]

    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='messages')
    sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sent_messages')
    content = models.TextField()
    message_type = models.CharField(max_length=10, choices=MESSAGE_TYPES, default='text')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='sent')
    created_at = models.DateTimeField(auto_now_add=True)
    is_deleted = models.BooleanField(default=False)
    replied_to = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='replies')
    is_forwarded = models.BooleanField(default=False)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['conversation', 'created_at']),
        ]

    def __str__(self):
        return f"{self.sender.username}: {self.content[:20]}"

class FCMToken(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='fcm_tokens')
    token = models.TextField(unique=True)
    device_id = models.CharField(max_length=255, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_updated = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username} - {self.token[:10]}"


class MessageReaction(models.Model):
    message = models.ForeignKey(ChatMessage, on_delete=models.CASCADE, related_name='reactions')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='reactions')
    emoji = models.CharField(max_length=10) # Store the emoji character
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('message', 'user', 'emoji')

    def __str__(self):
        return f"{self.user.username} reacted {self.emoji} to message {self.message.id}"


class GameInvitation(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('accepted', 'Accepted'),
        ('declined', 'Declined'),
        ('expired', 'Expired'),
        ('cancelled', 'Cancelled'),
    ]
    sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name='invitations_sent')
    receiver = models.ForeignKey(User, on_delete=models.CASCADE, related_name='invitations_received')
    game = models.ForeignKey('ChessGame', on_delete=models.SET_NULL, null=True, blank=True, related_name='invitation')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)

    def is_expired(self):
        return self.status == 'pending' and timezone.now() > self.created_at + timedelta(seconds=60)

    def __str__(self):
        return f"{self.sender.username} -> {self.receiver.username} ({self.status})"


class ChessGame(models.Model):
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('draw', 'Draw'),
        ('white_win', 'White Win'),
        ('black_win', 'Black Win'),
        ('aborted', 'Aborted'),
    ]
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    white_player = models.ForeignKey(User, on_delete=models.CASCADE, related_name='games_as_white')
    black_player = models.ForeignKey(User, on_delete=models.CASCADE, related_name='games_as_black')
    fen = models.TextField(default='rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1')
    pgn = models.TextField(blank=True, default='')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='active')
    created_at = models.DateTimeField(auto_now_add=True)
    last_move_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Game {self.id}: {self.white_player.username} vs {self.black_player.username}"


class ChessTip(models.Model):
    text = models.TextField()
    category = models.CharField(max_length=50, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Tip {self.id}: {self.text[:30]}"

class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    coins = models.PositiveIntegerField(default=100) # Starting coins for new users
    
    # Notification Preferences
    allow_calls = models.BooleanField(default=True)
    allow_messages = models.BooleanField(default=True)
    allow_invitations = models.BooleanField(default=True)
    allow_sticky = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.user.username} - {self.coins} coins"

# Signals to create/save UserProfile automatically
from django.db.models.signals import post_save
from django.dispatch import receiver

@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.create(user=instance)

@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    if hasattr(instance, 'profile'):
        instance.profile.save()
    else:
        UserProfile.objects.create(user=instance)

class NotificationLog(models.Model):
    STATUS_CHOICES = [
        ('failed', 'Failed'),
        ('sent', 'Sent'),
        ('delivered', 'Delivered'),
        ('opened', 'Opened'),
        ('dismissed', 'Dismissed'),
        ('blocked', 'Blocked'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    title = models.CharField(max_length=255)
    notification_type = models.CharField(max_length=50, default='general')
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='failed')
    sent_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username} - {self.title} ({self.status})"


class ClientLog(models.Model):
    LEVEL_CHOICES = [
        ('DEBUG', 'Debug'),
        ('INFO', 'Info'),
        ('WARNING', 'Warning'),
        ('ERROR', 'Error'),
        ('FATAL', 'Fatal'),
    ]

    user = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='client_logs'
    )
    level = models.CharField(max_length=10, choices=LEVEL_CHOICES, default='ERROR')
    feature = models.CharField(max_length=50, null=True, blank=True, db_index=True)
    message = models.TextField()
    stack_trace = models.TextField(null=True, blank=True)
    device_info = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"[{self.level}] {self.feature or 'Global'} - {self.message[:50]}"


