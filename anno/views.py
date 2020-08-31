from django.shortcuts import render
import pandas as pd
from datetime import datetime, timedelta
from .forms import FIREDSelectionForm
import json
from json import dumps 
import simplejson
import os
from annoticity.settings import PROJECT_ROOT, MEDIA_ROOT, MEDIA_URL
from django.http import JsonResponse
import pytz
import time
import subprocess
from django.http import HttpResponseRedirect
from django.urls import reverse
import numpy as np 
import sys
sys.path.insert(0, '/Users/voelkerb/Documents/smartenergy/datasets/FIRED')
sys.path.insert(0, '/Users/voelkerb/Documents/smartenergy/datasets/REDD')
sys.path.insert(0, '/Users/voelkerb/Documents/smartenergy/')
import MKV.mkv as mkv
import helper as hp
import reddLoader as redd

from .websocket import consumers as webSockets

from analyze.analyzeSignal import calcPowers
from analyze.pereiraChangeOfMean import pereiraLikelihood, getChangePoints, LikelihoodPlot, cleanLikelihoods
from analyze.GLRchangeOfMean import getGLRLikelihood
 
from django.core.files import File

import pysubs2
from pysubs2 import SSAFile, SSAEvent, make_time

hp.FIRED_BASE_FOLDER = "/Users/voelkerb/dump/FIRED/"

redd.BASE_PATH = "/users/voelkerb/NILM_Datasets/REDD/"
# Create your views here.
import pandas as pd
from django.core.files.storage import FileSystemStorage
from django.contrib import messages

# Global data for uploaded file
uploadedFile = None
dataDict = None
# Global data for FIRED
FIRED_File = None
REDDData = None

# import av
class NumpyEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return json.JSONEncoder.default(self, obj)

class OverwriteStorage(FileSystemStorage):
    def _save(self, name, content):
        self.delete(name)
        return super(OverwriteStorage, self)._save(name, content)

    def get_available_name(self, name, max_length=None):
        return name

def labelUpload(request):
    response = {}
    if request.method == 'POST':
        if 'uploadedFile' not in request.FILES:
            response['message'] = 'Please select the file to upload before'
        else:
            myfile = request.FILES['uploadedFile']
            filename = myfile.name
            suffix = filename.split(".")[-1].lower()
            if suffix not in supportedLabelFiles.keys(): 
                response['message'] = 'Sorry, currently only the following file types are supported: ' + ",".join(list(supportedLabelFiles.keys()))
            else:
                ts = request.POST.get("timestamp")
                if ts is not None:
                    ts = float(ts)
                    print("Timestamp: " + hp.time_format_ymdhms(ts))
                else: 
                    ts = 0
                fs = OverwriteStorage()
                filename = fs.save(myfile.name, myfile)
                csv_path = fs.url(filename)
                csv_path = os.path.join(PROJECT_ROOT, csv_path[1:])
                labels, error, warning = supportedLabelFiles[suffix](csv_path, ts=ts)
                print(labels)
                if error is not None:
                    response['message'] = error
                else:
                    response["labels"] = labels
                    if warning is not None: response["message"] = warning

    return JsonResponse(response)

readableMeasures = {
    "p": "Active Power",
    "q": "Reactive Power",
    "s": "Apparent Power",
    "v": "Voltage",
    "i": "Current",
}
def dataUpload(request):
    response = {}
    if request.method == 'POST':
        if 'uploadedFile' not in request.FILES:
            response['message'] = 'Please select the file to upload before'
        else:
            myfile = request.FILES['uploadedFile']
            filename = myfile.name
            suffix = filename.split(".")[-1]
            if suffix not in supportedFiles.keys(): 
                context['message'] = 'Sorry, currently only the following file types are supported: ' + ",".join(list(supportedFiles.keys()))
            else:
                fs = OverwriteStorage()
                newDataReinit()
                global uploadedFile, dataDict
                if uploadedFile is not None:
                    fs.delete(uploadedFile)
                filename = fs.save(myfile.name, myfile)
                uploaded_file_url = fs.url(filename)
                uploadedFile = os.path.join(PROJECT_ROOT, uploaded_file_url[1:])
                
                dataDict, error, warning = supportedFiles[suffix](uploadedFile)
                if error is not None:
                    response['message'] = error
                else:
                    if warning is not None: 
                        response['message'] = warning
                    response['uploaded_success'] = True
                response['uploaded_file_name'] = filename
                if dataDict["timestamp"] == 0:
                    response['timeZone'] = "UTC"
                duration = dataDict["duration"]
                # Get chart
                m = dataDict["measures"][0]
                samplingrate = min(dataDict["samplingrate"], srBasedOnDur(duration, m))
                data = resample(dataDict["data"][m], dataDict["samplingrate"], samplingrate) 
                startTs = dataDict["timestamp"]
                stopTs = startTs + dataDict["duration"]
                timestamps = np.linspace(startTs*1000, stopTs*1000, len(data))
                print(startTs)
                print(hp.time_format_ymdhms(startTs))
                title = "unknown"
                device = "unknown"
                if (dataDict["timestamp"] == 0): day = None
                else: day = datetime.strftime(datetime.fromtimestamp(dataDict["timestamp"]), "%m_%d_%Y")
                if "title" in dataDict: 
                    device = dataDict["title"]
                    title = dataDict["title"]
                    if (dataDict["timestamp"] != 0): title += " day: " + datetime.fromtimestamp(dataDict["timestamp"]).strftime("%m/%d/%Y")
                chart = getChart(title, m)
                data = [[t, float(d)] for d,t in zip(data, timestamps)]
                chart['series'][0]['data'] = data
                chart['series'][0]['pointStart'] = startTs*1000
                title = os.path.basename(uploadedFile.split(".")[0])
                chart['series'][0]['pointInterval'] = (1/samplingrate)*1000
                # chart['yAxis']['min'] = -2.0
                chart['yAxis']['startOnTick'] = False
                subs = []
                if 'subs' in dataDict:
                    for sub in dataDict["subs"]:
                        subs.append({"startTs":sub.start/1000.0, "stopTs":sub.end/1000.0, "text":sub.text})
                availableM = []
                for m in dataDict["measures"]:
                    name = m
                    if m.split("_")[0] in readableMeasures: name = readableMeasures[m.split("_")[0]]
                    availableM.append({"name":name, "id":m})
                
                response.update({'chart':chart, 'measures': availableM, 'subs ':subs, 'device': device, 'date':day, 'filename':os.path.basename(uploadedFile), 'startTs':startTs})
    return JsonResponse(response)


