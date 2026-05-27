from django.urls import path
from . import views
from . import voice_views

urlpatterns = [
    path('videos/', views.list_videos, name='list-videos'),
    path('videos/upload/', views.upload_video, name='upload-video'),
    path('videos/<int:video_id>/', views.get_video_detail, name='video-detail'),
    path('videos/<int:video_id>/stream/', views.stream_video, name='stream-video'),
    path('videos/<int:video_id>/delete/', views.delete_video, name='delete-video'),
    path('videos/<int:video_id>/comments/', views.video_comments, name='video-comments'),
    path('videos/<int:video_id>/reaction/', views.toggle_reaction, name='toggle-reaction'),
    path('videos/<int:video_id>/update-duration/', views.update_video_duration, name='update-video-duration'),

    # Voice AI endpoints
    path('voice/upload/', voice_views.upload_voice_samples, name='upload_voice'),
    path('voice/delete/', voice_views.delete_voice_profile, name='delete_voice'),
    path('voice/chat_with_self/', voice_views.chat_with_self, name='chat_self'),
    path('voice/status/', voice_views.get_voice_status, name='voice_status'),
]
