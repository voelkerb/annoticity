import numpy as np
from datetime import datetime
from . import chart

from .powerData import dataManager as dm
from decouple import config
SMART_ENERGY_TOOLS_PATH = config('SMART_ENERGY_TOOLS_PATH')

import sys
sys.path.insert(0, SMART_ENERGY_TOOLS_PATH)
import MKV.mkv as mkv


def resample(data, inRate, outRate):
    if inRate == outRate: return data
    resampleFac = inRate/outRate
    # NOTE: This is done for each measure
    # TODO: Maybe we can make this quicker somehow
    oldX = np.arange(0, len(data))
    newX = np.arange(0, len(data), resampleFac)
    if isinstance(data, np.record):
        data2 = np.zeros(len(newX), dtype=data.dtype)
        for measure in data.dtype.names:
            data2[measure] = np.float32(np.interp(newX, oldX, data[measure]))
    elif isinstance(data, dict):
        data2 = {key:None for key in data.keys()}
        for measure in data.keys():
            data2[measure] = np.float32(np.interp(newX, oldX, data[measure]))
    else:
        data2 = np.float32(np.interp(newX, oldX, data))
    return data2


def srBasedOnDur(dur, measure):
    samplingrate = 1
    if measure.split("_l")[0] in ["p","q","s", "v_rms", "i_rms"]:
        if dur > 4*60*60: samplingrate = 2/60
        elif dur > 2*60*60: samplingrate = 0.3
        elif dur > 1*60*60: samplingrate = 0.1
        elif dur > 30*60: samplingrate = 1
        elif dur > 10*60: samplingrate = 2
        elif dur > 1*60: samplingrate = 10
        else: samplingrate = 50
    elif measure.split("_l")[0] in ["v","i"]:
        if dur > 200: samplingrate = 0.1
        if dur > 10: samplingrate = 1
        elif dur > 5: samplingrate = 1000
        elif dur > 2: samplingrate = 1000
        else: samplingrate = 2000
    return samplingrate

def getMeasure(availMeas, selection):
    supSel = {"Active":"p", "Reactive":"q", "Apparent":"s"}
    if selection in supSel and supSel[selection] in availMeas: return supSel[selection]
    elif selection in supSel and supSel[selection] + "_l1" in availMeas: return supSel[selection] + "_l1"
    elif "i" in availMeas: return "i"
    elif "i_l1" in availMeas: return "i_l1"
    else: return availMeas[0]



readableMeasures = {
    "p": "Active Power",
    "q": "Reactive Power",
    "s": "Apparent Power",
    "v": "Voltage",
    "v_rms": "RMS Voltage",
    "i": "Current",
    "i_rms": "RMS Current",
}

def getAvailableMText(measures):
    availableM = []
    for m in measures:
        name = m
        if m.split("_l")[0] in readableMeasures: name = readableMeasures[m.split("_l")[0]]
        if len(m.split("_l")) > 1: name += " L" + m.split("_l")[-1]
        availableM.append({"name":name, "id":m})
    return availableM


def load(fp):
    suffix = fp.split(".")[-1]
    if suffix not in supportedFiles.keys(): 
        error = 'Sorry, currently only the following file types are supported: ' + ",".join(list(supportedFiles.keys()))
        return None, error, None
    return supportedFiles[suffix](fp)


def loadMKV(path):
    dataList = mkv.load(path, audio=True, subs=True)
    dataList,_ = mkv.mapSubsToAudio(dataList)
    error, warning, data = None, None, None
    if len(dataList) == 0: 
        error = 'File has more than one stream, only displaying first now'
        print(error)
    else:
        if len(dataList) > 1:
            warning = 'File has more than one stream, only displaying first now'
            print(warning)
        dataDict = dataList[0]
        if "timestamp" not in dataDict:
            warning = 'No timestamp found, using seconds instead'
            dataDict["timestamp"] = 0
        if "duration" not in dataDict:
            dataDict["duration"] = dataDict["samples"]/dataDict["samplingrate"]
    return dataDict, error, warning

supportedFiles = {"mkv":loadMKV}


dataProvider = {}


def getSessionData(sessionID, sessionInfo):
    if sessionID is None: return None
    dataDict = dm.get(sessionID)
    if dataDict is None:
        if sessionInfo is not None and sessionInfo["type"] in dataProvider:
            dataDict = dataProvider[sessionInfo["type"]](*sessionInfo["args"])
    return dataDict

    # if sessionInfo["type"] == "fired":
    #     info = mkv.info(sessionInfo["filePath"])["streams"]
    #     # Just the info for 1st audio in file
    #     streamInfo = next(s for s in info if s["type"] == "audio")
    #     # Load only this stream
    #     streamIndex = streamInfo["streamIndex"]
    #     dataDict = mkv.loadAudio(sessionInfo["filePath"], streamsToLoad=streamIndex)[0]
    # elif sessionInfo["type"] in ["redd", "uploaded", "blond"]:
    #     dataDict = dm.get(sessionID)
    #     if dataDict is None:
    #         if sessionInfo["type"] == "redd": 
    #             dataDict = redd.loadData(*sessionInfo["args"])
    #         elif sessionInfo["type"] == "blond": 
    #             dataDict = blond.loadData(*sessionInfo["args"])
    #         elif sessionInfo["type"] == "uploaded": 
    #             dataDict = uploaded.loadData(*sessionInfo["args"])

    # return dataDict