
from . import websocket
from django.urls import re_path

websocket_urlpatterns = [
    re_path(r'anno/ws', websocket.SocketConsumer),
    re_path(r'ben/ws', websocket.SocketConsumer),
]

