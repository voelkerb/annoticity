
# %%
# import subprocess
import os
from datetime import datetime, timedelta, timezone
import sys
import h5py
import numpy as np
import argparse
import json 
import pytz
import subprocess
import math
import numpy.lib.recfunctions


BASE_PATH = None
DOWNLOAD_PATH = "tmp"
DATE_FORMAT = "%Y-%m-%d"
DATE_FORMAT_HF = "%Y-%m-%dT%H-%M-%S.%fT%z"
VERBOSE = False
labels = None

KEEP_DOWNLOADS = True
COLLECT_DOWNLOADS = True

_loadedFiles = []

def printLabels(labels):
    """Print the given labels"""
    for medal_id in labels:
        circuit_id = labels[medal_id]["circuit_id"]
        entries = labels[medal_id]["entries"]
        print(medal_id + ":")
        print("\tcircuit_id:" + str(circuit_id))
        print("\entries:" + str(entries))

def getCircuitForMedalID(id):
    """Get the cricuit ID (L1-L3) for given id"""
    global labels
    if labels is None: labels = loadLabelsJson()
    return labels["MEDAL-" + id]["circuit_id"]

def getEntryForMedalID(id):
    """Get the entries for given id"""
    global labels
    if labels is None: labels = loadLabelsJson()
    return labels["MEDAL-" + str(id)]["entries"]

def medalEntries(id, dateStart, dateEnd):
    entries = getEntryForMedalID(id)
    lastEntry = None
    newEntries = []
    for entry in entries:
        date = datetime.strptime(entry["timestamp"], '%Y-%m-%dT%H-%M-%S')
        if len(newEntries) == 0 and dateStart < date and lastEntry is not None: newEntries.append(lastEntry)
        if dateStart < date and date < dateEnd: newEntries.append(entry)
        lastEntry = entry
    return newEntries

def devicesFromEntries(socket, entries):
    return [entry["socket_"+str(socket)] for entry in entries]

def uniqueNameForDevices(devices):
    name = ""
    lastDev = None
    for entry in devices: 
        if entry != lastDev:
            subName = ""
            if entry['class_name'] is not None: subName += entry['class_name'] + "_"
            if entry['appliance_name'] is not None: subName += entry['appliance_name']
            if subName == "": subName = "Nothing connected"
            name += subName.rstrip(" ") + ", "
            lastDev = entry
    return name.rstrip(", ")

def getPhase(medal):
    global labels
    if labels is None: labels = loadLabelsJson()
    if medal.upper() not in labels: return -1
    return int(labels[medal.upper()]["circuit_id"].lstrip("L"))


def loadLabelsJson():
    APPLIANCE_LOG_FILENAME = os.path.join(BASE_PATH, 'appliance_log.json')
    with open(APPLIANCE_LOG_FILENAME) as json_file:
        data = json.load(json_file)
        return data

def delDownloads():
    global _loadedFiles
    for f in _loadedFiles: 
        try: subprocess.check_output(["rm", f])
        except subprocess.CalledProcessError: pass
    _loadedFiles = []

def ftpGetFile(url, destinationPath, fileName=None):
    fn = fileName
    if fn is None:
        fn = os.path.basename(url)
    if not os.path.exists(DOWNLOAD_PATH):
        os.makedirs(DOWNLOAD_PATH, exist_ok=True)
    path = os.path.join(destinationPath, fn)
    # Look if path already exists
    if os.path.exists(path): return path
    # If not download using Ftp
    command = "curl -o {} {}".format(path, url)
    if VERBOSE: OUT = subprocess.PIPE 
    else: OUT = open(os.devnull, 'w')
    process = subprocess.Popen(command, stdout=OUT, stderr=OUT, shell=True)
    process.wait()
    if VERBOSE: print(path)
    if COLLECT_DOWNLOADS: _loadedFiles.append(path)
    return path

