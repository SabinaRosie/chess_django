from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from .views import (
    signup, login, forgot_password, verify_otp, reset_password,
    user_profile, logout_view, get_users, test_email,
    create_call, check_incoming, answer_call, send_signal, get_signals, end_call,
    get_turn_credentials,
)
from . import chat_views

urlpatterns = [
    path('signup', signup),
    path('login', login),
    path('forgot-password', forgot_password),
    path('verify-otp', verify_otp),
    path('reset-password', reset_password),
    path('profile', user_profile),
    path('logout', logout_view),
    path('users', get_users),
    path('token/refresh', TokenRefreshView.as_view()),
    path('test-email', test_email),

    # WebRTC Call Signaling
    path('call/create', create_call),
    path('call/check-incoming', check_incoming),
    path('call/answer', answer_call),
    path('call/signal', send_signal),
    path('call/signals', get_signals),
    path('call/end', end_call),
    path('call/turn-credentials', get_turn_credentials),
    
    # Chat Endpoints
    path('chat/conversations', chat_views.list_conversations),
    path('chat/messages/<uuid:conversation_id>', chat_views.get_messages),
    path('chat/start', chat_views.start_conversation),
    path('chat/seen/<uuid:conversation_id>', chat_views.mark_as_seen),
]