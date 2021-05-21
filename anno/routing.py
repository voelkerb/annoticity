
from . import websocket
from django.urls import re_path

websocket_urlpatterns = [
    re_path(r'anno/ws', websocket.SocketConsumer.as_asgi()),
    re_path(r'ben/ws', websocket.SocketConsumer.as_asgi()),
]

