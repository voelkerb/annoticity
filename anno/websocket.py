
import json
from channels.generic.websocket import WebsocketConsumer


print("test")

class SocketConsumer(WebsocketConsumer):
    def connect(self):
        id = None
        if "cookies" in self.scope and "sessionid" in self.scope["cookies"]:
            id = self.scope["cookies"]["sessionid"]
        elif "cookies" in self.scope and "csrftoken" in self.scope["cookies"]:
            id = self.scope["cookies"]["csrftoken"]
        if id != None:
            self.accept()
            wsManager.addConsumer(id, self)
            print("added WS with id" + str(id))
        else:
            print("Cannot retrieve id from websocket" + str(self.scope))

    def disconnect(self, close_code):
        id = self.scope["cookies"]["sessionid"]
        wsManager.removeConsumer(id)
        pass

    def receive(self, text_data):
        data = json.loads(text_data)
        print(data)

    def sendDict(self, data):
        self.send(text_data=json.dumps(data))



class WebSocketManager(object):

    consumers = {}
    
    def addConsumer(self, id, consumer):
        self.consumers[id] = consumer

    def removeConsumer(self, id):
        del self.consumers[id]

    def sendDict(self, id, data):
        if id in self.consumers:
            self.consumers[id].sendDict(data)

    def sendStatus(self, id, text, percent=100):
        if id in self.consumers:
            self.consumers[id].sendDict({"status":text, "percent":percent})

    def sendMsg(self, id, msg):
        if id in self.consumers:
            self.consumers[id].sendDict({"msg":msg})
            
    def sendTask(self, id, task):
        if id in self.consumers:
            self.consumers[id].sendDict({"task":task})

wsManager = WebSocketManager()