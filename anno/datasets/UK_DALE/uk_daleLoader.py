import subprocess
import os
from datetime import datetime
import pytz
import sys
import h5py
import numpy as np
import argparse
import json 
import yaml

import tables

# Import top level module (two time up)
try:
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
except NameError:
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(sys.argv[0]))))
sys.path.append(root)

BASE_PATH = None
DATE_FORMAT = "%Y-%m-%d"
DATE_FORMAT_EXT = "%Y-%m-%d %H.%M.%s"
H5_FILE = "ukdale.h5"
METADATA_FOLDER = "metadata"

def __checkBasePath():
    if BASE_PATH is None: raise Exception("ECO Base path not set yet!")

def h5Path():
    __checkBasePath()
    return os.path.join(BASE_PATH, H5_FILE)

def __getMH(house, meter):
    h = house
    if isinstance(house, str): h = int(h.lstrip("building"))
    m = meter
    if isinstance(meter, str): m = int(m.lstrip("meter"))
    return h, m
    

def getHouses():
    path = h5Path()
    houses = []
    with h5py.File(path, "r") as hf:
        houses = list(hf.keys())
        hf.close()
    hs = [int(h.lstrip("building")) for h in houses]
    hs = sorted(hs)

    return ["building" + str(h) for h in hs]

def getMeters(house):
    path = h5Path()
    meters = []
    with h5py.File(path, "r") as hf:
        h = house
        if isinstance(house, int): h = "building" + str(h)
        if h in hf.keys():
            meters = list(hf[h]['elec'].keys())
        hf.close()
    ms = [int(m.lstrip("meter")) for m in meters]
    ms = sorted(ms)

    return ms

def getFullDay(ts):
    date = datetime.fromtimestamp(ts)
    date = date.replace(hour=0, minute=0, second=0, microsecond=0)
    return date.timestamp()

def daterange(startTS, endTS):
    end_date = datetime.fromtimestamp(endTS)
    start_date = datetime.fromtimestamp(startTS)
    for n in range(int((end_date - start_date).days)):
        yield (start_date + timedelta(n)).timestamp()

def getTimeZone():
    return pytz.timezone("UTC")

def getTimeRange(house, meter):
    h, m = __getMH(house, meter)

    path = h5Path()
    ranges = []
    with tables.open_file(path, 'r') as h5file:
        qstr = "/" + "building" + str(h) + "/elec/" + "meter" + str(m) + "/table/"
        data = h5file.get_node(qstr)
        times = data[:]
        h5file.close()
        times = times["index"]
        times = times*0.000000001
        diff = np.diff(times)
        indices = np.where(diff > 24*60*60)[0]
        lastStart = times[0]
        for i in range(len(indices)):
            ranges.append([lastStart, times[indices[i]]])
            lastStart = times[indices[i]+1]
        ranges.append([lastStart, times[-1]])

    return ranges


def getData(house, meter, startTs, stopTs):
    h, m = __getMH(house, meter)
    filePath = h5Path()
    with tables.open_file(filePath, 'r') as h5file:
        qstr = "/" + "building" + str(h) + "/elec/" + "meter" + str(m) + "/table/"
        data = h5file.get_node(qstr)
        qstr = "({} <= index) & (index < {})".format(int(startTs*1000000000), int(stopTs*1000000000))
        indices = data.get_where_list(qstr)
        npData = data[indices]
        npData["index"] = npData["index"]*0.000000001
        h5file.close()
        return npData
    return None

def load(house, meter, day):
    h, m = __getMH(house, meter)
    ts = day.timestamp()
    # Load data
    data = getData(h, m, ts, ts+24*60*60)
    # Load metadata
    meta = loadMetadata(h, m)
    title = getNameFromMeta(meta)
    info = getInfoFromMeta(meta)
    # Get measures
    mi = loadMeterInfo(h, m)
    measures = getMeasureForMeterMeta(mi)
    # Special case for house 1 whole house meter
    if mi["model"].replace(" ", "") == "SoundCardPowerMeter":
        title = "mains 1Hz"
        info = "Whole house aggregated consumption"
    # Determine approx samplingrate
    sr = 1/6
    if len(measures) > 1: sr = 1
    dataDict = {"title": title, "info": info, 
                "house": h, "meter": m, "samplingrate": sr, "ts": data["index"],
                "timestamp":data["index"][0], "measures":measures, "duration":data["index"][-1]-data["index"][0],
                "samples": len(data)}
    dataDict["data"] = np.recarray(len(data), dtype=np.dtype([(m,np.float32) for m in measures]))
    # Extract data as recarray
    if data["values_block_0"].shape[1] > 1:
        for i, m in enumerate(measures):
            dataDict["data"][m] = data["values_block_0"][:, i]
    else:
        # TODO: Does only work for one measure
        dataDict["data"][measures[0]] = data["values_block_0"][:].ravel()
    return dataDict

measuresOfMeters = {
    "CurrentCostTx": ["s"],
    "EcoManagerWholeHouseTx": ["s"],
    "EcoManagerTxPlug": ["p"],
    "SoundCardPowerMeter": ["p", "s", "v_rms"]
}

def getMeasureForMeterMeta(meta):
    global measuresOfMeters
    return measuresOfMeters[meta["model"].replace(" ", "")]

def getInfoFromMeta(meta):
    return ", ".join([m["description"] for m in meta if "description" in m])

