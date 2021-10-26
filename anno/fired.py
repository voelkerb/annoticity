from datetime import datetime
import pytz
import numpy as np
from . import chart
from . import data as dataHp

from decouple import config

import sys, os
from .datasets.FIRED import helper as hp

from django.http import JsonResponse


hp.FIRED_BASE_FOLDER = config('FIRED_BASE_PATH')
hp.RSYNC_ALLOWED = True

def info():
    mapping = hp.getDeviceMapping()
    firedInfo = {"meter":[]}
    for m in mapping:
        if "smartmeter" in m: name = "aggregated"
        else: name = m.lstrip("powermeter") + ": " + str(", ".join(mapping[m]["appliances"])).replace("\"", ""),
        firedInfo["meter"].append({"name":name, "value":m})
    # firedInfo = {k:str(", ".join(mapping[k]["appliances"])).replace("\"", "") for k in mapping}
    # startTs, stopTs = hp.getRecordingRange()
    # firedInfo["range"] = [startTs, stopTs]
    return firedInfo

def getInfo(request):
    return JsonResponse(info())

def getTimes(request):
    startTs, stopTs = hp.getRecordingRange()

    # Map this to timezone unaware UTC Stuff
    # -> E.g. if it was 0-24 it is mapped to 0-24 on this day as utc timestamps
    date = datetime.fromtimestamp(startTs, pytz.UTC).astimezone(hp.getTimeZone())
    startTs = startTs + date.utcoffset().total_seconds()
    stopTs = stopTs + date.utcoffset().total_seconds()
    
    # Nasti hack to avoid next day if end time is 0:00:0
    response = {"ranges":[[startTs, stopTs-1]]}
    return JsonResponse(response)

def loadData(meter, day, samplingrate=50):
    startDate = datetime.strptime(day, "%m_%d_%Y")
    # TODO: how to handle dropout at midnight
    startTs = startDate.timestamp() + 60 
    stopTs = startTs + 60*60*24

    # Load once in best resolution and downsample later on
    dataDict = hp.getMeterPower(meter, samplingrate, startTs=startTs, stopTs=stopTs, smartmeterMergePhases=True)
    appliances = hp.getApplianceList(meter, startTs=startTs, stopTs=stopTs)
    devInfo = hp.getDeviceInfo()
    strings = []
    for a in appliances:
        string = a
        if a in devInfo: string += " ({} - {})".format(str(devInfo[a]["brand"]), str(devInfo[a]["model"]))
        strings.append(string)
    dataDict["info"] = ", ".join(strings)
    dataDict["unix_timestamp"] = hp.UTCfromLocalTs(dataDict["timestamp"])
    dataDict["tz"] = hp.getTimeZone().zone

    return dataDict

# Register data provider
dataHp.dataProvider["fired"] = loadData

def initChart(request, meter, day):
    startDate = datetime.strptime(day, "%m_%d_%Y")
    # TODO: how to handle dropout at midnight
    startTs = startDate.timestamp() + 60
    stopTs = startTs + 60*60*24

    filePath = hp.getMeterFiles(meter, 50, startTs=startTs, stopTs=stopTs)
    if len(filePath) > 0: filePath = filePath[0]
    else: filePath = None

    samplingrate = 2/60
    # samplingrate = 5
    # Load once in best resolution and downsample later on
    dataDict = loadData(meter, day, samplingrate=samplingrate)

    # Set global session data
    # request.session["dataInfo"] = {"type":"fired", "meter": meter, "day": day, "filePath":filePath}
    request.session["dataInfo"] = {"type":"fired", "filePath": filePath, "args": (meter, day)}
    response = chart.responseForInitChart(dataDict, measures=dataDict["measures"])
    response['timeZone'] = "Europe/Berlin"
    response["filename"] = os.path.basename(filePath)
    
    return JsonResponse(response)

def getData(request, startTs, stopTs):
    chartData = {}
    dataInfo = request.session.get("dataInfo", None)
    if dataInfo is not None:
        meter = dataInfo["args"][0]
        print("Selection: " + hp.time_format_ymdhms(startTs) + "->" + hp.time_format_ymdhms(stopTs))
        duration = stopTs - startTs

        samplingrate = min(50, dataHp.srBasedOnDur(duration, "p"))
        dataDict = hp.getMeterPower(meter, samplingrate, startTs=startTs, stopTs=stopTs, smartmeterMergePhases=Truert)
        dataDict["unix_timestamp"] = hp.UTCfromLocalTs(dataDict["timestamp"])
        chartData = chart.responseForData(dataDict, dataDict["measures"], startTs, stopTs)
    print("Done!") 
    return JsonResponse(chartData)

def getHighFreqData(request, startTsStr, stopTsStr):
    chartData = {}
    dataInfo = request.session.get("dataInfo", None)
    startTs = float(startTsStr.replace("_", "."))
    stopTs = float(stopTsStr.replace("_", "."))
    if dataInfo is not None:
        meter = dataInfo["args"][0]
        print("SelectionHigh: " + hp.time_format_ymdhms(startTs) + "->" + hp.time_format_ymdhms(stopTs))
        duration = stopTs - startTs

        samplingrate = min(4000, dataHp.srBasedOnDur(duration, "i"))
        dataDict = hp.getMeterVI(meter, samplingrate, startTs=startTs, stopTs=stopTs, smartmeterMergePhases=True)
        dataDict["unix_timestamp"] = hp.UTCfromLocalTs(dataDict["timestamp"])
        chartData = chart.responseForNewData(dataDict, dataDict["measures"], startTs, stopTs)
    return JsonResponse(chartData)