def index(request):
    """ view function for sales app """
    meters = hp.getMeterList()
    startTs, stopTs = hp.getRecordingRange()
    unixStartTs = time.mktime(datetime.fromtimestamp(startTs).timetuple())
    unixStopTs = time.mktime(datetime.fromtimestamp(stopTs).timetuple())

    houses = redd.getAvailableHouses()
    reddInfo = {h:{"channels": redd.getAvailableChannels(h), "times":redd.getAvailableDuration(h)} for h in houses}
    print(reddInfo)
    

    context = {"FIREDDevices": meters, "FIRED_range":[startTs, stopTs], "navbar":"FIRED", "REDDInfo": json.dumps(reddInfo),'use_seconds':False}

    return render(request, 'eventLabeling.html', context=context)

def newDataReinit():
    global uploadedFile, dataDict, FIRED_File, REDDData
    oldFiles = os.listdir(MEDIA_ROOT)
    for t in oldFiles:
        print(oldFiles)
        subprocess.check_output(['rm', '-rf', os.path.join(MEDIA_ROOT, t)])
    uploadedFile = None
    dataDict = None
    FIRED_File = None
    REDDData = None

import csv
import pandas as pd
def loadCSV(filepath, ts=0, delimiter = "\t"):
    #  Find delimiter by ourself
    entries = []
    data, error, warning = None, None, None
    with open(filepath, 'r') as csvfile:
        delimiter = csv.Sniffer().sniff(csvfile.read(1024), delimiters='\t ;,')
        csvfile.seek(0)
        reader = csv.reader(csvfile, delimiter)
        for row in reader:
            # if len(row) == 0: continue
            entries.append(row)
    if len(entries) < 1: 
        error = "Error loading CSV"
        return data, error, warning
    header = entries[0]

    entryCheck = any(len(e) != len(header) for e in entries)
    if entryCheck: 
        error = "Entries have different length"
        return data, error, warning

    # Check if first entry is header, by trying to convert to number
    hasHeader = True
    for entry in header:
        try:
            value = float(entry)
            hasHeader = False
        except: pass
    # Delete entry if it is a header
    if hasHeader and len(entries) > 0: del entries[0]
    
    # Get what are values and what are labels
    # Try to guess header
    valueLabels = []
    labelIndex = 0
    valueIndex = 0
    for entry in header:
        try:
            value = float(entry)
            valueLabels.append("value_" + str(valueIndex))
            valueIndex += 1
        except: 
            valueLabels.append("label_" + str(labelIndex))
            labelIndex += 1

    # Else try to guess header.
    # First text is label 
    # First value entry will be startTs
    # stopTs will be be next value entry for which all values are bigger than startTs
    if not hasHeader:
        guessedHeader = ["label" if x=="label_0" else x for x in valueLabels]
        guessedHeader = ["startTs" if x=="value_0" else x for x in guessedHeader]
        if valueIndex > 1:
            startIndex = guessedHeader.index("startTs")
            for i in range(1, valueIndex):
                stopIndex = guessedHeader.index("value_"+ str(i))
                if any(e[stopIndex] < e[startIndex] for e in entries):
                    continue
                else:
                    # This might be the stopTs
                    guessedHeader = ["stopTs" if x=="value_"+ str(i) else x for x in guessedHeader]
                    break

        warning = "Guessed Header: " + ", ".join(guessedHeader)
        header = guessedHeader

    # def dateparse(timestamp:float):
    #     return datetime.fromtimestamp(float(timestamp))
    # data = pd.read_csv(filepath, delimiter=delimiter.delimiter, parse_dates=True, date_parser=dateparse).to_dict('r')
    data = [{k:e[i] for i, k in enumerate(header)} for e in entries]
    
    if len(data) > 0:
        valueKeys = [k for k in valueLabels if "value" in k and k in header]

        # Convert all values to float
        for key in valueKeys:
            for i in range(len(data)):
                data[i][key] = float(data[i][key])

        possibleTimeStartKeys = ["startTs", "startTS", "start", "timestamp", "Timestamp", "TIMESTAMP"]
        possibleTimeStopKeys = ["end", "stop", "stopTs", "stopTS"] 
        timeKeys = list(set(possibleTimeStartKeys + possibleTimeStopKeys) & set(header))

        # Convert all timestamps to float
        for key in timeKeys:
            for i in range(len(data)):
                data[i][key] = float(data[i][key])

        # Try if we have to add the timestamp
        if ts != 0: 
            addTsKeys = []
            for key in timeKeys:
                try:
                    date = datetime.fromtimestamp(float(data[0][key]))
                    if date.year > 1990 and date.year < 2050: continue
                    else: addTsKeys.append(key)
                except: addTsKeys.append(key)
            print("Add timestamp for keys: " + str(addTsKeys))
            # Add timestamp
            for key in addTsKeys:
                for i in range(len(data)):
                    data[i][key] = data[i][key] + ts

    return data, error, warning