def getShortNameFromMeta(meta):
    names = []
    for a in meta:
        n = ""
        if "type" in a:
            n = a["type"]
        elif "original_name" in a:
            n = a["original_name"]
        if n not in names: names.append(n)
    # Treat empty names as main
    if len(names) == 0: names.append("mains")
    return ", ".join(names)

def getNameFromMeta(meta):
    names = []
    for a in meta:
        n = ""
        if "room" in a:
            n = a["room"] + ": "
        if "original_name" in a:
            n += a["original_name"]
        elif "type" in a:
            n += a["type"]
        if "manufacturer" in a: n += ": " + a["manufacturer"]
        if "model" in a: n += " - " + a["model"]
        if n not in names: names.append(n)
    # Treat empty names as main
    if len(names) == 0: names.append("mains")
    return ", ".join(names)

def getLabels(house):
    labels = {0: "mains"}
    meters = getMeters(house)
    for m in meters:
        meta = loadMetadata(house, m)
        labels[m] = getShortNameFromMeta(meta)
    return labels

metadata = {}
meterInfo = {}

def loadMeterInfo(house, meter):
    global metadata, meterInfo
    __checkBasePath()
    h, m = __getMH(house, meter)
    fp =  os.path.join(BASE_PATH, METADATA_FOLDER, "building" + str(h) + ".yaml")
    # Look if previously loaded
    if h not in metadata:
        fp =  os.path.join(BASE_PATH, METADATA_FOLDER, "building" + str(h) + ".yaml")
        with open(fp, 'r') as stream:
            try:
                meta = yaml.safe_load(stream)
                metadata[h] = meta
            except yaml.YAMLError as exc: print(exc)
    
    meta = metadata[h]["elec_meters"]
    meter = next(meta[me] for me in meta if me == m)
    if meter["device_model"] not in meterInfo:

        fp2 =  os.path.join(BASE_PATH, METADATA_FOLDER, "meter_devices.yaml")
        with open(fp2, 'r') as stream:
            try:
                meterInfo = yaml.safe_load(stream)
            except yaml.YAMLError as exc: print(exc)
    return meterInfo[meter["device_model"]]


def loadMetadata(house, meter):
    global metadata
    __checkBasePath()
    h, m = __getMH(house, meter)
    if m == 1: return [{"original_name": "mains"}]
    # Look if previously loaded
    if h not in metadata:
        fp =  os.path.join(BASE_PATH, METADATA_FOLDER, "building" + str(h) + ".yaml")
        with open(fp, 'r') as stream:
            try:
                meta = yaml.safe_load(stream)
                metadata[h] = meta
            except yaml.YAMLError as exc:
                print(exc)

    meta = metadata[h]["appliances"]
    appInfo = [me for me in meta if m in me["meters"]]
    return appInfo

def loadMapping():
    __checkBasePath()
    path = os.path.join(BASE_PATH, "mapping.json")
    data = None
    with open(path) as outfile:
        data = json.load(outfile)
    return data

def __storeMapping(mapping):
    __checkBasePath()
    path = os.path.join(BASE_PATH, "mapping.json")
    with open(path, 'w') as outfile:
        json.dump(mapping, outfile)

availability = None
def loadAvailability():
    __checkBasePath()
    global availability
    if availability is not None: return availability
    path = os.path.join(BASE_PATH, "availability.json")
    availability = None
    with open(path) as outfile:
        availability = json.load(outfile)
    newAvailability = {}
    # Convert to integers
    for h in availability:
        newAvailability[int(h.lstrip("building"))] = {int(m):availability[h][m] for m in availability[h]}
    availability = newAvailability
    return availability

def __storeAvailability(avail):
    __checkBasePath()
    path = os.path.join(BASE_PATH, "availability.json")
    with open(path, 'w') as outfile:
        json.dump(avail, outfile)

def initParser():
    parser = argparse.ArgumentParser()
    parser.add_argument("--path", type=str, default="/Users/voelkerb/NILM_Datasets/UKDALE",
                        help="Root path of the BLOND dataset.")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Increase output verbosity")
    return parser

if __name__ == "__main__":
    parser = initParser()
    args = parser.parse_args()

    BASE_PATH = args.path

    houses = getHouses()
    # getMeters(1)

    # data = load(houses[0], 1, datetime.strptime("2016-06-02", DATE_FORMAT))
    # print("_"*50)
    # data = load(houses[0], 54, datetime.strptime("2016-06-02", DATE_FORMAT))

    # data = load(houses[0], getMeters(houses[0])[1], datetime.strptime("2016-06-02", DATE_FORMAT))
    # print(data)
    # availability = {h:{} for h in houses}
    # for h in houses:
    #     meters = getMeters(h)
    #     print(str(h) + ": " + str(meters))
    #     for meter in meters:
    #         timeranges = getTimeRange(h, meter)
    #         print("\t" + str(meter) + " - tr: " + str(timeranges))
    #         availability[h][meter] = timeranges
    
    # print(json.dumps(availability))
    
    # __storeAvailability(availability)

    # avail = loadAvailability()

    # print(avail)

    # print(getLabels("building3"))
    # mapping = loadMapping()
    # print(mapping["building3"])


    houses = getHouses()
    ukdaleInfo = {h:getLabels(h) for h in houses}
    print(ukdaleInfo)


    __storeMapping(ukdaleInfo)
    mapping = loadMapping()
    
    # print(mapping)