def _channelCleaner(channel):
    if channel is None: return None
    ch = channel
    if not isinstance(ch, list): ch = [ch]
    # Converts string of channel to integer
    if len(ch) > 0 and isinstance(ch[0], str): ch = [int(str(c)[-1]) for c in ch]
    return ch

def loadHighFreqHDF5(fp, channels=None, startTs=None, stopTs=None):
    ch = _channelCleaner(channels)

    dataList = []
    base = os.path.basename(fp)
    
    # Thats a medal file
    if "medal" in base:
        # extract id
        medal_id = int(base.split("-")[1])
        if ch is None: ch = [i+1 for i in range(6)]
        name = "medal-" + str(medal_id) + ", socket<i>"
        device = "medal-" + str(medal_id)

    elif "clear" in base:
        device = "clear"
        name = "Mains L<i>"
        device = "clear"
        if ch is None: ch = [i+1 for i in range(3)]

    try:
        with h5py.File(fp, 'r', driver='core') as f:
            for c in ch:
                if VERBOSE: 
                    print([n for n in list(f)])
                    print([n for n in list(f.attrs)])
                vname = "voltage{}".format(c)
                if vname not in f: vname = "voltage"
                if vname not in list(f): continue

                # extract timestamp
                start_date = datetime(
                            year=int(f.attrs['year']),
                            month=int(f.attrs['month']),
                            day=int(f.attrs['day']),
                            hour=int(f.attrs['hours']),
                            minute=int(f.attrs['minutes']),
                            second=int(f.attrs['seconds']),
                            microsecond=int(f.attrs['microseconds']),
                            tzinfo=timezone(timedelta(hours=int(f.attrs['timezone'][1:4]), minutes=int(f.attrs['timezone'][4:]))),
                        )
                
                if VERBOSE: 
                    print(start_date)
                
                startI = 0
                stopI = len(f[vname]) 
                if startTs is not None:
                    sr = f.attrs['frequency']
                    startI = int((startTs-start_date.timestamp())*sr)
                    stopI = int((stopTs-start_date.timestamp())*sr)
                    assert startI < len(f[vname]), "Start Ts is after file"
                    assert stopI < len(f[vname]), "Stop Ts is after file"
                    assert startI < stopI, "Stop Ts is before Start Tsafter file"
                    # Does this work?
                    start_date += timedelta(seconds=startTs-start_date.timestamp())

                data = np.recarray((len(f[vname][startI:stopI]),), dtype=[("i", 'f4'),("v", 'f4')]).view(np.recarray)
                
                # data["v"] = f[vname][:] * 1.0 * f[vname].attrs['calibration_factor']
                # data["i"] = f['current{}'.format(c)][:] * 1000.0 * f['current{}'.format(c)].attrs['calibration_factor']

                data["v"] = f[vname][startI:stopI] * 1.0 * f[vname].attrs['calibration_factor']
                data["i"] = f['current{}'.format(c)][startI:stopI] * 1000.0 * f['current{}'.format(c)].attrs['calibration_factor']

                dataDict = {"device": device,
                            "socket": "L"+str(c) if "clear" in device else "Socket-"+str(c), 
                            "type": "audio", "title": "clear, L-"+str(c),
                            "title": name.replace("<i>", str(c)),
                            "samplingrate": f.attrs['frequency'], "measures": ["i","v"], "duration":len(data)/f.attrs['frequency'],
                            "samples":len(data),
                            "timestamp": start_date.timestamp(), 
                            "data": data}
                dataList.append(dataDict)
    except OSError:
        print("Error loading file: {}".format(fp))

    return dataList

