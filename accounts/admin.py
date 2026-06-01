from django.contrib import admin
from .models import OTPVerification, FCMToken, RecordedCall

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
    list_display = ('caller', 'callee', 'date_time', 'call_type')
    search_fields = ('caller__username', 'callee__username')
    list_filter = ('date_time', 'call_type')
