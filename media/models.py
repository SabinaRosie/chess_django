from django.db import models
from django.conf import settings
from cloudinary.models import CloudinaryField
import cloudinary.api

class GameVideo(models.Model):
    """Stores chess tutorial/gameplay videos"""
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    video_file = CloudinaryField('video', resource_type='video')
    thumbnail = CloudinaryField('image', null=True, blank=True)
    duration = models.IntegerField(help_text="Duration in seconds", default=0)
    file_size = models.BigIntegerField(help_text="File size in bytes", default=0)
    views = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        db_table = 'call_gamevideo'

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        # Check if a new file is being uploaded
        is_upload = hasattr(self.video_file, 'file')
        super().save(*args, **kwargs)

        # After saving, if it was an upload, fetch the video metadata from Cloudinary
        if is_upload and self.video_file:
            try:
                public_id = self.video_file.public_id
                # Fetch metadata from Cloudinary API
                result = cloudinary.api.resource(public_id, resource_type='video')
                
                updated = False
                if 'duration' in result:
                    self.duration = int(result['duration'])
                    updated = True
                if 'bytes' in result:
                    self.file_size = result['bytes']
                    updated = True
                    
                if updated:
                    # Update without calling save() again to avoid recursion
                    GameVideo.objects.filter(pk=self.pk).update(
                        duration=self.duration,
                        file_size=self.file_size
                    )
            except Exception as e:
                print(f"Failed to fetch video metadata from Cloudinary: {e}")

class VideoComment(models.Model):
    video = models.ForeignKey(GameVideo, on_delete=models.CASCADE, related_name='comments')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        db_table = 'call_videocomment'

    def __str__(self):
        return f"Comment by {self.user} on {self.video}"

class VideoReaction(models.Model):
    REACTION_TYPES = [
        ('like', 'Like'),
        ('heart', 'Heart'),
        ('laugh', 'Laugh'),
        ('surprised', 'Surprised'),
        ('sad', 'Sad'),
        ('angry', 'Angry'),
    ]
    video = models.ForeignKey(GameVideo, on_delete=models.CASCADE, related_name='reactions')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    reaction_type = models.CharField(max_length=20, choices=REACTION_TYPES)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('video', 'user')
        db_table = 'call_videoreaction'

    def __str__(self):
        return f"{self.user} reacted {self.reaction_type} to {self.video}"
