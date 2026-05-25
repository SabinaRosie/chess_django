from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework import status
from django.http import FileResponse, Http404, StreamingHttpResponse
from django.shortcuts import get_object_or_404
from .models import GameVideo, VideoComment, VideoReaction
from .serializers import GameVideoSerializer, VideoCommentSerializer
import os
import mimetypes


@api_view(['GET'])
@permission_classes([AllowAny])
def list_videos(request):
    """List all available videos"""
    # Auto-heal: fix videos with duration=0
    zero_duration_videos = GameVideo.objects.filter(duration=0)
    for video in zero_duration_videos:
        if video.video_file:
            try:
                import cloudinary.api
                public_id = str(video.video_file)
                print(f"Auto-heal: attempting for '{video.title}', public_id='{public_id}'")
                result = cloudinary.api.resource(public_id, resource_type='video')
                duration = int(float(result.get('duration', 0)))
                file_size = result.get('bytes', 0)
                print(f"Auto-heal: got duration={duration}, file_size={file_size}")
                if duration > 0:
                    GameVideo.objects.filter(pk=video.pk).update(duration=duration, file_size=file_size)
                    print(f"Auto-heal: updated '{video.title}' successfully")
            except Exception as e:
                print(f"Auto-heal failed for '{video.title}': {type(e).__name__}: {e}")

    videos = GameVideo.objects.all()
    serializer = GameVideoSerializer(videos, many=True, context={'request': request})
    return Response(serializer.data)


@api_view(['GET'])
@permission_classes([AllowAny])
def get_video_detail(request, video_id):
    """Get details of a specific video"""
    video = get_object_or_404(GameVideo, id=video_id)
    
    # Increment view count
    video.views += 1
    video.save(update_fields=['views'])
    
    serializer = GameVideoSerializer(video, context={'request': request})
    return Response(serializer.data)


class RangeFileWrapper:
    """Wrapper to support range requests for video streaming"""
    def __init__(self, filelike, blksize=8192, offset=0, length=None):
        self.filelike = filelike
        self.filelike.seek(offset, os.SEEK_SET)
        self.remaining = length
        self.blksize = blksize

    def __iter__(self):
        return self

    def __next__(self):
        if self.remaining is None:
            data = self.filelike.read(self.blksize)
            if data:
                return data
            raise StopIteration
        else:
            if self.remaining <= 0:
                raise StopIteration
            data = self.filelike.read(min(self.remaining, self.blksize))
            if not data:
                raise StopIteration
            self.remaining -= len(data)
            return data