def loadHDF5(fp, channels=None):
    ch = _channelCleaner(channels)

    dataList = []
    base = os.path.basename(fp)

    if "medal" in base:
        medal_id = int(os.path.basename(fp).split("medal-")[-1].split(".")[0])
        name = "medal-" + str(medal_id) + ", socket<i>"
        device = "medal-" + str(medal_id)
        if ch is None: ch = [i+1 for i in range(6)]

    elif "clear" in base:
        dayStr = base.split("summary-")[-1].split("-clear")[0]
        name = "Mains L<i>"
        device = "clear"
        if ch is None: ch = [i+1 for i in range(3)]
    try:
        with h5py.File(fp, 'r', driver='core') as f:  
            for c in ch:
                if VERBOSE: 
                    print([n for n in list(f)])
                    print([n for n in list(f.attrs)])
                if "apparent_power{}".format(c) not in list(f): continue
                ap = f["apparent_power{}".format(c)][:]
                data = np.recarray((len(ap),), dtype=[("s", 'f4'),("p", 'f4'),("q", 'f4'),("i_rms", 'f4'),("v_rms", 'f4')]).view(np.recarray)
                data["s"] = ap
                data["p"] = f["real_power{}".format(c)][:]
                # data["q"] = f["power_factor{}".format(c)][:]
                data["q"] = np.sqrt(np.abs(np.square(data["s"]) - np.square(data["p"])))
                data["i_rms"] = f["current_rms{}".format(c)][:]*1000.0
                vrms = "voltage_rms{}".format(c)
                if vrms not in f: vrms = "voltage_rms"
                data["v_rms"] = f[vrms][:]
                # extract timestamp
                start_date = datetime(year=int(f.attrs['year']),month=int(f.attrs['month']),day=int(f.attrs['day'])).timestamp()
                start_date += f.attrs['delay_after_midnight']
                start_date = datetime.fromtimestamp(start_date)
                if VERBOSE: 
                    print(start_date)

                dataDict = {"device": device,
                            "socket": "L"+str(c) if "clear" in device else "Socket-"+str(c), 
                            "type": "audio", "title": name.replace("<i>", str(c)), "samplingrate": 1, "measures": ["s","p","q","i_rms","v_rms"], "duration":24*60*60, "samples":len(data[0]),
                            "timestamp": start_date.timestamp(), "data": data}
                dataList.append(dataDict)
    except OSError:
        print("Error loading file: {}".format(fp))
    return dataList


SETS = ["BLOND-50", "BLOND-250"]
METERS = ["clear"] + ["medal-" + str(i) for i in range(1,16)]
DUR = { "BLOND-50":[datetime.strptime("2016-10-01", DATE_FORMAT).timestamp(), datetime.strptime("2017-04-30", DATE_FORMAT).timestamp()+24*60*60-1],
        "BLOND-250":[datetime.strptime("2017-05-12", DATE_FORMAT).timestamp(), datetime.strptime("2017-06-30", DATE_FORMAT).timestamp()+24*60*60-1]}

def shortDeviceList(medal, socket, tStart, tEnd):
    tSock = socket
    if not isinstance(tSock, str): tSock = "socket-" + str(tSock)
    if medal == "clear": return []
    medal_id = int(medal.split("-")[-1])
    entryLabels = medalEntries(medal_id, datetime.fromtimestamp(tStart), datetime.fromtimestamp(tEnd))
    connectedDevices = [entry[str(tSock.replace("-", "_"))] for entry in entryLabels]
    if len(connectedDevices) < 1: return []
    name = uniqueNameForDevices(connectedDevices).split(", ")
    return name
        
def getTimeZone():
    return pytz.timezone("Europe/Berlin")

def getAvailableSets():
    return SETS

def getAvailableMeters():
    return METERS

def getAvailableChannels(meter):
    if meter not in METERS: return []
    if "clear" in meter: return ["L1", "L2", "L3"]
    else: return ["socket-" + str(i+1) for i in range(6)]

def getAvailableDuration(SET):
    if SET not in SETS: return None
    return tuple(DUR[SET])

