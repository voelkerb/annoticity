import os
from .storage import OverwriteStorage
from . import data as dataHp
from . import chart
from .powerData import dataManager as dm

from annoticity.settings import PROJECT_ROOT, MEDIA_ROOT, MEDIA_URL
import numpy as np


from django.http import JsonResponse

def loadData(filePath, samplingrate=None):
    dataDict, _, _ =  dataHp.load(filePath)
    if samplingrate is not None and samplingrate != dataDict["samplingrate"]:
        dataHp.resample(dataDict["data"], dataDict["samplingrate"], samplingrate)
        dataDict["samplingrate"] = samplingrate
        dataDict["samples"] = len(dataDict["data"])

    return dataDict

# Register data provider
dataHp.dataProvider["uploaded"] = loadData

def dataUpload(request):
    response = {}
    if request.method == 'POST':
        if 'uploadedFile' not in request.FILES:
            response['msg'] = 'Please select the file to upload before'
        else:
            myfile = request.FILES['uploadedFile']
            filename = myfile.name
            
            sessionID = request.session.session_key

            WORKING_FOLDER = os.path.join(MEDIA_ROOT, sessionID)
            if not os.path.exists(WORKING_FOLDER): os.makedirs(WORKING_FOLDER, exist_ok=True)

            fs = OverwriteStorage(os.path.join(MEDIA_URL, sessionID))
            # store new file
            filename = fs.save(myfile.name, myfile)

            filePath = os.path.join(WORKING_FOLDER, filename)
            
            dataDict, error, warning =  dataHp.load(filePath)
            # Return on error IMPORTANT
            if error is not None:
                response['msg'] = error
                return JsonResponse(response)
            else:
                if warning is not None: 
                    response['msg'] = warning
                response['uploaded_success'] = True
            # TODO
            # newDataReinit()

            # Get uploaded file of previous session
            prevFile = request.session.get('uploadedFile', None)
            # print(prevFile)
            # Delete old file if existing
            if prevFile is not None and os.path.exists(prevFile): fs.delete(prevFile)

            # Set global session data
            request.session["uploadedFile"] = filePath
            # request.session["dataInfo"] = {"type":"uploaded", "filePath":filePath}
            request.session["dataInfo"] = {"type":"uploaded", "filePath":filePath, "args": (filePath,)}
            # Add data to global dataManager
            dm.add(sessionID, dataDict)
               
            response['filename'] = os.path.basename(filePath)
            response.update(chart.responseForInitChart(dataDict, measures=dataDict["measures"]))

            if dataDict["timestamp"] == 0: response['timeZone'] = "UTC"

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