@api_view(['GET'])
@permission_classes([AllowAny])
def stream_video(request, video_id):
    """
    Proxy stream to Cloudinary URL.
    Direct redirect causes issues with some Android devices (Xiaomi ExoPlayer).
    """
    video = get_object_or_404(GameVideo, id=video_id)
    
    if not video.video_file:
        raise Http404("Video file not found")
    
    # Get the Cloudinary URL
    cloudinary_url = video.video_file.url

    # CLOUDINARY HARDENING: Force 480p, H.264 Baseline 3.0, 1Mbps
    if 'video/upload/' in cloudinary_url:
        try:
            safe_profile = 'w_854,h_480,c_limit,q_auto,vc_h264:baseline:3.0,br_1m'
            from django.conf import settings
            cloud_name = getattr(settings, 'CLOUDINARY_STORAGE', {}).get('CLOUD_NAME') or "drxgymnwa"
            base_cloud = f"https://res.cloudinary.com/{cloud_name}"
            
            delimiter = 'video/upload/'
            _, rest = ("", cloudinary_url) if cloudinary_url.startswith(delimiter) else cloudinary_url.split(delimiter, 1)
            parts = [p for p in rest.split('/') if p]
            new_parts = [safe_profile]
            version = next((p for p in parts[:-1] if p.startswith('v') and p[1:].isdigit()), None)
            if version: new_parts.append(version)
            new_parts.append(parts[-1])
            cloudinary_url = f"{base_cloud}/video/upload/{'/'.join(new_parts)}"
        except:
            pass
    
    # Proxy the request to Cloudinary with range support
    import requests
    
    # Forward range headers if present
    headers = {}
    if 'HTTP_RANGE' in request.META:
        headers['Range'] = request.META['HTTP_RANGE']
    
    try:
        # Stream from Cloudinary
        cloudinary_response = requests.get(cloudinary_url, headers=headers, stream=True)
        
        # Create streaming response
        response = StreamingHttpResponse(
            cloudinary_response.iter_content(chunk_size=8192),
            content_type=cloudinary_response.headers.get('Content-Type', 'video/mp4')
        )
        
        # Forward important headers
        if 'Content-Length' in cloudinary_response.headers:
            response['Content-Length'] = cloudinary_response.headers['Content-Length']
        if 'Content-Range' in cloudinary_response.headers:
            response['Content-Range'] = cloudinary_response.headers['Content-Range']
        if 'Accept-Ranges' in cloudinary_response.headers:
            response['Accept-Ranges'] = cloudinary_response.headers['Accept-Ranges']
        
        response.status_code = cloudinary_response.status_code
        return response
        
    except requests.RequestException as e:
        raise Http404(f"Error streaming video: {str(e)}")


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def upload_video(request):
    """Upload a new video (admin only)"""
    if not request.user.is_staff:
        return Response(
            {"error": "Only administrators can upload videos"},
            status=status.HTTP_403_FORBIDDEN
        )
    
    serializer = GameVideoSerializer(data=request.data, context={'request': request})
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def delete_video(request, video_id):
    """Delete a video (admin only)"""
    if not request.user.is_staff:
        return Response(
            {"error": "Only administrators can delete videos"},
            status=status.HTTP_403_FORBIDDEN
        )
    
    video = get_object_or_404(GameVideo, id=video_id)
    
    # Delete from Cloudinary
    if video.video_file:
        import cloudinary.uploader
        # CloudinaryField stores the public_id
        try:
            cloudinary.uploader.destroy(video.video_file.public_id, resource_type='video')
        except Exception as e:
            print(f"Error deleting video from Cloudinary: {e}")

    if video.thumbnail:
        import cloudinary.uploader
        try:
            cloudinary.uploader.destroy(video.thumbnail.public_id)
        except Exception as e:
            print(f"Error deleting thumbnail from Cloudinary: {e}")
    
    video.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def video_comments(request, video_id):
    """List or add comments for a video"""
    if request.method == 'GET':
        comments = VideoComment.objects.filter(video_id=video_id)
        serializer = VideoCommentSerializer(comments, many=True)
        return Response(serializer.data)
    
    elif request.method == 'POST':
        video = get_object_or_404(GameVideo, id=video_id)
        serializer = VideoCommentSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(user=request.user, video=video)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def toggle_reaction(request, video_id):
    """Toggle a reaction for a video"""
    video = get_object_or_404(GameVideo, id=video_id)
    reaction_type = request.data.get('reaction_type')
    
    if not reaction_type:
        return Response({"error": "reaction_type is required"}, status=status.HTTP_400_BAD_REQUEST)
        
    # Check if reaction already exists
    reaction = VideoReaction.objects.filter(video=video, user=request.user).first()
    
    if reaction:
        if reaction.reaction_type == reaction_type:
            # If same reaction, remove it (toggle off)
            reaction.delete()
            status_code = status.HTTP_200_OK
        else:
            # If different reaction, update it
            reaction.reaction_type = reaction_type
            reaction.save()
            status_code = status.HTTP_200_OK
    else:
        # Create new reaction
        VideoReaction.objects.create(video=video, user=request.user, reaction_type=reaction_type)
        status_code = status.HTTP_201_CREATED

    # Refresh counts and user reaction after change
    # CRITICAL: refresh_from_db ensures related managers (reactions) are up to date
    video.refresh_from_db()
    serializer = GameVideoSerializer(video, context={'request': request})
    return Response({
        "status": "success",
        "video": serializer.data
    }, status=status.HTTP_200_OK if 'status_code' not in locals() else status_code)


@api_view(['POST'])
@permission_classes([AllowAny])
def update_video_duration(request, video_id):
    """Update video duration (called by frontend when Cloudinary returns 0)"""
    video = get_object_or_404(GameVideo, id=video_id)
    duration = request.data.get('duration', 0)
    try:
        duration = int(float(duration))
    except (ValueError, TypeError):
        return Response({"error": "Invalid duration"}, status=status.HTTP_400_BAD_REQUEST)

    if duration > 0 and video.duration == 0:
        GameVideo.objects.filter(pk=video.pk).update(duration=duration)
        return Response({"status": "updated", "duration": duration})
    return Response({"status": "no_update_needed", "duration": video.duration})