def loadSRTASS(filepath, ts=0):
    data, error, warning = None, None, None
    subs = pysubs2.load(filepath)
    data = [{"startTs":ts+sub.start/1000.0, "stopTs":ts+sub.end/1000.0, "label": sub.text} for sub in subs]
    return data, error, warning


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
            data2[measure] = np.interp(newX, oldX, data[measure])
    elif isinstance(data, dict):
        data2 = {key:None for key in data.keys()}
        for measure in data.keys():
            data2[measure] = np.interp(newX, oldX, data[measure])
    else:
        data2 = np.zeros(len(newX))
        data2 = np.interp(newX, oldX, data)

    data = data2
    return data


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

measureTexts = {"p":{"name":"Active Power", "unit":"W"}, 
                "q":{"name":"Reactive Power", "unit":"var"}, 
                "s":{"name":"Apparent Power", "unit":"VA"},
                "v":{"name":"Voltage", "unit":"V"},
                "i":{"name":"Current", "unit":"A"},
                }
def getAxisMeasureUnit(measure):
    measureText = "Unknown"
    unit = ""
    if measure.rstrip("_l1") in measureTexts:
        measureText = measureTexts[measure.rstrip("_l1")]["name"]
        unit = measureTexts[measure.rstrip("_l1")]["unit"]
    return measureText, unit

def getChart(title, measure):
    measureText, unit = getAxisMeasureUnit(measure)
    chart = {
        # 'colors': ["rgba(235, 162, 59, 1)", "#c1a374"],
        'chart': {'type': 'area', 'zoomType': 'x', 'panning': True, 'animation': False, 'spacingTop': 5},
        'boost': { 'useGPUTranslations': True, 'enabled' : False },
        'navigator' : {
            'adaptToUpdatedData': False,
            'dateTimeLabelFormats': {
                'day': '%b %e, %Y'
            },
        },
        'plotOptions': {
            'series': {
                'allowPointSelect': True,
                'boost': { 'useGPUTranslations': True, 'enabled' : False },
                'fillOpacity': 0.4,
                'lineWidth': 1.0,
                'turboThreshold': 100,
                'gapSize': 20,
                'states': { 'hover': { 'enabled': False, 'lineWidth': 4 } },
                'marker': { 'enabled': False },
            },
        },
        'exporting': { 'enabled': False },
        'title': { 'text':title},
        'xAxis': {
            'ordinal' : False,
            'type': 'datetime',
            'crosshair': False,
            # 'title': { 'text': 'Time' },
            'dateTimeLabelFormats': {
              'millisecond': '%H:%M:%S.%L',
              'second': '%H:%M:%S',
              'minute': '%H:%M',
              'hour': '%H:%M',
              'day': '%e. %b',
              'week': '%e. %b',
              'month': '%b \'%y',
              'year': '%Y'
            },
        },
        'yAxis': {
            'title': {'text':"{} [{}]".format(measureText, unit)}
        },
        'tooltip': { 
            'split': True,
            'valueSuffix': " " + unit, 
            'valueDecimals': 2,
            'dateTimeLabelFormats': {
              'millisecond': '%H:%M:%S.%L',
              'second': '%H:%M:%S',
              'minute': '%H:%M',
              'hour': '%H:%M',
            },
        },
        'series': [{
            'name': measureText,
            'dataGrouping': { 'enabled': False },
        }]
    }
    return chart