def urlFromFile(fp):
    base = os.path.basename(fp)
    isMedal = False
    if "medal" in base: isMedal = True 
    splits = base.split("-")[1:]
    if isMedal: 
        device = "medal-"+splits[0]
        del split[0]
    else: device = "clear"
        
    day = "-".join(splits).split("T")[0]
    date = datetime.strptime(day, DATE_FORMAT)
    print(day)
    print(device)
    _set = ""
    for s in SET:
        dur = getAvailableDuration(s)
        if dur[0] <= date.timestamp() <= dur[1]: 
            _set = s
            break
    print(_set)
    url = "ftp://m1375836:m1375836@dataserv.ub.tum.de//FD_Share_Kriechbaumer/BLOND/<SET>/<DAY>/<METER>/"
    url = url.replace("<SET>", str(_set))
    url = url.replace("<METER>", str(device))
    url = url.replace("<DAY>", date.strftime(DATE_FORMAT))
    return url

def loadHighFreqRange(SET, METER, channel:int, tStart, tStop):
    if SET not in ["BLOND-50", "BLOND-250"]: return None
    url = "ftp://m1375836:m1375836@dataserv.ub.tum.de//FD_Share_Kriechbaumer/BLOND/<SET>/<DAY>/<METER>/"
    url = url.replace("<SET>", str(SET))
    url = url.replace("<METER>", str(METER))

    # determine required files
    # Files are sorted in folders named by day, so determine start day first
    startD = datetime.fromtimestamp(tStart).replace(hour=0, minute=0, second=0, microsecond=0)
    reqFiles = []
    if VERBOSE:
        print(str(startD) + " > " + str(datetime.fromtimestamp(tStop)))
    # While stop day not reached
    while startD.timestamp() < tStop:

        # url to get file list
        nurl = url.replace("<DAY>", startD.strftime(DATE_FORMAT))
        files = fileList(nurl)
        # remove summary files and all other files except hdf5
        urls = [nurl + x for x in files if "summary" not in x and ".hdf5" in x]
        # extract timestamps from files
        times = [x for x in files if "summary" not in x and ".hdf5" in x]
        tss = [datetime.strptime("-".join(f.replace(METER,"").split("-")[1:-1]), DATE_FORMAT_HF).timestamp() for f in times]
        if len(tss) == 0: continue

        # All files in interval (e.g. if you want from 0:10:00-0:16:00 and files go 
        # like 0:05:00, 0:10:00, 0:15:00, 0:20:00 -> it will choose only 15:00)
        nreqFiles = [f for f,ts in zip(urls,tss) if tStart < ts and ts < tStop]
        # First file (e.g. if you want from 0:10:00 -> file at 0:10:00 is added)
        lastFile = None
        for f, ts in zip(urls,tss):
            if ts > tStart: break
            lastFile = f
        # if lastfile not determined, and time was not between two files it MUST be in the previous day
        if len(reqFiles) == 0 and tStart < tss[0] and lastFile is None:
            if VERBOSE: print("Need to use file from day before")
            dayBefore = startD - timedelta(days=1)
            nurl = url.replace("<DAY>", dayBefore.strftime(DATE_FORMAT))
            nFiles = fileList(nurl)
            lastFile = nurl + [x for x in nFiles if "summary" not in x and ".hdf5" in x][-1]
        if lastFile is not None:
            nreqFiles = [lastFile] + nreqFiles
        # Appned to other files
        reqFiles.extend(sorted(nreqFiles))
        startD += timedelta(days=1)
    data = None
    # files are sorted, so we can stop if file ts > tStop 
    for f in reqFiles: 
        if VERBOSE: print("Loading: {}".format(os.path.basename(f)))
        fp = ftpGetFile(f, DOWNLOAD_PATH)

        # quick and dirty way to just load the part of interest
        # TODO: Make this work for multiple files
        if len(reqFiles) == 1: nData = loadHighFreqHDF5(fp, channels=channel, startTs=tStart, stopTs=tStop)
        else: nData = loadHighFreqHDF5(fp, channels=channel)
        # nData = loadHighFreqHDF5(fp, channels=channel)

        # File may be broken, just delete it and try to get it one more time
        if len(nData) < 1: 
            print("File broke, try to repair once")
            try: subprocess.check_output(["rm", fp])
            except subprocess.CalledProcessError: pass
            fp = ftpGetFile(f, DOWNLOAD_PATH)
            nData = loadHighFreqHDF5(fp, channels=channel)
            if len(nData) < 1: 
                raise AssertionError("Error loading blond data")

        nData = nData[0]
        if data is None: data = nData
        else: data["data"] = np.concatenate((data["data"], nData["data"]))
        startD += timedelta(days=1)

    if data is not None:
        # FIX duration and length
        sampleStart = int((tStart - data["timestamp"])*data["samplingrate"])
        data["timestamp"] = tStart
        data["samples"] = int((tStop-tStart)*data["samplingrate"])
        # prevent memory leak
        new = np.recarray((data["samples"],), dtype=data["data"].dtype).view(np.recarray)
        cut = data["data"][sampleStart:sampleStart+data["samples"]]
        new[:len(cut)] = cut
        data["samples"] = len(new)
        del data["data"]
        data["data"] = new
        data["duration"] = data["samples"]/data["samplingrate"]
    
    if not KEEP_DOWNLOADS: delDownloads()
    return data
    

