from datetime import datetime
import numpy as np
import pytz
from . import chart
from . import data as dataHp
from .powerData import dataManager as dm
from decouple import config

import sys, os
from .datasets.BLOND import blondLoader as bl

from django.http import JsonResponse


bl.BASE_PATH = config('BLOND_BASE_PATH')
bl.DOWNLOAD_PATH = os.path.join(bl.BASE_PATH, "tmp")


def info():
    sets = bl.getAvailableSets()
    blondInfo = {"set":[{"name":s} for s in sets]}
    
    for i,s in enumerate(sets):
        meters = bl.getAvailableMeters()
        blondInfo["set"][i]["meter"] = [{"name": m} for m in meters]
        for j,m in enumerate(meters):
            channels = bl.getAvailableChannels(m)
            blondInfo["set"][i]["meter"][j]["channel"] = [{"name": c} for c in channels]
        # blondInfo[s]["meters"] = {m:bl.getAvailableChannels(m) for m in bl.getAvailableMeters()}
        # start, stop = bl.getAvailableDuration(s)
        # blondInfo[s]["range"] = [[start, stop]]
    return blondInfo

def getInfo(request):
    return JsonResponse(info())

def getTimes(request, set, meter, channel):
    startTs, stopTs = bl.getAvailableDuration(set)

    # Map this to timezone unaware UTC Stuff
    # -> E.g. if it was 0-24 it is mapped to 0-24 on this day as utc timestamps
    date = datetime.fromtimestamp(startTs, pytz.UTC).astimezone(bl.getTimeZone())
    startTs = startTs + date.utcoffset().total_seconds()
    stopTs = stopTs + date.utcoffset().total_seconds()

    response = {"ranges":[[startTs, stopTs]]}
    return JsonResponse(response)

def loadData(set, meter, channel, day, samplingrate=1):
    print("set: {}, meter: {}, channel: {}, day: {}".format(set, meter, channel, day))
    startDate = datetime.strptime(day, "%m_%d_%Y")

    startTs = startDate.timestamp()
    stopTs = startTs + 60*60*24
    dataDict = bl.loadRange(set, meter, channel, startTs, stopTs)

    #if len(dataDict) > 0: dataDict = dataDict[0]
    #else: return None

    devices = bl.shortDeviceList(meter, channel, dataDict["timestamp"], dataDict["timestamp"]+dataDict["duration"])

    if len(devices) > 0: dataDict["info"] = ", ".join(devices)
    if samplingrate != dataDict["samplingrate"]:
        dataDict["data"] = dataHp.resample(dataDict["data"], dataDict["samplingrate"], samplingrate)
        dataDict["samplingrate"] = samplingrate
        dataDict["samples"] = len(dataDict["data"])
    dataDict["tz"] = bl.getTimeZone().zone
    dataDict["tsIsUTC"] = False
    return dataDict

# Register data provider
dataHp.dataProvider["blond"] = loadData

def initChart(request, set, meter, channel, day):
    startDate = datetime.strptime(day, "%m_%d_%Y")

    # Load once in best resolution and downsample later on
    dataDict = loadData(set, meter, channel, day)

    # Set global session data
    fp = set + "__" + meter + "__" + channel + "__" + day + ".mkv"
    request.session["dataInfo"] = {"type":"blond", "filePath": fp, "args": (set, meter, channel, day)}
    # request.session["dataInfo"] = {"type":"blond", "filePath": fp, "set": set, "meter": meter, "channel": channel, "day": day}
    # add data to dataManager
    dm.add(request.session.session_key, dataDict)

    response = chart.responseForInitChart(dataDict, measures=dataDict["measures"])
    response['timeZone'] = "Europe/Berlin"
    response['filename'] = fp

    return JsonResponse(response)

def getData(request, startTs, stopTs):
    chartData = {}

    dataDict = dm.get(request.session.session_key)

    if dataDict is not None:
        print("Getting blond data")
        duration = stopTs - startTs
        
        dataDictCopy = dict((k,v) for k,v in dataDict.items() if k != "data")

        startSample = int((startTs-dataDict["timestamp"])*dataDict["samplingrate"])
        startSample = max(0, startSample)
        stopSample = int((stopTs-dataDict["timestamp"])*dataDict["samplingrate"])
        stopSample = min(len(dataDict["data"]), stopSample)
        dataDictCopy["data"] = dataDict["data"][startSample:stopSample]

        startTs = max(dataDictCopy["timestamp"], startTs)
        stopTs = min(dataDictCopy["timestamp"]+dataDictCopy["duration"], stopTs)

        dataDictCopy["timestamp"] = startTs
        dataDictCopy["duration"] = stopTs-startTs

        chartData = chart.responseForData(dataDictCopy, dataDictCopy["measures"], startTs, stopTs)
    
    print("Done")
    return JsonResponse(chartData)


def getHighFreqData(request, startTsStr, stopTsStr):
    chartData = {}
    dataInfo = request.session.get("dataInfo", None)
    startTs = float(startTsStr.replace("_", "."))
    stopTs = float(stopTsStr.replace("_", "."))
    if dataInfo is not None:
        meter = dataInfo["args"][0]
        duration = stopTs - startTs
        print("Getting high freq blond data")

        dataDict = bl.loadHighFreqRange(dataInfo["args"][0], dataInfo["args"][1], dataInfo["args"][2], startTs, stopTs)
        
        samplingrate = min(dataDict["samplingrate"], dataHp.srBasedOnDur(duration, "i"))

        if samplingrate != dataDict["samplingrate"]:
            dataDict["data"] = dataHp.resample(dataDict["data"], dataDict["samplingrate"], samplingrate)
            dataDict["samplingrate"] = samplingrate
            dataDict["samples"] = len(dataDict["data"])
        
        dataDict["unix_timestamp"] = dataDict["timestamp"]
        chartData = chart.responseForNewData(dataDict, dataDict["measures"], startTs, stopTs)
    print("Done")
    return JsonResponse(chartData)