def srBasedOnDur(dur, measure):
    if measure.rstrip("_l1") in ["p","q","s"]:
        if dur > 2*60*60: samplingrate = 0.1
        elif dur > 30*60: samplingrate = 1
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

def getREDDData(request, house, channel, day):
    startDate = datetime.strptime(day, "%m_%d_%Y").replace(hour=0, minute=0, second=0, microsecond=0)

    startTs = startDate.timestamp()
    stopTs = startTs + 60*60*24
    newDataReinit()
    print(hp.time_format_ymdhms(startTs) + "->" + hp.time_format_ymdhms(stopTs))
    dataDict = redd.loadLowFreqInterval(house, datetime.fromtimestamp(startTs), datetime.fromtimestamp(stopTs), channels=[channel])[0]
    # dataDict = redd.loadLowFreqDay(house, startDate, channels=[channel])[0]
    
    for i in range(10):
        print(dataDict["ts"][i])

    startTs = float(dataDict["ts"][0])
    stopTs = float(dataDict["ts"][-1])
    duration = stopTs - startTs
    
    samplingrate = 1
    oldX = dataDict["ts"]
    # Convert to one hz
    newX = np.arange(startTs, stopTs, 1/samplingrate)
    data = np.interp(newX, oldX, dataDict["data"]["s"])

    # data = []
    # for i in range(len(dataDict["data"])):
    #     data.append([float(dataDict["data"]["ts"][i])*1000, float(dataDict["data"]["s"][i])])
    
    
    m = "s"

    # wtype = np.dtype([('ts',newX.dtype),('s',data.dtype)])
    wtype = np.dtype([('s',data.dtype), ('s_l1',data.dtype)])
    dataDict["data"] = np.empty(len(newX), dtype=wtype)

    # dataDict["data"]["ts"] = newX
    dataDict["data"]["s"] = data
    dataDict["data"]["s_l1"] = data

    dataDict["timestamp"] = startTs
    dataDict["metadata"] = {k:dataDict[k] for k in {"timestamp", "title"}}
    dataDict["metadata"]["CHANNELS"] = 2
    dataDict["metadata"]["CHANNEL_TAGS"] = "s,s_l1"
    dataDict["samplingrate"] = samplingrate


    samplingrate = 0.1
    data = resample(dataDict["data"][m], dataDict["samplingrate"], samplingrate) 
    data = list(data)
    timestamps = np.linspace(startTs*1000, stopTs*1000, len(data))
    data = [[t, float(d)] for d,t in zip(data, timestamps)]
    

    devices = dataDict["title"]
    title = devices + " day: " + day.replace("_", "/")  
    chart = getChart(title, m)
    chart['series'][0]['data'] = data
    chart['series'][0]['pointStart'] = startTs*1000
    chart['series'][0]['pointInterval'] = (1/samplingrate)*1000
    
    availableM = []
    for m in dataDict["measures"]:
        if "ts" in m: continue
        name = m
        if m.split("_")[0] in readableMeasures: name = readableMeasures[m.split("_")[0]]
        availableM.append({"name":name, "id":m})
    
    global REDDData 
    REDDData = dataDict
    chartData = {'chart':chart, 'measures':availableM, 'device': devices, 'filename':"REDD", 'date':day.replace("_", "/"), 'startTs':startTs}
    chartData['timeZone'] = "UTC"
    chartData["filename"] = "house_" + str(house) + "__channel_" + str(channel) + "__" + day + ".mkv"
    # chartData = {"series":[{"data":data, "unit":unit, "measureText":measureText, "startTs": startTs, "interval": 1/samplingrate}]}
    return JsonResponse(chartData)

def getREDDDataRange(request, startTs, stopTs):
    chartData = {}
    if REDDData is None: return JsonResponse({})
    duration = stopTs - startTs
    # We only have 1Hz data remember?
    if duration < 5.0: 
        duration = 5.0
        stopTs = startTs + duration
    m = "s"
    samplingrate = min(REDDData["samplingrate"], srBasedOnDur(duration, m))
    
    startSample = int((startTs - REDDData["timestamp"])*REDDData["samplingrate"])
    stopSample = int((stopTs - REDDData["timestamp"])*REDDData["samplingrate"])
    data = resample(REDDData["data"][m][startSample:stopSample], REDDData["samplingrate"], samplingrate)
    data = list(data)

    timestamps = np.linspace(startTs*1000, stopTs*1000, len(data))
    data = [[t, float(d)] for d,t in zip(data, timestamps)]
    
    measureText, unit = getAxisMeasureUnit(m)

    chartData = {"series":[{"data":data,"unit":unit, "measureText":measureText, "startTs": startTs, "interval": 1/samplingrate}]}
    
    # chartData = {"series":[{"data":data, "unit":unit, "measureText":measureText, "startTs": startTs, "interval": 1/samplingrate}]}
    return JsonResponse(chartData)

