# mysite/routing.py
from anno import websocket
from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
import anno.routing
from django.urls import path

application = ProtocolTypeRouter({
    # (http->django views is added by default)
    'websocket': AuthMiddlewareStack(
        URLRouter(
            anno.routing.websocket_urlpatterns
        )
    ),
})