def loadRange(SET, METER, channel:int, tStart, tStop):
    if SET not in ["BLOND-50", "BLOND-250"]: return None
    startD = datetime.fromtimestamp(tStart).replace(hour=0, minute=0, second=0, microsecond=0)

    # days = math.ceil((tStart - startD.timestamp() + tStop-tStart)/(24*60*60))
    data = None
    while startD.timestamp() < tStop:
        nData = load(SET, METER, startD, channels=channel)
        if len(nData) < 1: raise AssertionError("Error loading blond data")
        nData = nData[0]
        if data is None: 
            data = nData
        else: 
            # Keep track of missing samples to next ts
            # Blond samplingrate seems to be higher than promised
            goalTsOfNew = data["timestamp"]+len(data["data"])/data["samplingrate"]
            isTsNew = nData["timestamp"]
            missingSamples = int((isTsNew-goalTsOfNew)*data["samplingrate"])
            if missingSamples > 0:
                if VERBOSE: print("need to add samples")
                new = np.recarray((missingSamples,), dtype=data["data"].dtype).view(np.recarray)
                new[:len(data["data"][-1])] = data["data"][-1] # fill with last value
                data["data"] = np.concatenate((data["data"], new))
            elif missingSamples < 0:
                if VERBOSE: print("need to remove samples")
                data["data"] = data["data"][:missingSamples]

            data["data"] = np.concatenate((data["data"], nData["data"]))

        startD += timedelta(days=1)

    if data is not None:
        # FIX duration and length
        sampleStart = int((tStart - data["timestamp"])*data["samplingrate"])
        if VERBOSE: print("This file start: {}".format(sampleStart))
        # BLOND summary file misses up tp 15 minutes from a day, 
        # the data is located in the summary of the previous day
        if sampleStart < 0:
            prevDay = datetime.fromtimestamp(tStart).replace(hour=0, minute=0, second=0, microsecond=0)-timedelta(days=1)
            sData = load(SET, METER, prevDay, channels=channel)
            if len(sData) < 1: raise AssertionError("Error loading blond data")
            sData = sData[0]
            # sampleStart = int((tStart-sData["timestamp"])*data["samplingrate"])
            if VERBOSE: print("We want earlier, using previous file, remaining samples: {}".format(len(sData["data"])-sampleStart))
            # take missing samples
            data["data"] = np.concatenate((sData["data"][sampleStart:], data["data"]))
        else:
            data["data"] = data["data"][sampleStart:]
        
        data["timestamp"] = tStart
        data["samples"] = int((tStop-data["timestamp"])*data["samplingrate"])
        data["data"] = data["data"][:data["samples"]]
        data["duration"] = data["samples"]/data["samplingrate"]
    
    # Handled directly in function load
    # if not KEEP_DOWNLOADS: delDownloads()
    return data

