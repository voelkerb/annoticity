
import csv
import pandas as pd
import pysubs2
import numpy as np
import os
from datetime import datetime
from annoticity.settings import PROJECT_ROOT, MEDIA_ROOT, MEDIA_URL
import subprocess

from django.http import JsonResponse

from .storage import OverwriteStorage


# If user uploaded labels, we need to parse these and return them
def labelUpload(request):
    response = {}
    if request.method == 'POST':
        if 'uploadedFile' not in request.FILES:
            response['msg'] = 'Please select the file to upload before'
        else:
            myfile = request.FILES['uploadedFile']
            filename = myfile.name
            ts = request.POST.get("timestamp")
            if ts is not None: ts = float(ts)
            else: ts = 0

            sessionID = request.session.session_key
            WORKING_FOLDER = os.path.join(MEDIA_ROOT, sessionID)
            if not os.path.exists(WORKING_FOLDER): os.makedirs(WORKING_FOLDER, exist_ok=True)

            fs = OverwriteStorage(os.path.join(MEDIA_URL, sessionID))
            # store new file
            filename = fs.save(myfile.name, myfile)

            filePath = os.path.join(WORKING_FOLDER, filename)

            lbls, error, warning = load(filePath, ts=ts)

            if error is not None: response['msg'] = error
            else:
                response["labels"] = lbls
                if warning is not None: response["msg"] = warning
            # Delete file after it has been processed
            subprocess.check_output(["rm", "-rf", filePath])
    return JsonResponse(response)


def load(fp, ts=0):
    suffix = fp.split(".")[-1].lower()
    if suffix not in supportedLabelFiles.keys(): 
        error = 'Sorry, currently only the following file types are supported: ' + ",".join(list(supportedLabelFiles.keys()))
        return None, error, None
    return supportedLabelFiles[suffix](fp, ts=ts)


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




supportedLabelFiles = {"csv":loadCSV,"srt":loadSRTASS,"ass":loadSRTASS}