# Main file.
# !/usr/bin/python3

import os
import sys
import struct
import datetime
import pytz
import json

from os import listdir  # noqa
from os.path import isfile, isdir, join  # noqa
from datetime import datetime
import numpy as np
import pytz


DEBUG = False
SUFFIX_LOW = ".dat"
SUFFIX_HIGH = ""
SAMPLING_RATE = 16000
MEASUREMENTS = ["v", "i"]
BASE_PATH = None


def __checkBasePath():
    if BASE_PATH is None: raise AssertionError("Redd base path not set")

def getAvailableHouses():
    __checkBasePath()
    lowFreqPath = os.path.join(BASE_PATH, "low_freq")
    houses = [int(n.lstrip("house_")) for n in os.listdir(lowFreqPath) if os.path.isdir(os.path.join(lowFreqPath, n))]
    houses = sorted(houses)
    return houses

def getAvailableChannels(house):
    __checkBasePath()
    lowFreqPath = os.path.join(BASE_PATH, "low_freq", "house_" + str(house))
    channels = [int(n.lstrip("channel_").rstrip(".dat")) for n in os.listdir(lowFreqPath) if "channel_" in n]
    return sorted(channels)
    
def getTimeRange(house, channel):
    __checkBasePath()
    path = os.path.join(BASE_PATH, "low_freq", "house_" + str(house), "channel_" + str(channel) + ".dat")
    ranges = []

    data = np.genfromtxt(path, delimiter=' ')
    times = data[:,0]
    diff = np.diff(times)
    indices = np.where(diff > 24*60*60)[0]
    lastStart = times[0]
    for i in range(len(indices)):
        ranges.append([lastStart, times[indices[i]]])
        lastStart = times[indices[i]+1]
    ranges.append([lastStart, times[-1]])

    return ranges

def getAvailableDuration(house):
    __checkBasePath()
    channel1Path = os.path.join(BASE_PATH, "low_freq", "house_" + str(house), "channel_1.dat")
    firstTs, lastTs = None, None
    with open(channel1Path, "rb") as f:
        firstLine = f.readline().decode("utf-8")
        f.seek(-2, 2)              # Jump to the second last byte.
        while f.read(1) != b"\n":  # Until EOL is found ...
            f.seek(-2, 1)          # ... jump back, over the read byte plus one more.
        lastLine = f.readline().decode("utf-8")
        firstTs = float(firstLine.split(" ")[0])
        lastTs = float(lastLine.split(" ")[0])
    return firstTs, lastTs

def __fileToList(path):
    """
    Return data as list from file at given location.

    :param path: Path to data
    :type  path: str
    :return: Data from file and timestamp
    :rtype:  list, float
    """
    data = []
    ts = None
    first = None
    last = None
    tsi = struct.unpack("f", b'\x74\x69\x6d\x65')[0]
    with open(path, "rb") as f:
        fileContent = f.read()
        size = (len(fileContent)/4)
        size = int(size)
        ptr = 0
        while size > 0:
            cut = 1000
            if size < cut:
                cut = size
            data.extend(list(struct.unpack(str(cut)+"f", fileContent[ptr:ptr+cut*4])))
            ptr = ptr+cut*4
            size -= cut
    indices = [i for i, v in enumerate(data) if v == tsi]
    fb = struct.unpack("i", bytearray(struct.pack("f", data[indices[0]+1])))[0]
    sb = struct.unpack("i", bytearray(struct.pack("f", data[indices[0]+2])))[0]
    first = float(fb) + float(sb)/1e9
    fb = struct.unpack("i", bytearray(struct.pack("f", data[indices[-1]+1])))[0]
    sb = struct.unpack("i", bytearray(struct.pack("f", data[indices[-1]+2])))[0]
    last = float(fb) + float(sb)/1e9
    # _indices = []
    # for i in indices:
    #     _indices.extend([i, i+1, i+2])
    # data = [v for i, v in enumerate(data) if i not in _indices]
    for i in reversed(indices):
        del data[i+2]
        del data[i+1]
        del data[i]

    fs = len(data)/(last - first)
    ts = first
    return data, ts


def getCircuitMapping(house):
    mapping = {
        1: {
            #                              ?            ?
            1: [1, 3, 5, 7, 9, 11, 12, 13, 14, 15, 18, 19],
            #                            ?
            2: [2, 4, 6, 8, 10, 16, 17, 20],
        }
    }
    return mapping[house]

def loadLabels(house):
    return loadLowFreqLabels(os.path.join(BASE_PATH, "low_freq", "house_" + str(house), "labels.dat"))

def loadLowFreqLabels(labelFilePath):
    """
    Return dictionary of channel labels.

    :param labelFilePath:    path to the data. The path should end with the folder containing all data for a specific house.
    :type  labelFilePath:    str

    :rparam: keys=channels_x - appliance name
    :rtype:  dict
    """
    labels = None
    with open(labelFilePath) as f:
        content = f.readlines()
        labels = {"channel_" + d.split(" ")[0]: d.split(" ")[1].rstrip("\n") for d in content}
    return labels