cacheFileList = {}
def fileList(url):
    if url in cacheFileList: return cacheFileList[url]
    command = ["curl", "-l", url]
    if VERBOSE: print(" ".join(command))
    process = subprocess.Popen(command, stdout=subprocess.PIPE , stderr=subprocess.PIPE, universal_newlines=True)
    files = [x.rstrip('\n') for x in process.stdout]
    # if VERBOSE: print(files)
    files = sorted([x for x in files if "clear" in x or "medal" in x])
    cacheFileList[url] = files
    return files


def load(SET, METER, day, channels=None):
    if SET not in ["BLOND-50", "BLOND-250"]: return None
    url = "ftp://m1375836:m1375836@dataserv.ub.tum.de//FD_Share_Kriechbaumer/BLOND/<SET>/<DAY>/<METER>/summary-<DAY>-<METER>.hdf5"
    url = url.replace("<SET>", str(SET))
    url = url.replace("<METER>", str(METER))
    dayStr = day.strftime(DATE_FORMAT)
    url = url.replace("<DAY>", dayStr)
    filePath = ftpGetFile(url, destinationPath=DOWNLOAD_PATH)
    data = loadHDF5(filePath, channels=channels)
    if not KEEP_DOWNLOADS: delDownloads()
    return data

def initParser():
    parser = argparse.ArgumentParser()
    parser.add_argument("--path", type=str, default="/Users/voelkerb/NILM_Datasets/BLOND",
                        help="Root path of the BLOND dataset.")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Increase output verbosity")
    return parser

# %%
if __name__ == "__main__":
    import matplotlib.pyplot as plt 
    from IPython import get_ipython
    import time
    parser = initParser()
    if get_ipython(): args = parser.parse_args([])
    else: args = parser.parse_args()


    BASE_PATH = args.path
    ts = 1479723398.0
    dataDictP = loadRange("BLOND-50", "medal-2", 1, ts-10, ts+10)
    
    start = time.time()
    dataDict = loadHighFreqRange("BLOND-50", "medal-2", 1, ts-3, ts+5)
    print("loading took {:.2f}ms".format(float(time.time()-start)*1000))
    data = dataDict["data"]
    # Lets align data perfectly
    index = -1
    # index = getRushInIndex(data, dataDict["samplingrate"])

    tss = np.arange(dataDict["timestamp"], dataDict["timestamp"]+dataDict["duration"], 1/dataDict["samplingrate"])
    dates = [datetime.fromtimestamp(ts) for ts in tss]
        
    plt.plot(dates[:dataDict["samples"]], dataDict["data"]["i"])
    ax = plt.gca()
    ax2 = ax.twinx()

    tss = np.arange(dataDictP["timestamp"], dataDictP["timestamp"]+dataDictP["duration"], 1/dataDictP["samplingrate"])
    dates = [datetime.fromtimestamp(ts) for ts in tss]
    x = np.arange(dataDictP["timestamp"],dataDictP["timestamp"]+dataDictP["duration"], 1/dataDictP["samplingrate"])
    ax2.plot(dates[:dataDictP["samples"]], dataDictP["data"]["p"], color='r')
    ax.axvline(x=datetime.fromtimestamp(ts), linewidth=2, color=(0,0,0))

    if index != -1:
        tsevent = dataDict["timestamp"]+index/dataDict["samplingrate"]
        ax.axvline(x=datetime.fromtimestamp(tsevent), linewidth=2, color=(1,0,0))
    plt.show(block=False)


    # url = "ftp://m1375836:m1375836@dataserv.ub.tum.de//FD_Share_Kriechbaumer/BLOND/BLOND-50/2016-09-30/medal-1/summary-2016-09-30-medal-1.hdf5"
    # ftpGetFile("/Users/voelkerb/Downloads/", url)
    # load("BLOND-50", 2, datetime.strptime("2016-09-30", DATE_FORMAT))
# %%

# %%
