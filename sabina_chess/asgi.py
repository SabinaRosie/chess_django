import os
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from accounts.middleware import JWTAuthMiddleware
import accounts.routing

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'sabina_chess.settings')

application = ProtocolTypeRouter({
    "http": get_asgi_application(),
    "websocket": JWTAuthMiddleware(
        URLRouter(
            accounts.routing.websocket_urlpatterns
        )
    ),
})