def loadLowFreqPath(path, utcStartTs=None, utcStopTs=None, verbose=False):
    """
    Load data for given file.

    :param path:    path to the data. The path should end with the folder containing all data for a specific house.
    :type  path:    str
    :param verbose: enabe debug output
    :type  verbose: bool
    """
    tdata = np.genfromtxt(path, delimiter=' ')
    # convert into timeuone US/Eastern
    # tdata[:,0] -= 4*60*60
    indexStart = 0
    if utcStartTs is not None:
        indexStart2 = np.nonzero(tdata >= utcStartTs)
        if len(indexStart2[0]) > 0: indexStart = indexStart2[0][0]
    indexEnd = len(tdata) - 1
    if utcStopTs is not None:
        indexEnd2 = np.nonzero(tdata >= utcStopTs)
        if len(indexEnd2[0]) > 0: indexEnd = indexEnd2[0][0]
    if verbose:
        print(datetime.utcfromtimestamp(utcStartTs).strftime('%Y-%m-%d %H:%M:%S'), end="")
        print(" - ", end="")
        print(datetime.utcfromtimestamp(utcStopTs).strftime('%Y-%m-%d %H:%M:%S'), end="")
        print(datetime.utcfromtimestamp(int(tdata[indexStart][0])).strftime('%Y-%m-%d %H:%M:%S'), end="")
        print(" - ", end="")
        print(datetime.utcfromtimestamp(int(tdata[indexEnd-1][0])).strftime('%Y-%m-%d %H:%M:%S'))
        print("duration: ", end="")
        print(tdata[-1][0] - tdata[0][0])
        print("datapoints: ", end="")
        print(len(tdata[indexStart:indexEnd]))
        print("samplingrate: ", end="")
        print((tdata[-1][0] - tdata[0][0])/len(tdata))
    return tdata[indexStart:indexEnd]


def loadLowFreqDay(house, dateTimeDay, channels=None):
    startTs = datetime.timestamp(dateTimeDay.astimezone(pytz.utc))
    return loadLowFreq(house, channels=channels,
                            utcStartTs=startTs,
                            utcStopTs=startTs+60*60*24)


def loadLowFreqInterval(house, startDt, stopDt, channels=None):
    return loadLowFreq(house, channels=channels,
                            utcStartTs=datetime.timestamp(startDt.astimezone(pytz.utc)),
                            utcStopTs=datetime.timestamp(stopDt.astimezone(pytz.utc)))

def loadLowFreq(house, channels=None, utcStartTs=None, utcStopTs=None):
    """
    Load data of the given house.

    :param dirpath:  path to the data. The path should end with the folder containing all data for a specific house.
    :type  dirpath:  str
    :param channels: list of channels to load
    :type  channels: list of int
    """
    __checkBasePath()
    dirname = os.path.join(BASE_PATH, "low_freq", "house_" + str(house))
    filesToLoad = [os.path.join(dirname, f) for f in os.listdir(dirname) if os.path.isfile(os.path.join(dirname, f))]
    labelsFile = next(os.path.join(dirname, f) for f in os.listdir(dirname) if "labels.dat" in f)
    filesToLoad.remove(labelsFile)
    labels = loadLowFreqLabels(labelsFile)

    if channels is not None:
        channelsToLoad = ["channel_" + str(channel) + ".dat" for channel in channels]
        filesToLoad = [os.path.join(dirname, channel) for channel in channelsToLoad]
    filesToLoad.sort(key=lambda f: int(''.join(filter(str.isdigit, f))))
    dataList = []
    for path in filesToLoad:
        channel = os.path.basename(path).split(".")[0]
        loaded = loadLowFreqPath(path, utcStartTs=utcStartTs, utcStopTs=utcStopTs)
        wtype = np.dtype([('s',np.float32)])
        data = np.empty(len(loaded), dtype=wtype)

        

        # dataDict["data"]["ts"] = newX
        data["s"] = np.array(loaded[:,1])
        dataDict = {"channel": int(channel.split("_")[1]), "title": labels[channel], "samplingrate": 1/3,
                    "data": data, "ts":loaded[:,0], "measures":["s"], "duration":loaded[-1,0]-loaded[0,0],
                    "samples": len(data), "timestamp":loaded[0,0]}

        dataList.append(dataDict)
    return dataList

def getTimeZone():
    return pytz.timezone("US/Eastern")

def loadHighFreqRaw(house):
    """
    Load data of the given house.

    :param house: House number
    :type  house: int
    """
    if house not in [3, 5]:
        print("Error: " + str(house) + " does not exist in high freq data")
        return None
    path = join(datapath, "high_freq_raw", str("house_" + str(house)))
    c_1_path = join(path, "current_1")
    files = os.listdir(c_1_path)
    c_2_path = join(path, "current_2")
    voltage_path = join(path, "voltage")
    mds = []
    for file in files:
        fpath = join()

availability = None
def loadAvailability():
    __checkBasePath()
    global availability
    if availability is not None: return availability
    path = os.path.join(BASE_PATH, "availability.json")
    availability = None
    with open(path) as outfile:
        availability = json.load(outfile)
    return availability

def __storeAvailability(avail):
    __checkBasePath()
    path = os.path.join(BASE_PATH, "availability.json")
    with open(path, 'w') as outfile:
        json.dump(avail, outfile)


def initParser():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--path", type=str, default="/Users/voelkerb/NILM_Datasets/REDD",
                        help="Root path of the BLOND dataset.")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Increase output verbosity")
    return parser

if __name__ == "__main__":
    parser = initParser()
    args = parser.parse_args()

    BASE_PATH = args.path


    houses = getAvailableHouses()

    availability = {h:{} for h in houses}
    for h in houses:
        channels = getAvailableChannels(h)
        print(str(h) + ": " + str(channels))
        for c in channels:
            timeranges = getTimeRange(h, c)
            print("\t" + str(c) + " - tr: " + str(timeranges))
            availability[h][c] = timeranges
    
    print(json.dumps(availability))
    
    __storeAvailability(availability)

    avail = loadAvailability()

    print(avail)