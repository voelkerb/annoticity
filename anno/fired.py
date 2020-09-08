from datetime import datetime
import numpy as np
from . import chart
from . import data as dataHp

from annoticity.settings import SMART_ENERGY_TOOLS_PATH

import sys, os
sys.path.insert(0, os.path.join(SMART_ENERGY_TOOLS_PATH, "datasets", "FIRED"))
import helper as hp

from django.http import JsonResponse


hp.FIRED_BASE_FOLDER = "/Users/voelkerb/dump/FIRED/"




def info():
    meters = hp.getMeterList()
    mapping = hp.getDeviceMapping()
    firedInfo = {k:str(", ".join(mapping[k]["appliances"])).replace("\"", "") for k in mapping}
    startTs, stopTs = hp.getRecordingRange()
    firedInfo["range"] = [startTs, stopTs]
    return firedInfo

def loadData(meter, day, samplingrate=50):
    startDate = datetime.strptime(day, "%m_%d_%Y")
    startTs = startDate.timestamp()
    stopTs = startTs + 60*60*24

    # Load once in best resolution and downsample later on
    dataDict = hp.getMeterPower(meter, samplingrate, startTs=startTs, stopTs=stopTs)
    return dataDict

# Register data provider
dataHp.dataProvider["fired"] = loadData

def initChart(request, meter, day):
    startDate = datetime.strptime(day, "%m_%d_%Y")
    startTs = startDate.timestamp()
    stopTs = startTs + 60*60*24

    filePath = hp.getMeterFiles(meter, 50, startTs=startTs, stopTs=stopTs)
    if len(filePath) > 0: filePath = filePath[0]
    else: filePath = None

    samplingrate = 2/60
    # Load once in best resolution and downsample later on
    dataDict = loadData(meter, day, samplingrate=samplingrate)

    # Set global session data
    # request.session["dataInfo"] = {"type":"fired", "meter": meter, "day": day, "filePath":filePath}
    request.session["dataInfo"] = {"type":"fired", "filePath": filePath, "args": (meter, day)}
    
    response = chart.responseForInitChart(dataDict, measures=dataDict["measures"])
    response['timeZone'] = "Europe/Berlin"

    return JsonResponse(response)

def getData(request, startTs, stopTs):
    chartData = {}
    dataInfo = request.session.get("dataInfo", None)
    if dataInfo is not None:
        meter = dataInfo["args"][0]
        print("Selection: " + hp.time_format_ymdhms(startTs) + "->" + hp.time_format_ymdhms(stopTs))
        duration = stopTs - startTs

        samplingrate = min(50, dataHp.srBasedOnDur(duration, "p"))
        dataDict = hp.getMeterPower(meter, samplingrate, startTs=startTs, stopTs=stopTs)
        chartData = chart.responseForData(dataDict, dataDict["measures"], startTs, stopTs)
    
    return JsonResponse(chartData)
