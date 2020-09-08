
from . import websocket
from django.urls import re_path

websocket_urlpatterns = [
    re_path(r'ws/', websocket.SocketConsumer),
]

