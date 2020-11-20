from decouple import config
SMART_ENERGY_TOOLS_PATH = config('SMART_ENERGY_TOOLS_PATH')
import sys, os
sys.path.insert(0, os.path.join(SMART_ENERGY_TOOLS_PATH))
from datasets.REDD import reddLoader as redd

import numpy as np 
from datetime import datetime, timedelta
import pytz

from .websocket import wsManager
from . import chart
from . import data as dataHp

from django.http import JsonResponse

from measurement.usefulFunctions import time_format_ymdhms

from .powerData import dataManager as dm

redd.BASE_PATH = config('REDD_BASE_PATH')


def info():
    houses = redd.getAvailableHouses()
    reddInfo = {'house':[{"name":h} for h in houses]}
    for i,h in enumerate(houses):
        channels = redd.getAvailableChannels(h)
        labels = redd.loadLabels(h)
        reddInfo["house"][i]["channel"] = [{"name":str(m) + ": " + labels["channel_"+str(m)], "value":m} for m in channels]

    # reddInfo = {h:{"channels": redd.getAvailableChannels(h), "mapping": redd.loadLabels(h), "times":redd.getAvailableDuration(h)} for h in houses}
    return reddInfo

def getInfo(request):
    return JsonResponse(info())

def getTimes(request, house, channel):
    availability = redd.loadAvailability()
    response = {}
    if house in availability and channel in availability[house]:
        response["ranges"] = availability[house][channel]

        # Map this to timezone unaware UTC Stuff
        # -> E.g. if it was 0-24 it is mapped to 0-24 on this day as utc timestamps   
        newRanges = []
        for r in response["ranges"]:
            startTs = r[0]
            stopTs = r[1]
            date = datetime.fromtimestamp(startTs, pytz.UTC).astimezone(redd.getTimeZone())
            startTs = startTs + date.utcoffset().total_seconds()
            stopTs = stopTs + date.utcoffset().total_seconds()
            newRanges.append([startTs, stopTs])

        response["ranges"] = newRanges

    return JsonResponse(response)

def loadData(house, channel, day, samplingrate=1):
    # Let this be an unaware timestamp object
    startDate = datetime.strptime(day, "%m_%d_%Y").replace(hour=0, minute=0, second=0, microsecond=0)
    tz = redd.getTimeZone()
    startDate = tz.localize(startDate)
    stopDate = startDate+timedelta(days=1)

    dataDict = redd.loadLowFreq(house, utcStartTs=startDate.timestamp(), utcStopTs=stopDate.timestamp(), channels=[channel])[0]


    # TODO: make this work wit timestamps from original data
    startTs = float(dataDict["ts"][0])
    stopTs = float(dataDict["ts"][-1])
    
    # Convert to one hz
    data = np.interp(np.arange(startTs, stopTs, 1/samplingrate), dataDict["ts"], dataDict["data"]["s"])
    dataDict["data"] = np.recarray(len(data), dtype=np.dtype([('s',np.float32)]))
    dataDict["data"]["s"] = data
    dataDict["tz"] = tz.zone
    dataDict["duration"] = stopTs-startTs
    dataDict["duration"] = len(data)/samplingrate
    dataDict["samplingrate"] = samplingrate
    del dataDict["ts"]
    return dataDict

# Register data provider
dataHp.dataProvider["redd"] = loadData

def initChart(request, house, channel, day):
    sessionID = request.session.session_key
    wsManager.sendStatus(sessionID, "Loading REDD data...", percent=25)
    # Load the data
    dataDict = loadData(house, channel, day)
    wsManager.sendStatus(sessionID, "Preparing ...", percent=75)

    # Set global session data
    fp = "house_" + str(house) + "__" + "channel_" + str(channel) + "__" + day + ".mkv"
    request.session["dataInfo"] = {"type":"redd", "filePath": fp, "args": (house, channel, day)}
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
        
        # TODO: make this work wit timestamps from original data
        # indices = np.where((dataDict["ts"] > startTs) & (dataDict["ts"] < stopTs))[0]
        # dataDictCopy["data"] = dataDict["data"][indices]
        # dataDictCopy["ts"] = dataDict["ts"][indices]
        # startTs = dataDictCopy["ts"][0]
        # stopTs = dataDictCopy["ts"][-1]

        startSample = int((startTs - dataDict["timestamp"])*dataDict["samplingrate"])
        stopSample = int((stopTs - dataDict["timestamp"])*dataDict["samplingrate"])

        dataDictCopy["data"] = dataDict["data"][startSample:stopSample]

        chartData = chart.responseForData(dataDictCopy, dataDictCopy["measures"], startTs, stopTs)

    return JsonResponse(chartData)