def getDeviceData(request, meter, measure, startTs, stopTs):
    """ view function for sales app """
    print("Loading chart data range")

    print(hp.time_format_ymdhms(startTs) + "->" + hp.time_format_ymdhms(stopTs))
    duration = stopTs - startTs
    m = measure
    samplingrate = min(50, srBasedOnDur(duration, m))
    dataDict = hp.getMeterPower(meter, samplingrate, startTs=startTs, stopTs=stopTs)
    data = list(dataDict["data"][m])

    timestamps = np.linspace(startTs*1000, stopTs*1000, len(data))
    data = [[t, float(d)] for d,t in zip(data, timestamps)]
    
    measureText, unit = getAxisMeasureUnit(m)

    chartData = {"series":[{"data":data, "unit":unit, "measureText":measureText, "startTs": startTs, "interval": 1/samplingrate}]}
    return JsonResponse(chartData)


def initChart(request, meter, measure, day):
    
    startDate = datetime.strptime(day, "%m_%d_%Y")
    startTs = startDate.timestamp()
    stopTs = startTs + 60*60*24

    newDataReinit()
    global FIRED_File
    FIRED_File = hp.getMeterFiles(meter, 50, startTs=startTs, stopTs=stopTs)
    if len(FIRED_File) > 0: FIRED_File = FIRED_File[0]
    else: FIRED_File = None

    samplingrate = 0.1
    # Load once in best resolution and downsample later on
    dataDict = hp.getMeterPower(meter, samplingrate, startTs=startTs, stopTs=stopTs)
    m = dataDict["measures"][0]
    if measure in dataDict["measures"]: m = measure
    data = resample(dataDict["data"][m], dataDict["samplingrate"], samplingrate) 
    data = list(dataDict["data"][m])
    timestamps = np.linspace(startTs*1000, stopTs*1000, len(data))
    data = [[t, float(d)] for d,t in zip(data, timestamps)]
    devMapping = hp.getDeviceMapping()
    devices = meter
    if meter in devMapping:
        names = [hp.prettyfyApplianceName(n) for n in devMapping[meter]["appliances"]]
        devices = ", ".join(names)
        print(devices)
    title = devices + " day: " + day.replace("_", "/")  
    chart = getChart(title, m)
    chart['series'][0]['data'] = data
    chart['series'][0]['pointStart'] = startTs*1000
    chart['series'][0]['pointInterval'] = (1/samplingrate)*1000
    subs = []
    if 'subs' in dataDict:
        for sub in dataDict["subs"]:
            subs.append({"startTs":sub.start/1000.0, "stopTs":sub.end/1000.0, "text":sub.text})
    availableM = []
    for m in dataDict["measures"]:
        name = m
        if m.split("_")[0] in readableMeasures: name = readableMeasures[m.split("_")[0]]
        availableM.append({"name":name, "id":m})
                
    data = {'chart':chart, 'measures':availableM, 'subs':subs, 'device': devices, 'filename':os.path.basename(FIRED_File), 'date':day.replace("_", "/"), 'startTs':startTs}
    data['timeZone'] = "Europe/Berlin"

    return JsonResponse(data)


def getDataUploaded(request, startTs, stopTs, measure):

    duration = stopTs - startTs
    data = []
    samplingrate = 1
    unit = ""
    measureText = ""

    if dataDict is not None:
        m = dataDict["measures"][0]
        if measure in dataDict["measures"]: m = measure
        samplingrate = min(dataDict["samplingrate"], srBasedOnDur(duration, m))
        startSample = int((startTs-dataDict["timestamp"])*dataDict["samplingrate"])
        stopSample = int((stopTs-dataDict["timestamp"])*dataDict["samplingrate"])
        subData = dataDict["data"][m][startSample:stopSample]
        data = resample(subData, dataDict["samplingrate"], samplingrate) 
        timestamps = np.linspace(startTs*1000, stopTs*1000, len(data))
        data = [[t, float(d)] for d,t in zip(data, timestamps)]
        measureText, unit = getAxisMeasureUnit(m)

    chartData = {"series":[{"data":data, "unit":unit, "measureText":measureText,"startTs": startTs, "interval": 1/samplingrate}]}
    return JsonResponse(chartData)

def getFilePath(typee, fileName):
    filePath = None
    if typee == "FIRED":
        filePath = FIRED_File
        if filePath is None and fileName is not None:
            meter = os.path.basename(fileName).split("_")[0]
            filePath = os.path.join(hp.get50HzSummaryPath(), meter, fileName)
    elif typee == "Uploaded":
        filePath = uploadedFile
        if uploadedFile is None and fileName is not None:
            if os.path.exists(fileName): 
                filePath = fileName
            elif os.path.exists(os.path.join(MEDIA_ROOT, fileName)): 
                filePath = os.path.join(MEDIA_ROOT, fileName)
    elif typee == "REDD":
        raise Exception("Sorry, not implemented")
    return filePath

