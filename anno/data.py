import numpy as np
from datetime import datetime
from . import chart
import os

from .powerData import dataManager as dm
from decouple import config
SMART_ENERGY_TOOLS_PATH = config('SMART_ENERGY_TOOLS_PATH')

import sys
sys.path.insert(0, SMART_ENERGY_TOOLS_PATH)
import MKV.mkv as mkv
import csv
import pandas as pd

def resampleDict(dataDict, measure, outRate, forceEvenRate=False):
    if "ts" not in dataDict: 
        data = resample(dataDict["data"][measure], dataDict["samplingrate"], outRate) 
        timestamps = np.linspace(dataDict["timestamp"]*1000, (dataDict["timestamp"]+dataDict["duration"])*1000, len(data))
    else:
        if forceEvenRate is False and outRate >= dataDict["samplingrate"]:
            data = dataDict["data"][measure] 
            timestamps = [ts*1000 for ts in dataDict["ts"]]
        else:
            data, tss = resampleUneven(dataDict["data"][measure], outRate, dataDict["ts"]) 
            timestamps = [ts*1000 for ts in tss]
    return data, timestamps


def resampleUneven(data, outRate, tsIn):
    oldX = tsIn
    newX = np.arange(tsIn[0], tsIn[-1], 1/outRate)
    if isinstance(data, (np.record,np.recarray)):
        data2 = np.zeros(len(newX), dtype=data.dtype)
        for measure in data.dtype.names:
            data2[measure] = np.float32(np.interp(newX, oldX, data[measure]))
    elif isinstance(data, dict):
        data2 = {key:None for key in data.keys()}
        for measure in data.keys():
            data2[measure] = np.float32(np.interp(newX, oldX, data[measure]))
    else:
        data2 = np.float32(np.interp(newX, oldX, data))
    return data2, newX

def resample(data, inRate, outRate):
    if inRate == outRate: return data
    resampleFac = inRate/outRate

    # print("Resample:" +  str(data.__name__))
    # NOTE: This is done for each measure
    # TODO: Maybe we can make this quicker somehow
    
    oldX = np.arange(0, len(data))
    newX = np.arange(0, len(data), resampleFac)
    if isinstance(data, (np.record,np.recarray)):
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
    if measure.lower().split("_l")[0] in ["p","q","s", "v_rms", "i_rms"]:
        #if dur > 24*60*60: samplingrate = 1.0/600
        if dur > 10*60*60: samplingrate = 1.0/60
        elif dur > 4*60*60: samplingrate = 2.0/60
        elif dur > 2*60*60: samplingrate = 0.3
        elif dur > 1*60*60: samplingrate = 0.1
        elif dur > 30*60: samplingrate = 1
        elif dur > 10*60: samplingrate = 2
        elif dur > 1*60: samplingrate = 10
        else: samplingrate = 50
    elif measure.lower().split("_l")[0] in ["v","i"]:
        if dur > 200: samplingrate = 0.1
        if dur > 10: samplingrate = 1
        elif dur > 5: samplingrate = 1000
        elif dur > 2: samplingrate = 2000
        elif dur > 1: samplingrate = 4000
        else: samplingrate = 50000
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




def getCSVHeaderDelimiterFirstRow(filepath, delimiter = "\t"):
    #  Find delimiter by ourself
    firstRow = []
    with open(filepath, 'r') as csvfile:
        delimiter = csv.Sniffer().sniff(csvfile.read(1024), delimiters='\t ;,')
        csvfile.seek(0)
        reader = csv.reader(csvfile, delimiter)
        delimiter = delimiter.delimiter
        for i, row in enumerate(reader):
            firstRow.append(row)
            if i == 1: break

    header = firstRow[0]
    # Check if first entry is header, by trying to convert to number
    hasHeader = True
    for entry in header:
        try:
            value = float(entry)
            hasHeader = False
        except: pass
    # Delete entry if it is a header
    if hasHeader and len(firstRow) > 0: firstRow = firstRow[-1]
    if not hasHeader: header = None

    return header, delimiter, firstRow

def get_date_parser(s_date):
    try:
        value = float(s_date)
        return date, "timestamp"
    except: pass
    date_patterns = ["%d-%m-%Y", "%Y-%m-%d", "%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f"]

    for pattern in date_patterns:
        try:
            return datetime.strptime(s_date, pattern), pattern
        except:
            pass

    print("Date is not in expected format: {}".format(s_date))
    return None, None

def loadCSV(filepath, ts=0, delimiter = "\t"):
    #  Find delimiter by ourself
    dataDict = None
    data, error, warning = None, None, None

    header, delimiter, firstRow = getCSVHeaderDelimiterFirstRow(filepath, delimiter=delimiter)

    print("CSV Header: \"{}\"".format(header))
    print("CSV Delimiter: \"{}\"".format(delimiter))

    if header is None: 
        error = "Please provide a header with your CSV data e.g.\"ts\", \"value\""
        return dataDict, error, warning
    # Try to get timestamp column
    tsNames = ["timestamp", "ts", "date", "datum"]
    tsName = None
    for name in tsNames:
        try: 
            index = [x.lower() for x in header].index(name)
            tsName = header[index]
            break
        except:
            pass
    if tsName is None:
        error = "Cannot find timestamp column. Header name should be one of {}".format(", ".join(["\"{}\"".format(n) for n in tsNames]))
        return dataDict, error, warning

    print("TS Colum Name: \"{}\"".format(tsName))
    
    newDataNames = [d if d != tsName else "ts" for d in header]
    print("New Colum Names: \"{}\"".format(newDataNames))
    print("FirstRow: \"{}\"".format(firstRow))

    date, date_format = get_date_parser(firstRow[header.index(tsName)])
    print(date)
    print("FirstEntry Time: \"{}\"".format(date))
    print("Date Format: \"{}\"".format(date_format))

    dateparser = lambda x: pd.Timestamp(pd.datetime.strptime(x, date_format))
    data = pd.read_csv(filepath, delimiter=delimiter, names=newDataNames, parse_dates=["ts"], skiprows=[0], date_parser=dateparser)
    data["ts"] = data['ts'].astype(np.int64)
    data["ts"] = data['ts'].astype(np.float64)/float(1e9)
    data = data.set_index(["ts"])
    rec = data.to_records()
    ts = rec["ts"]
    newDtype = [(m.lower(), np.float32) for m in rec.dtype.names if m != "ts"]
    print(newDtype)
    newData = np.recarray((len(ts),), dtype=newDtype).view(np.recarray)
    for m in rec.dtype.names: 
        if m.lower() in newData.dtype.names: newData[m.lower()] = rec[m]
    
    #print(type(data["ts"][1]))
    print(newData)
    print(rec.dtype)
    
    sr = float(1.0/np.mean(np.diff(ts)))
    print("Avg sr: {}".format(sr))
    print(sr)
    dataDict = {"data":newData, "ts":ts, "timestamp":ts[0], "samplingrate":sr, "title":os.path.basename(filepath).split(".csv")[0], 
                "measures":[m.lower() for m in newData.dtype.names], "duration":ts[-1]-ts[0]}

    return dataDict, error, warning

supportedFiles = {"mkv":loadMKV, "csv":loadCSV}


dataProvider = {}


def getSessionData(sessionID, sessionInfo):
    if sessionInfo["type"] == "fired":
        dataDict = dataProvider[sessionInfo["type"]](*sessionInfo["args"])
    else:
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