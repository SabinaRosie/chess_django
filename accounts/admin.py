from django.contrib import admin
from django.utils.html import format_html
from .models import OTPVerification, FCMToken, RecordedCall, NotificationLog

@admin.register(OTPVerification)
class OTPVerificationAdmin(admin.ModelAdmin):
    list_display = ('user', 'otp', 'created_at', 'is_verified')
    list_filter = ('is_verified',)
    readonly_fields = ('created_at',)

@admin.register(FCMToken)
class FCMTokenAdmin(admin.ModelAdmin):
    list_display = ('user', 'token', 'created_at', 'last_updated')
    search_fields = ('user__username', 'token')

@admin.register(RecordedCall)
class RecordedCallAdmin(admin.ModelAdmin):
    list_display = ('caller', 'callee', 'date_time', 'call_type', 'recording_link')
    search_fields = ('caller__username', 'callee__username')
    list_filter = ('date_time', 'call_type')
    readonly_fields = ('date_time', 'recording_link')

    @admin.display(description='Recording')
    def recording_link(self, obj):
        if obj.recording_file:
            return format_html(
                '<a href="{}" target="_blank" style="color:#00bfff;">▶ Play / Download</a>',
                obj.recording_file.url
            )
        return '— no file —'

@admin.register(NotificationLog)
class NotificationLogAdmin(admin.ModelAdmin):
    list_display = ('user', 'title', 'notification_type', 'status', 'sent_at', 'updated_at')
    list_filter = ('status', 'notification_type', 'sent_at')
    search_fields = ('user__username', 'title')
    readonly_fields = ('id', 'sent_at', 'updated_at')