from filter.bilateral import bilateral
def getSteadyStateIndex(data, minSteadyIndex, threshold):
    start = 0
    startIndex = -1
    chunkSize = 10
    index = chunkSize

    filteredData = bilateral(np.array(data[chunkSize:]), sSpatial=3, sIntensity=10)
    for i in range(len(filteredData)-25):
        split = filteredData[i:i+25]
        std = np.abs(np.std(split))
        mean = np.mean(split)

        match = True
        for p in split:
            if abs(p-mean) > max(0.01*p, 1): match = False
        if match: return i + chunkSize
        index += chunkSize
    index = None
    return index

def indicesInDoubleArray(array2, value, thres):
    index1 = -1
    index2 = -1
    minDist = float("inf")
    for i, array in enumerate(array2):
        for j, val in enumerate(array):
            dist = abs(val - value)
            if dist < thres and dist < minDist:
                minDist = dist
                index1 = i
                index2 = j
    return index1, index2

def findEvents(power, thres, pre, post, voting, minDist, m):
    
    likelihoods = pereiraLikelihood(power, threshold=thres, preEventLength=pre, postEventLength=post, linearFactor=m, verbose=True)
    # likelihoods = cleanLikelihoods(likelihoods, 5*threshold)
    # Get change indices
    changeIndices = getChangePoints(power, likelihoods, windowSize=voting, minDist=minDist)

    return changeIndices

def findUniqueStates(power, changeIndices, thres, minDist):
    LINE_NOISE = 1.0

    # Get State Seuence from all state changes
    # Handle start state
    stateSequence = [{'index': 0, 'endIndex': changeIndices[0] if len(changeIndices) > 0 else len(power)}]
    # Changes in between
    for i, change in enumerate(changeIndices[:-1]):
        stateSequence.append({'index': change, 'endIndex': changeIndices[i+1]})
    # handle end state
    if len(changeIndices) > 0: stateSequence.append({'index': changeIndices[-1], 'endIndex': len(power)-1})


    # Get Steady states point after each state change
    for i in range(len(stateSequence)):
        slice = power[ stateSequence[i]['index'] : stateSequence[i]['endIndex'] ]
        stateSequence[i]['ssIndex'] = int(stateSequence[i]['index']+minDist )
        stateSequence[i]['ssEndIndex'] = int(max(stateSequence[i]['endIndex']-minDist/2, stateSequence[i]['ssIndex']+1))
        
    # Construct mean value of state
    for i in range(len(stateSequence)):
        if stateSequence[i]['ssIndex'] is None or stateSequence[i]['ssEndIndex'] is None or stateSequence[i]['ssEndIndex'] - stateSequence[i]['ssIndex'] < 1:
            stateSequence[i]['mean'] = None
        else:
            stateSequence[i]['mean'] = np.mean(power[stateSequence[i]['ssIndex']:stateSequence[i]['ssEndIndex']])
            if stateSequence[i]['mean'] <= LINE_NOISE: stateSequence[i]['mean'] = 0


    means = sorted([stateSequence[i]['mean'] for i in range(len(stateSequence))])
    print(means)
    cluster = 0
    clusters = [0]
    # lastMean = means[0]
    # for i in range(1, len(means)):
    #     if abs(lastMean-means[i]) > thres:
    #         lastMean = means[i]
    #         cluster += 1
    #     # lastMean = np.mean(np.array([means[i], lastMean]))
    #     clusters.append(cluster)
    
    for i in range(1, len(means)):
        if abs(means[i-1]-means[i]) > thres:
            cluster += 1
        clusters.append(cluster)

    for i in range(len(stateSequence)):
        stateSequence[i]["stateID"] = clusters[means.index(stateSequence[i]['mean'])]


    # prevent Self loops
    if len(stateSequence) > 1:
        newStateSequence = []
        source = stateSequence[0]
        for i in range(len(stateSequence)-1):
            dest = stateSequence[i+1]
            if source["stateID"] == dest["stateID"]:
                source['endIndex'] = dest["endIndex"]
                source['ssEndIndex'] = dest["ssEndIndex"]
                #recalculate mean based on the length of the arrays
                source['mean'] = (source['mean'] * (source['endIndex'] - source['index']) + dest["mean"] * (dest['endIndex'] - dest['index']))/(dest['endIndex'] - source['index'])
            else:
                newStateSequence.append(source)
                if dest == stateSequence[-1]:
                    newStateSequence.append(dest)
                source = dest
        stateSequence = newStateSequence


    return stateSequence


