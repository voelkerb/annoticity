
from pysubs2 import SSAFile, SSAEvent, make_time

from .websocket import wsManager
from .powerData import dataManager as dm
from . import data as dataHp

from annoticity.settings import PROJECT_ROOT, MEDIA_ROOT, MEDIA_URL
from decouple import config

import os, sys
from .mkv.mkv import mkv as mkv
from .usefulFunctions import time_format_ymdhms as timeStr

from django.conf import settings
from django.http import HttpResponse,StreamingHttpResponse, Http404
from wsgiref.util import FileWrapper
from django.http import FileResponse

from datetime import datetime, timedelta
import time
import subprocess
import json


DEBUG_FFMPEG = True

def download(request):
    # must be a post method
    if request.method != "POST": Http404
    # Get data from post
    data = json.loads(request.POST.get('data'))
    # Get data format
    dataFormat = data["format"].lower()

    # for Mkv subformat must be srt
    if dataFormat != "mkv": subFormat = dataFormat
    else: subFormat = "srt"

    # Se if we want to include the data
    includeData = data["includeData"]
    # Get labels, convert and sort them
    ev = data["events"]
    events = [{"ts":float(value["ts"]), "label":value["label"] if "label" in value else ""} for _,value in ev.items()]
    events = sorted(events, key=lambda k: k['ts'])


    sessionID = request.session.session_key
    sessionInfo = request.session.get('dataInfo', {"type":"unknown"})

    WORKING_FOLDER = os.path.join(MEDIA_ROOT, sessionID)
    if not os.path.exists(WORKING_FOLDER): os.makedirs(WORKING_FOLDER, exist_ok=True)

    # Files used for creation, that need to be removed at the end
    tmpFiles = []
    # First lets remove all old files in the directory
    for a in os.listdir(WORKING_FOLDER):
        print(a)
        f = os.path.join(WORKING_FOLDER, a)
        if "filePath" in sessionInfo and f == sessionInfo["filePath"]: continue
        subprocess.check_output(["rm", "-rf", f])

    wsManager.sendStatus(sessionID, "Gathering data...", percent=10)
    # We need to create mkv first
    if sessionInfo["type"] in ["fired", "uploaded"]:
        filePath = sessionInfo["filePath"]

        info = mkv.info(filePath)["streams"]
        # Just the info for 1st audio in file
        dataDict = next(s for s in info if s["type"] == "audio")
        streamIndex = dataDict["streamIndex"]
    else:
        fn = sessionInfo["filePath"]
        filePath = os.path.join(WORKING_FOLDER, fn)
        
        dataDict = dataHp.getSessionData(sessionID, sessionInfo)
        if dataDict is None:
            wsManager.sendStatus(sessionID, "Error getting {} data!".format(sessionInfo["type"].upper()))
            return

        if includeData:
            wsManager.sendStatus(sessionID, "Creating MKV from {} data...".format(sessionInfo["type"].upper()), percent=20)
            # Should be deleted afterwards
            tmpFiles.append(filePath)
            mkv.makeMkv([dataDict], filePath, verbose=DEBUG_FFMPEG)

        streamIndex = 0


    origFileName = filePath

    ts = 0
    if "timestamp" in dataDict: ts = dataDict["timestamp"]
    duration = dataDict["duration"]
    
    # Maybe we have to cut the data here as we want only a range
    selRange = None
    if "range" in data:
        selRange = data["range"]
        print("Range:" + timeStr(selRange[0]) + "->" + timeStr(selRange[1]))

        start = selRange[0] - ts
        stop = selRange[1] - ts
        duration = stop - start
        ts = selRange[0]
        
        # Cut the data for range
        if includeData:
            wsManager.sendStatus(sessionID, "Cutting data to selected range...", percent=50)
            tmpRangeData = os.path.join(WORKING_FOLDER, "range_" + os.path.basename(filePath))
            # Force reencode s.t. timestamps match. copy somehow causes problems
            systemCall = "ffmpeg -hide_banner -i {} -map 0 -c:a wavpack -map_metadata 0 -metadata:s:a:0 timestamp=\"{}\" -ss {:.3f} -t {:.3f} -y {}".format(filePath, selRange[0], float(start), round(duration, 3), tmpRangeData)
            mkv.__call_ffmpeg(systemCall, verbose=DEBUG_FFMPEG)

            tmpFiles.append(tmpRangeData)
            # This is with data loading and making mkv but its fucking slow
            # dataList = next(mkv.chunkLoad(filePath, duration, starttime=start, stoptime=stop))[0]
            # if "TIMESTAMP" in dataList["metadata"]:  dataList["metadata"]["TIMESTAMP"] = dataList["timestamp"]
            # print(selRange[0])
            # print(dataList["timestamp"])
            # tmpRangeData = os.path.join(MEDIA_ROOT, "tmp_data.mkv")
            # mkv.makeMkv([dataList], tmpRangeData, verbose=DEBUG_FFMPEG)
            
            filePath = tmpRangeData


    wsManager.sendStatus(sessionID, "Creating subtitles from labels..", percent=75)
    # Convert events to pysubs2
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
        
        # print(timeStr(ts+events[i]["ts"]/1000) + "->" + events[i]["label"])
        label = events[i]["label"]
        if label == "" or label.isspace(): label = "unknown" 
        ev = SSAEvent(start=make_time(s=start), end=make_time(s=end), text=label)
        subs.append(ev)
    # FFMpeg does not like empty subtitles
    if len(subs) == 0:
        subs.append(SSAEvent(start=make_time(s=0), end=make_time(s=0), text="empty"))

    # Store as ass file 
    # NOTE: Use srt here, as pysubs2 uses 10h timestamp limit
    # MKV convert to ass is not limited to 10h
    tmpSubFileName = os.path.join(WORKING_FOLDER, "tmp_sub." + subFormat)
    subs.save(tmpSubFileName, encoding="utf-8")
    returnedFile = tmpSubFileName

    goalFilePath = os.path.join(WORKING_FOLDER, "subbed_" + os.path.basename(filePath))

    if dataFormat == "mkv":
        tmpFiles.append(tmpSubFileName)
        wsManager.sendStatus(sessionID, "Converting labels to MKV..", percent=85)
        tmpSubMKVFileName = os.path.join(WORKING_FOLDER, "tmp_sub.mkv")
        # Convert to MKV and set correct title
        systemCall = "ffmpeg -hide_banner -i {} {} -y {}".format(tmpSubFileName, mkv.makeMetaArgs(dataDict["title"], "subtitle"), tmpSubMKVFileName)
        mkv.__call_ffmpeg(systemCall, verbose=DEBUG_FFMPEG)
        returnedFile = tmpSubMKVFileName

    if includeData:
        tmpFiles.append(tmpSubMKVFileName)
        wsManager.sendStatus(sessionID, "Merging data and labels ...", percent=95)
        systemCall = "ffmpeg -hide_banner -i {} -i {} -c copy -map_metadata 0  -map 0:{} -map 1:0 -y {}".format(filePath, tmpSubMKVFileName, streamIndex, goalFilePath)
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

    for t in tmpFiles:
        print(t)
        subprocess.check_output(["rm", "-rf", t])
    wsManager.sendTask(sessionID, "dismissProgressbar")
    return response
