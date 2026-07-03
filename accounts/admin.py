from django.contrib import admin
from django.utils.html import format_html
from .models import OTPVerification, FCMToken, RecordedCall, NotificationLog, ClientLog

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
    list_display = ('caller_name', 'receiver_name', 'date_time', 'call_type', 'recording_link')
    search_fields = ('caller__username', 'callee__username')
    list_filter = ('date_time', 'call_type')
    readonly_fields = ('date_time', 'recording_link')

    @admin.display(description='Caller')
    def caller_name(self, obj):
        return obj.caller.username if obj.caller else '—'

    @admin.display(description='Received By')
    def receiver_name(self, obj):
        return obj.callee.username if obj.callee else '—'

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
    list_display = ('sent_by', 'received_by', 'title', 'notification_type', 'colored_status', 'sent_at', 'accepted_at')
    list_filter = ('status', 'notification_type', 'sent_at')
    search_fields = ('user__username', 'sender__username', 'title')
    readonly_fields = ('id', 'sent_at', 'accepted_at')

    @admin.display(description='Sent By')
    def sent_by(self, obj):
        return obj.sender.username if obj.sender else '🔧 System'

    @admin.display(description='Received By')
    def received_by(self, obj):
        return obj.user.username

    @admin.display(description='Status')
    def colored_status(self, obj):
        colors = {
            'failed': '#7f8c8d',
            'sent': '#3498db',
            'delivered': '#f39c12',
            'opened': '#2ecc71',
            'dismissed': '#95a5a6',
            'blocked': '#e74c3c',
        }
        color = colors.get(obj.status, '#ffffff')
        return format_html(
            '<span style="color:{}; font-weight:bold;">{}</span>',
            color, obj.get_status_display()
        )


@admin.register(ClientLog)
class ClientLogAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'colored_level', 'feature', 'user', 'message_summary')
    list_filter = ('level', 'feature', 'created_at')
    search_fields = ('message', 'stack_trace', 'user__username', 'feature')
    readonly_fields = ('created_at', 'user', 'level', 'feature', 'message', 'stack_trace', 'device_info')
    date_hierarchy = 'created_at'

    @admin.display(description='Level')
    def colored_level(self, obj):
        colors = {
            'DEBUG': '#7f8c8d',
            'INFO': '#2ecc71',
            'WARNING': '#f39c12',
            'ERROR': '#e74c3c',
            'FATAL': '#c0392b',
        }
        color = colors.get(obj.level, '#ffffff')
        return format_html(
            '<span style="background-color:{}; color:#ffffff; padding:3px 6px; border-radius:3px; font-weight:bold;">{}</span>',
            color, obj.level
        )

    def message_summary(self, obj):
        return obj.message[:80] + '...' if len(obj.message) > 80 else obj.message
    message_summary.short_description = 'Message'