def autoLabel(request):
    if request.method != "POST": Http404
    
    response = {}

    data = json.loads(request.body)
    parameter = data["parameter"]
    
    if "type" not in data: data["type"] = ""
    if "filename" not in data: data["filename"] = None 

    if REDDData is not None:
        dataDict = REDDData
    else:
        filePath = getFilePath(data["type"], data["filename"])

        print(filePath)


        info = mkv.info(filePath)["streams"]
        # Just the info for 1st audio in file
        streamInfo = next(s for s in info if s["type"] == "audio")
        for consumer in webSockets: 
            data = {
                "status":"Loading Data in high resolution: {}Hz".format(streamInfo["samplingrate"]),
                "percent": 10
                }
            consumer.sendDict(data)

        streamIndex = streamInfo["streamIndex"]

        dataDict = mkv.loadAudio(filePath, streamsToLoad=streamIndex)[0]

    usablePower = ["s", "s_l1", "p", "p_l1"]

    usableKeys = list(set(usablePower) & set(dataDict["measures"]))
    if len(usableKeys) < 1: 
        if "v" in dataDict["measures"] and "i" in dataDict["measures"]:
            pass
            p,q,s = calcPowers(dataDict["data"]["v"], dataDict["data"]["i"], dataDict["samplingrate"])
            power = s
            response["msg"] = "Calculated apparent power using Current and Voltage"
        else:
            response["msg"] = "Could not find power, or voltage and current in data."
            return JsonResponse(response)
    else:
        power = list(dataDict["data"][sorted(usableKeys)[-1]])

    # power = resample(power, dataDict["samplingrate"], 1) 
    # print(power)
    # sr = 1

    sr = dataDict["samplingrate"]
    thres = 5.0
    if "thres" in parameter: thres = float(parameter["thres"])
    pre = 1.0*sr
    if "pre" in parameter: pre = int(float(parameter["pre"])*sr)
    post = 1.0*sr
    if "post" in parameter: post = int(float(parameter["post"])*sr)
    vote = 2.0*sr
    if "voting" in parameter: voting = int(float(parameter["voting"])*sr)
    minDist = 1.0*sr
    if "minDist" in parameter: minDist = int(float(parameter["minDist"])*sr)
    m = 0.005
    if "linearCoeff" in parameter: m = float(parameter["linearCoeff"])
    print("sr: {}Hz, thres: {}W, pre: {}samples, post: {}:samples, voting: {}samples, minDist: {} samples, m:{}".format(sr, thres, pre, post, voting, minDist, m), flush=True)
    
    for consumer in webSockets: 
        data = {
            "status":"Finding Events...",
            "percent": 20
            }
        consumer.sendDict(data)
    changeIndices = findEvents(power, thres, pre, post, voting, minDist, m)


    for consumer in webSockets: 
        data = {
            "status":"Clustering Events...",
            "percent": 70
            }
        consumer.sendDict(data)
    stateSequence = findUniqueStates(power, changeIndices, thres, minDist)

    if len(changeIndices) == 0:
        response["msg"] = "No Changes found in signal..."

    if len(changeIndices) >= 200:
        response["msg"] = "Too many events found, you may want to change settings"
        changeIndices = []
    print(changeIndices)


    for consumer in webSockets: 
        data = {
            "status":"Generating Labels...",
            "percent": 100
            }
        consumer.sendDict(data)
    # Convert change indices to timestamps
    ts = 0
    if "timestamp" in dataDict: ts = dataDict["timestamp"]
    # labels = [{"startTs": ts+(float(i/sr)), "label":""} for i in changeIndices]
    labels = [{"startTs": ts+(float(i["index"]/sr)), "label":"S" + str(i["stateID"])} for i in stateSequence]
    response["labels"] = labels

    return JsonResponse(response)

import os
from django.conf import settings
from django.http import HttpResponse,StreamingHttpResponse, Http404
from wsgiref.util import FileWrapper
from django.http import FileResponse
DEBUG_FFMPEG = True

