
import json
from channels.generic.websocket import WebsocketConsumer


consumers = []

class SocketConsumer(WebsocketConsumer):
    def connect(self):
        self.accept()
        consumers.append(self)

    def disconnect(self, close_code):
        consumers.remove(self)
        pass

    def receive(self, text_data):
        data = json.loads(text_data)
        print(data)

    def sendDict(self, data):
        self.send(text_data=json.dumps(data))