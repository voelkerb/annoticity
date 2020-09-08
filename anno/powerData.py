

class PowerDataManager(object):
    pd = {}
    
    def add(self, id, dataDict):
        self.pd[id] = dataDict

    def get(self, id):
        if id not in self.pd: return None
        else: return self.pd[id] 

dataManager = PowerDataManager()
