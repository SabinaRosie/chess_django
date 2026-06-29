from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from .auth import views as auth_views
from .call import views as call_views
from .chat import views as chat_views
from .game import views as game_views
from .notifications import views as notifications_views
from .tips import views as tips_views

urlpatterns = [
    # Auth Endpoints
    path('signup', auth_views.signup),
    path('login', auth_views.login),
    path('forgot-password', auth_views.forgot_password),
    path('verify-otp', auth_views.verify_otp),
    path('reset-password', auth_views.reset_password),
    path('profile', auth_views.user_profile),
    path('logout', auth_views.logout_view),
    path('users', auth_views.get_users),
    path('token/refresh', TokenRefreshView.as_view()),
    path('test-email', auth_views.test_email),
    
    # Tips Endpoints
    path('chess-tip', tips_views.get_random_tip),

    # WebRTC Call Signaling
    path('call/create', call_views.create_call),
    path('call/check-incoming', call_views.check_incoming),
    path('call/answer', call_views.answer_call),
    path('call/signal', call_views.send_signal),
    path('call/signals', call_views.get_signals),
    path('call/end', call_views.end_call),
    path('call/turn-credentials', call_views.get_turn_credentials),
    path('call/recordings/save', call_views.save_recording),
    
    # Chat Endpoints
    path('chat/conversations', chat_views.list_conversations),
    path('chat/messages/<uuid:conversation_id>', chat_views.get_messages),
    path('chat/start', chat_views.start_conversation),
    path('chat/seen/<uuid:conversation_id>', chat_views.mark_as_seen),
    path('chat/messages/<int:message_id>/reactions', chat_views.toggle_reaction),
    path('chat/messages/<int:message_id>/delete', chat_views.delete_message),
    path('chat/forward', chat_views.forward_message),
    
    # Notifications
    path('register-fcm-token', notifications_views.register_fcm_token),
    path('notifications/track', notifications_views.track_notification),
    path('notifications/settings', notifications_views.notification_settings),

    # Client Logs
    path('logs/submit', auth_views.submit_client_logs),

    # Game Endpoints

    path('game/users', game_views.list_users),
    path('game/invite', game_views.send_invitation),
    path('game/respond', game_views.respond_invitation),
    path('game/cancel', game_views.cancel_invitation),
    path('game/invitations/pending', game_views.list_pending_invitations),
    path('game/invitations/sent', game_views.list_sent_invitations),
    path('game/invitation/<int:invitation_id>/status', game_views.get_invitation_status),
]
