from django.contrib import admin
from .models import OTPVerification

@admin.register(OTPVerification)
class OTPVerificationAdmin(admin.ModelAdmin):
    list_display = ('user', 'otp', 'created_at', 'is_verified')
    list_filter = ('is_verified',)
    readonly_fields = ('created_at',)
