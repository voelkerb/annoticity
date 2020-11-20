from decouple import config
SMART_ENERGY_TOOLS_PATH = config('SMART_ENERGY_TOOLS_PATH')

import sys, os
sys.path.insert(0, os.path.join(SMART_ENERGY_TOOLS_PATH))
from datasets.UK_DALE import uk_daleLoader as ukdale

import numpy as np 
from datetime import datetime
import pytz

from .websocket import wsManager
from . import chart
from . import data as dataHp

from django.http import JsonResponse

from measurement.usefulFunctions import time_format_ymdhms

from .powerData import dataManager as dm

ukdale.BASE_PATH = config('UKDALE_BASE_PATH')



def info():
    if not os.path.exists(ukdale.BASE_PATH): return {}
    houses = ukdale.getHouses()
    mapping = ukdale.loadMapping()
    ukdaleInfo = {"house": [{"name":  int(h.lstrip("building"))} for h in houses]}
    for i, h in enumerate(houses):
        meters = ukdale.getMeters(h)
        ukdaleInfo["house"][i]["meter"] = [{"name": str(m) + ": " + mapping[str(h)][str(m)], "value":m} for m in meters]
    # ukdaleInfo = {h:{"meters": ukdale.getMeters(h), "mapping": mapping[h]} for h in houses}
    
    return ukdaleInfo

def getInfo(request):
    return JsonResponse(info())

def getTimes(request, house, meter):
    availability = ukdale.loadAvailability()
    response = {}
    if house in availability and meter in availability[house]:
        response["ranges"] = availability[house][meter]

        # Map this to timezone unaware UTC Stuff
        # -> E.g. if it was 0-24 it is mapped to 0-24 on this day as utc timestamps   
        newRanges = []
        for r in response["ranges"]:
            startTs = r[0]
            stopTs = r[1]
            date = datetime.fromtimestamp(startTs, pytz.UTC).astimezone(ukdale.getTimeZone())
            startTs = startTs + date.utcoffset().total_seconds()
            stopTs = stopTs + date.utcoffset().total_seconds()
            newRanges.append([startTs, stopTs])
        response["ranges"] = newRanges

    return JsonResponse(response)

def loadData(house, meter, day, samplingrate=1):
    startDate = datetime.strptime(day, "%m_%d_%Y").replace(hour=0, minute=0, second=0, microsecond=0)
    tz = ukdale.getTimeZone()
    startDate = tz.localize(startDate)

    startTs = startDate.timestamp()
    stopTs = startTs + 60*60*24
    
    dataDict = ukdale.load(house, meter, startDate)

    startTs = float(dataDict["ts"][0])
    stopTs = float(dataDict["ts"][-1])
    newX = np.arange(startTs, stopTs, 1/samplingrate)
    data = np.recarray(len(newX), dtype=np.dtype([(m,np.float32) for m in dataDict["measures"]]))
    # Convert to one hz
    for m in dataDict["measures"]: 
        data[m] = np.interp(newX, dataDict["ts"], dataDict["data"][m])
    dataDict["data"] = data
    dataDict["tz"] = tz.zone
    dataDict["timestamp"] = startTs
    dataDict["duration"] = len(data)/samplingrate
    dataDict["samplingrate"] = samplingrate
    del dataDict["ts"]
    return dataDict

# Register data provider
dataHp.dataProvider["ukdale"] = loadData

def initChart(request, house, meter, day):
    sessionID = request.session.session_key
    wsManager.sendStatus(sessionID, "Loading UK-DALE data...", percent=25)
    # Load the data
    dataDict = loadData(house, meter, day)
    wsManager.sendStatus(sessionID, "Preparing ...", percent=75)

    # Set global session data
    fp = "house_" + str(house) + "__" + "meter_" + str(meter) + "__" + day + ".mkv"
    request.session["dataInfo"] = {"type":"ukdale", "filePath": fp, "args": (house, meter, day)}
    # add data to dataManager
    dm.add(sessionID, dataDict)

    # Generate data response
    response = chart.responseForInitChart(dataDict, measures=dataDict["measures"])
    response['date'] = day.replace("_", "/")
    response["filename"] = fp
    return JsonResponse(response)

def getData(request, startTs, stopTs):
    chartData = {}

    # Get data from dataManager
    dataDict = dm.get(request.session.session_key)
    
    if dataDict is not None: 
        duration = stopTs - startTs
        # We only have 1Hz data remember?
        if duration < 5.0: 
            duration = 5.0
            stopTs = startTs + duration
        
        dataDictCopy = dict((k,v) for k,v in dataDict.items() if k != "data")
        # TODO: MAKE THIS WORK WITH original timestamps
        startSample = int((startTs-dataDict["timestamp"])*dataDict["samplingrate"])
        startSample = max(0, startSample)
        stopSample = int((stopTs-dataDict["timestamp"])*dataDict["samplingrate"])
        stopSample = min(len(dataDict["data"]), stopSample)
        dataDictCopy["data"] = dataDict["data"][startSample:stopSample]

        startTs = max(dataDictCopy["timestamp"], startTs)
        stopTs = min(dataDictCopy["timestamp"]+dataDictCopy["duration"], stopTs)

        chartData = chart.responseForData(dataDictCopy, dataDictCopy["measures"], startTs, stopTs)
        
    return JsonResponse(chartData)
