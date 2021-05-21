import subprocess
import os
from datetime import datetime
import pytz
import sys
import h5py
import numpy as np
import argparse
import json 

BASE_PATH = None
DATE_FORMAT = "%Y-%m-%d"
DATE_FORMAT_EXT = "%Y-%m-%d %H.%M.%s"

def getTimeZone():
    return pytz.timezone("Europe/Berlin")

def checkBasePath():
    if BASE_PATH is None: raise Exception("ECO Base path not set yet!")

def getHouses():
    checkBasePath()
    houses = [int(h) for h in os.listdir(BASE_PATH) if os.path.isdir(os.path.join(BASE_PATH, h)) and h.isdigit()]
    return sorted(houses)

def getMeters(house):
    housePath = os.path.join(BASE_PATH, "{:02d}".format(house))
    if not os.path.exists(housePath): return []
    meters = [int(h) for h in os.listdir(housePath) if os.path.isdir(os.path.join(housePath, h)) and h.isdigit()]
    return sorted(meters)

def getTsFromFileName(fn):
    try:
        return datetime.strptime(fn, DATE_FORMAT + ".csv").timestamp()
    except ValueError:
        try:
            return datetime.strptime(fn, DATE_FORMAT_EXT + ".csv").timestamp()
        except:
            return -1
    return -1

def getTimeRange(house, meter):
    path = os.path.join(BASE_PATH, "{:02d}".format(house), "{:02d}".format(meter))
    if not os.path.exists(path): return []
    files = [h for h in os.listdir(path) if os.path.isfile(os.path.join(path, h))]
    files = [f for f in files if f.split(".")[-1].lower() == "csv"]
    files = sorted(files)
    ranges = []
    lastFile = files[0]
    lastStart = files[0]
    for f in files[1:]:
        lastTs = getTsFromFileName(lastFile)
        newTs = getTsFromFileName(f)
        if newTs != lastTs + 24*60*60:
            startTs = getTsFromFileName(lastStart)
            stopTs = getTsFromFileName(lastFile)+24*60*60-1
            lastStart = f
            ranges.append([startTs, stopTs])
        lastFile = f
    
    startTs = getTsFromFileName(lastStart)
    stopTs = getTsFromFileName(lastFile)+24*60*60-1
    ranges.append([startTs, stopTs])

    # startTs = datetime.strptime(files[0].split(".")[0], DATE_FORMAT).timestamp()
    # stopTs = datetime.strptime(files[-1].split(".")[0], DATE_FORMAT).timestamp()+24*60*60-1
    return ranges

ecolabels = None
def loadLabelsJson():
    global ecolabels
    if ecolabels is None:
        APPLIANCE_LOG_FILENAME = os.path.join(BASE_PATH, 'labels.json')
        with open(APPLIANCE_LOG_FILENAME) as json_file:
            ecolabels = json.load(json_file)
    return ecolabels

def getDevice(house, meter):
    if meter == 0: return "mains"
    labels = loadLabelsJson()
    h = str(house)
    m = str(meter)
    if h in labels and m in labels[h]: return labels[h][m]["name"]
    return "Unknown"

def getDeviceInfo(house, meter):
    labels = loadLabelsJson()
    h = str(house)
    m = str(meter)
    if h in labels and m in labels[h]: 
        return labels[h][m]["info"]
    return None
    
def loadCSV(path, delimiter=","):
    data = np.genfromtxt(path, delimiter=',', encoding="utf8")
    return data

def getFile(house, meter, day):
    dayStr = day.strftime(DATE_FORMAT)
    path = os.path.join(BASE_PATH, "{:02d}".format(house), "{:02d}".format(meter), dayStr + ".csv")
    # See if path exists, if not look if substring exists (started in the middle of the day)
    if not os.path.exists(path): 
        folder = os.path.join(BASE_PATH, "{:02d}".format(house), "{:02d}".format(meter))
        files = [h for h in os.listdir(folder) if os.path.isfile(os.path.join(folder, h))]
        files = [f for f in files if f.split(".")[-1].lower() == "csv"]
        matching = [f for f in files if dayStr in f]
        if len(matching) > 0: return matching[0]
        return None
    return os.path.join(BASE_PATH, "{:02d}".format(house), "{:02d}".format(meter), dayStr + ".csv")

mappingSM = {'p_l1':1, 'p_l2':2, 'p_l3':3, 'i_rms_l1':5, 'i_rms_l2':6, 'i_rms_l3':7, 'v_rms_l1':8, 'v_rms_l2':9, 'v_rms_l3':10}
def load(house, meter, day):
    dayStr = day.strftime(DATE_FORMAT)
    filePath = getFile(house, meter, day)
    loaded = loadCSV(filePath)
    if meter == 0:
        wtype = np.dtype([(k, np.float32) for k in mappingSM.keys()])
        data = np.empty(len(loaded), dtype=wtype)
        for k in mappingSM.keys():        
            data[k] = np.array(loaded[:,mappingSM[k]])
    else:
        wtype = np.dtype([('p',np.float32)])
        data = np.recarray(len(loaded), dtype=wtype)
        data["p"] = np.array(loaded)
    startTs = day.timestamp()
    stopTs = startTs + len(data)
    title = getDevice(house, meter)
    dataDict = {"title": title, "house": house, "meter": meter, "samplingrate": 1, "timestamp": getTsFromFileName(filePath),
                "data": data, "timestamp":startTs, "measures":list(data.dtype.names), "duration":stopTs-startTs,
                "samples": len(data)}
    info = getDeviceInfo(house, meter)
    if info is not None: dataDict["info"] = info
    return dataDict

def initParser():
    parser = argparse.ArgumentParser()
    parser.add_argument("--path", type=str, default="/Users/voelkerb/NILM_Datasets/ECO",
                        help="Root path of the BLOND dataset.")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Increase output verbosity")
    return parser

if __name__ == "__main__":
    parser = initParser()
    args = parser.parse_args()

    BASE_PATH = args.path

    houses = getHouses()
    print(houses)

    for h in houses:
        meters = getMeters(h)
        print(str(h) + ": " + str(meters))
        for meter in meters:
            timeranges = getTimeRange(h, meter)
            print("\t" + str(meter) + " - tr: " + str(timeranges))
    load(1, 0, datetime.strptime("2012-06-01", DATE_FORMAT))