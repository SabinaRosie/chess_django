from django.core.management.base import BaseCommand
import cloudinary.api
from media.models import GameVideo


class Command(BaseCommand):
    help = 'Re-fetch video duration and file_size from Cloudinary for all videos'

    def handle(self, *args, **options):
        videos = GameVideo.objects.all()
        self.stdout.write(f"Found {videos.count()} videos to update...")

        for video in videos:
            if not video.video_file:
                self.stdout.write(self.style.WARNING(f"  Skipping '{video.title}' - no video file"))
                continue

            try:
                public_id = video.video_file.public_id
                result = cloudinary.api.resource(public_id, resource_type='video')

                duration = int(result.get('duration', 0))
                file_size = result.get('bytes', 0)

                GameVideo.objects.filter(pk=video.pk).update(
                    duration=duration,
                    file_size=file_size,
                )
                self.stdout.write(self.style.SUCCESS(
                    f"  Updated '{video.title}': duration={duration}s, size={file_size} bytes"
                ))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"  Failed for '{video.title}': {e}"))

        self.stdout.write(self.style.SUCCESS("Done!"))
