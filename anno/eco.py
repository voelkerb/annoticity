from decouple import config
SMART_ENERGY_TOOLS_PATH = config('SMART_ENERGY_TOOLS_PATH')

import sys, os
sys.path.insert(0, os.path.join(SMART_ENERGY_TOOLS_PATH))
from datasets.ECO import ecoLoader as eco


import numpy as np 
from datetime import datetime

from .websocket import wsManager
from . import chart
from . import data as dataHp

from django.http import JsonResponse

from measurement.usefulFunctions import time_format_ymdhms

from .powerData import dataManager as dm

eco.BASE_PATH = config('ECO_BASE_PATH')

def info():
    houses = eco.getHouses()
    ecoInfo = {"house":[{"name":h} for h in houses]}
    for i,h in enumerate(houses):
        meters = eco.getMeters(h)
        ecoInfo["house"][i]["meter"] = [{"name":str(m) + ": " + eco.getDevice(h, m), "value":m} for m in meters]

    # ecoInfo = {}
    # for h in houses:
    #     meters = eco.getMeters(h)
    #     mapping = {m:eco.getDevice(h, m) for m in meters}
    #     ecoInfo[h] = {"meters":meters, "mapping": mapping}
    return ecoInfo

def getInfo(request):
    return JsonResponse(info())

def getTimes(request, house, meter):
    h = int(house)
    m = int(meter)
    availability = eco.getTimeRange(h, m)
    response = {}
    response["ranges"] = availability
    return JsonResponse(response)

def loadData(house, meter, day, samplingrate=1):
    startDate = datetime.strptime(day, "%m_%d_%Y").replace(hour=0, minute=0, second=0, microsecond=0)

    dataDict = eco.load(int(house), int(meter), startDate)
    if dataDict is not None and samplingrate != dataDict["samplingrate"]:
        dataDict["data"] = dataHp.resample(dataDict["data"], dataDict["samplingrate"], samplingrate)
        dataDict["samplingrate"] = samplingrate
        dataDict["samples"] = len(dataDict["data"])
    dataDict["tz"] = eco.getTimeZone().zone
    dataDict["tsIsUTC"] = False
    return dataDict

# Register data provider
dataHp.dataProvider["eco"] = loadData

def initChart(request, house, meter, day):
    startDate = datetime.strptime(day, "%m_%d_%Y").replace(hour=0, minute=0, second=0, microsecond=0)
    response = {}
    sessionID = request.session.session_key
    wsManager.sendStatus(sessionID, "Loading ECO data...", percent=25)

    # Load the data
    dataDict = loadData(int(house), int(meter), day)
    wsManager.sendStatus(sessionID, "Preparing ...", percent=75)

    fp = "house_" + str(house) + "__" + "meter" + str(meter) + "__" + day + ".mkv"
    request.session["dataInfo"] = {"type":"eco", "filePath": fp, "args": (int(house), int(meter), day)}

    # add data to dataManager
    dm.add(sessionID, dataDict)
    # response = dataHp.responseForData(dataDict, measure=measure)
    response = chart.responseForInitChart(dataDict, measures=dataDict["measures"])
    return JsonResponse(response)

def getData(request, startTs, stopTs):
    chartData = {}

    dataDict = dm.get(request.session.session_key)

    if dataDict is not None:
        duration = stopTs - startTs
        
        dataDictCopy = dict((k,v) for k,v in dataDict.items() if k != "data")

        startSample = int((startTs-dataDict["timestamp"])*dataDict["samplingrate"])
        startSample = max(0, startSample)
        stopSample = int((stopTs-dataDict["timestamp"])*dataDict["samplingrate"])
        stopSample = min(len(dataDict["data"]), stopSample)
        dataDictCopy["data"] = dataDict["data"][startSample:stopSample]

        startTs = max(dataDictCopy["timestamp"], startTs)
        stopTs = min(dataDictCopy["timestamp"]+dataDictCopy["duration"], stopTs)

        chartData = chart.responseForData(dataDictCopy, dataDictCopy["measures"], startTs, stopTs)
  
    return JsonResponse(chartData)