from decouple import config
import sys, os
from .analyze.analyzeSignal import calcPowers
from .analyze.pereiraChangeOfMean import pereiraLikelihood, getChangePoints, cleanLikelihoods

from .websocket import wsManager
from . import data as dataHp
import json

import numpy as np

from django.http import JsonResponse


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
    # if len(stateSequence) > 1:
    #     newStateSequence = []
    #     source = stateSequence[0]
    #     for i in range(len(stateSequence)-1):
    #         dest = stateSequence[i+1]
    #         if source["stateID"] == dest["stateID"]:
    #             source['endIndex'] = dest["endIndex"]
    #             source['ssEndIndex'] = dest["ssEndIndex"]
    #             #recalculate mean based on the length of the arrays
    #             source['mean'] = (source['mean'] * (source['endIndex'] - source['index']) + dest["mean"] * (dest['endIndex'] - dest['index']))/(dest['endIndex'] - source['index'])
    #         else:
    #             newStateSequence.append(source)
    #             if dest == stateSequence[-1]:
    #                 newStateSequence.append(dest)
    #             source = dest
    #     stateSequence = newStateSequence


    return stateSequence


def autoLabel(request):
    if request.method != "POST": Http404
    
    response = {}

    data = json.loads(request.body)
    parameter = data["parameter"]

    sessionID = request.session.session_key

    sessionData = request.session.get('dataInfo', {})

    if sessionData["type"] == "fired":
        wsManager.sendStatus(sessionID, "Loading 50Hz power data...", percent=10)
    dataDict = dataHp.getSessionData(sessionID, sessionData)

    channel = 0
    if "channel" in parameter:
        channel = parameter["channel"]
    
    if (channel > len(dataDict["measures"])-1):
        response["msg"] += "Error: cannot select this specific channel index: {}".format(channel)
        return JsonResponse(response)
    channelName = dataDict["measures"][channel]
    # usablePower = ["s", "s_l1", "p", "p_l1"]

    # usableKeys = list(set(usablePower) & set(dataDict["measures"]))
    # if len(usableKeys) < 1: 
    #     if "v" in dataDict["measures"] and "i" in dataDict["measures"]:
    #         pass
    #         p,q,s = calcPowers(dataDict["data"]["v"], dataDict["data"]["i"], dataDict["samplingrate"])
    #         power = s
    #         response["msg"] = "Calculated apparent power using Current and Voltage"
    #     else:
    #         response["msg"] = "Could not find power, or voltage and current in data. Name it as \"p\",\"s\" or \"v\",\"i\".\n"
    #         response["msg"] += "If you have electricity data of multiple supply legs, name it as \"<measure>_l1\", \"<measure>_l2\", ... accordingly.\n"
    #         response["msg"] += "Will continue with {}\n".format(dataDict["measures"][0])
    #         response["msg"] += "Resampled from {}Hz".format(dataDict["samplingrate"])
    #         power = dataDict["measures"][0]
    #         usableKeys = [power]

    #         #return JsonResponse(response)
    # else:
    #     power = list(dataDict["data"][sorted(usableKeys)[-1]])
    # channelName = sorted(usableKeys)[-1]
    sr = dataDict["samplingrate"]

    power = list(dataDict["data"][channelName])
    # We only do this at a max samplingrate of 50 Hz
    if sr > 50:
        wsManager.sendStatus(sessionID, text="Resampling from {} to 50Hz...".format(sr), percent=15)
        power, timestamps = dataHp.resampleDict(dataDict, channelName, 50, forceEvenRate=True)
        #power = dataHp.resample(power, sr, 50) 
        # print(power)
        sr = 50

    newSr = None
    if "sr" in parameter: newSr = float(parameter["sr"])
    if newSr != None and newSr != -1 or "ts" in dataDict:
        if "ts" in dataDict and newSr is None: newSr = max(1/3.0, dataDict["samplingrate"])
        wsManager.sendStatus(sessionID, text="Resampling to "+ str(round(newSr, 2)) + "Hz...", percent=17)
        power, timestamps = dataHp.resampleDict(dataDict, channelName, newSr, forceEvenRate=True)
        #power = dataHp.resample(power, sr, newSr) 
        sr = newSr


    thres = 5.0
    if "thres" in parameter: thres = float(parameter["thres"])
    thres = max(thres, 0.1)
    pre = 1.0*sr
    if "pre" in parameter: pre = int(float(parameter["pre"])*sr)
    pre = max(pre, 2)
    post = 1.0*sr
    if "post" in parameter: post = int(float(parameter["post"])*sr)
    post = max(post, 2)
    voting = 2.0*sr
    if "voting" in parameter: voting = int(float(parameter["voting"])*sr)
    voting = max(voting, 1)
    minDist = 1.0*sr
    if "minDist" in parameter: minDist = int(float(parameter["minDist"])*sr)
    minDist = max(minDist, 1)
    m = 0.005
    if "linearCoeff" in parameter: m = float(parameter["linearCoeff"])
    print(channelName)
    print("Channel:{}, sr: {}Hz, thres: {}W, pre: {}samples, post: {}:samples, voting: {}samples, minDist: {} samples, m:{}".format(str(channelName), sr, thres, pre, post, voting, minDist, m), flush=True)
    


    wsManager.sendStatus(sessionID, "Finding Events...", percent=20)
    changeIndices = findEvents(power, thres, pre, post, voting, minDist, m)

    wsManager.sendStatus(sessionID, "Clustering Events...", percent=70)
    stateSequence = findUniqueStates(power, changeIndices, thres, minDist)

    if len(changeIndices) == 0:
        response["msg"] = "No Changes found in signal..."

    if len(changeIndices) >= 200:
        response["msg"] = "Too many events found, you may want to change settings"
        changeIndices = []

    wsManager.sendStatus(sessionID, "Generating Labels...")
    # Convert change indices to timestamps
    ts = 0
    if "timestamp" in dataDict: ts = dataDict["timestamp"]
    # labels = [{"startTs": ts+(float(i/sr)), "label":""} for i in changeIndices]
    labels = [{"startTs": ts+(float(i["index"]/sr)), "label":"S" + str(i["stateID"])} for i in stateSequence]
    response["labels"] = labels

    return JsonResponse(response)
