from django.contrib import admin
from .models import GameVideo, VideoComment, VideoReaction

@admin.register(GameVideo)
class GameVideoAdmin(admin.ModelAdmin):
    list_display = ('title', 'duration', 'views', 'created_at')
    search_fields = ('title', 'description')
    readonly_fields = ('duration', 'file_size', 'views')

@admin.register(VideoComment)
class VideoCommentAdmin(admin.ModelAdmin):
    list_display = ('user', 'video', 'created_at')
    search_fields = ('text', 'user__username')

@admin.register(VideoReaction)
class VideoReactionAdmin(admin.ModelAdmin):
    list_display = ('user', 'video', 'reaction_type', 'created_at')
    list_filter = ('reaction_type',)
