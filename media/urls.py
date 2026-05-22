from django.urls import path
from . import views

urlpatterns = [
    path('videos/', views.list_videos, name='list-videos'),
    path('videos/upload/', views.upload_video, name='upload-video'),
    path('videos/<int:video_id>/', views.get_video_detail, name='video-detail'),
    path('videos/<int:video_id>/stream/', views.stream_video, name='stream-video'),
    path('videos/<int:video_id>/delete/', views.delete_video, name='delete-video'),
    path('videos/<int:video_id>/comments/', views.video_comments, name='video-comments'),
    path('videos/<int:video_id>/reaction/', views.toggle_reaction, name='toggle-reaction'),
]