def downloadMKV(request):
    if request.method != "POST": Http404
    
    data = json.loads(request.POST.get('data'))
    dataFormat = data["format"].lower()
    if dataFormat != "mkv":
        subFormat = dataFormat
    else:
        subFormat = "srt"

    includeData = data["includeData"]
    ev = data["events"]
    events = [{"ts":float(value["ts"]), "label":value["label"] if "label" in value else ""} for _,value in ev.items()]
    # for key, value in eventsRaw.items():
    #     if "label" not in value: value["label"] = ""
    #     events.append({"ts":float(value["ts"]), "label":value["label"]})
    events = sorted(events, key=lambda k: k['ts'])

    tmpFiles = []

    if "type" not in data: data["type"] = ""
    if "filename" not in data: data["filename"] = None

    if data["type"] == "REDD":
        if REDDData is not None:
            tmpRangeData = os.path.join(MEDIA_ROOT, "tmp_data.mkv")
            mkv.makeMkv([REDDData], tmpRangeData, verbose=DEBUG_FFMPEG)
            filePath = tmpRangeData
        else:
            return
    else:
        filePath = getFilePath(data["type"], data["filename"])
    
    origFileName = filePath

    info = mkv.info(filePath)["streams"]
    # Just the info for 1st audio in file
    streamInfo = next(s for s in info if s["type"] == "audio")

    streamIndex = streamInfo["streamIndex"]

    ts = 0
    if "timestamp" in streamInfo: ts = streamInfo["timestamp"]
    duration = streamInfo["duration"]
    
    # Maybe we have to cut the data here
    selRange = None
    if "range" in data:
        selRange = data["range"]
        print(hp.time_format_ymdhms(selRange[0]) + "->" + hp.time_format_ymdhms(selRange[1]))

        start = selRange[0] - ts
        stop = selRange[1] - ts
        duration = stop - start
        ts = selRange[0]
        
        if includeData:
            tmpRangeData = os.path.join(MEDIA_ROOT, "range_" + os.path.basename(filePath))
            # Force reencode s.t. timestamps match. copy somehow causes problems
            systemCall = "ffmpeg -hide_banner -i {} -map 0 -c:a wavpack -map_metadata 0 -metadata:s:a:0 timestamp=\"{}\" -ss {:.3f} -t {:.3f} -y {}".format(filePath, selRange[0], float(start), round(duration, 3), tmpRangeData)
            mkv.__call_ffmpeg(systemCall, verbose=DEBUG_FFMPEG)

            
            # This is with data loading and making mkv but its fucking slow
            # dataList = next(mkv.chunkLoad(filePath, duration, starttime=start, stoptime=stop))[0]
            # if "TIMESTAMP" in dataList["metadata"]:  dataList["metadata"]["TIMESTAMP"] = dataList["timestamp"]
            # print(selRange[0])
            # print(dataList["timestamp"])
            # tmpRangeData = os.path.join(MEDIA_ROOT, "tmp_data.mkv")
            # mkv.makeMkv([dataList], tmpRangeData, verbose=DEBUG_FFMPEG)
            
            filePath = tmpRangeData
            returnedFile = tmpRangeData


    # Convert to pysubs2
    subs = SSAFile()    
    # If we have only one state
    for i in range(len(events)):
        start = events[i]["ts"]/1000 - ts
        if i+1 >= len(events): end = duration
        else: end = events[i+1]["ts"]/1000 - ts

        # If range was selected remove events outside bounds and cap the events to boarder
        if start < 0 and end < 0: continue
        if start > duration: continue
        
        # Cap 
        start = max(start, 0)
        end = min(end, duration)
        
        print(hp.time_format_ymdhms(ts+events[i]["ts"]/1000) + "->" + events[i]["label"])
        ev = SSAEvent(start=make_time(s=start), end=make_time(s=end), text=events[i]["label"])
        subs.append(ev)
    # FFMPeg does not like empty subtitles
    if len(subs) == 0:
        subs.append(SSAEvent(start=make_time(s=0), end=make_time(s=0), text="empty"))

    # Store as ass file 
    # NOTE: Use srt here, as pysubs2 uses 10h timestamp limit
    # MKV convert to ass is not limited to 10h
    tmpSubFileName = os.path.join(MEDIA_ROOT, "tmp_sub." + subFormat)
    tmpFiles.append(tmpSubFileName)
    subs.save(tmpSubFileName, encoding="utf-8")
    returnedFile = tmpSubFileName

    goalFilePath = os.path.join(MEDIA_ROOT, "subbed_" + os.path.basename(filePath))

    if dataFormat == "mkv":
        tmpSubMKVFileName = os.path.join(MEDIA_ROOT, "tmp_sub.mkv")
        tmpFiles.append(tmpSubMKVFileName)
        # Convert to MKV and set correct title
        systemCall = "ffmpeg -hide_banner -i {} {} -y {}".format(tmpSubFileName, mkv.makeMetaArgs(streamInfo["title"], "subtitle"), tmpSubMKVFileName)
        mkv.__call_ffmpeg(systemCall, verbose=DEBUG_FFMPEG)
        returnedFile = tmpSubMKVFileName

    if includeData:
        systemCall = "ffmpeg -hide_banner -i {} -i {} -c copy -map 0:{} -map 1:0 -y {}".format(filePath, tmpSubMKVFileName, streamIndex, goalFilePath)
        mkv.__call_ffmpeg(systemCall, verbose=DEBUG_FFMPEG)
        returnedFile = goalFilePath
    
    # Resonse file
    filename = os.path.basename(origFileName).split(".")[0] + "." + dataFormat
    if selRange is not None: filename = "range_" + filename
    if not includeData: filename = "subs_" + filename

    chunk_size = 8192
    response = StreamingHttpResponse(
        FileWrapper(open(returnedFile, 'rb'), min(chunk_size, os.path.getsize(returnedFile))),
        content_type="application/octet-stream"
    )
    response['Content-Length'] = os.path.getsize(returnedFile)    
    response['Content-Disposition'] = "attachment; filename=%s" % filename
    return response

supportedFiles = {"mkv":loadMKV}
supportedLabelFiles = {"csv":loadCSV,"srt":loadSRTASS,"ass":loadSRTASS}