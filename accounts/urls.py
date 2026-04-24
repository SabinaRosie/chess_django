from django.urls import path
from .views import signup, login, forgot_password, verify_otp, reset_password, user_profile, logout_view, get_users

urlpatterns = [
    path('signup', signup),
    path('login', login),
    path('forgot-password', forgot_password),
    path('verify-otp', verify_otp),
    path('reset-password', reset_password),
    path('profile', user_profile),
    path('logout', logout_view),
    path('users', get_users),
]