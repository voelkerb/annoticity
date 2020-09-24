from . import data as dataHp
import numpy as np
from datetime import datetime
import pytz

def get(title, measures):
    chart = {
        # 'colors': ["rgba(235, 162, 59, 1)", "#c1a374"],
        'chart': {'type': 'area', 'zoomType': 'xy', 'resetZoomEnabled':False, 'animation': False, 'spacingTop': 5},
        'boost': { 'useGPUTranslations': True, 'enabled' : False },
        'navigator' : {
            'adaptToUpdatedData': False,
            'dateTimeLabelFormats': {
                'day': '%b %e, %Y'
            },
        },
        'legend': {
            'enabled': True
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
        'exporting': { 'enabled': True },
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
            'title': {'text':getAxisTitles(measures)}
        },
        'tooltip': { 
            'split': True,
            'valueDecimals': 2,
            'dateTimeLabelFormats': {
              'millisecond': '%H:%M:%S.%L',
              'second': '%H:%M:%S',
              'minute': '%H:%M',
              'hour': '%H:%M',
            },
        },
        'series': []
    }
    for m in measures:
        measureText, unit = getMeasureUnit(m)
        series = {
            'name': measureText,
            'color': '#0066FF',
            'dataGrouping': { 'enabled': False },
            'showInNavigator': True,
            'tooltip': { 'valueSuffix': " " + unit }, 
        }
        color = getColor(m)
        if color is not None: series['color'] = color
        chart['series'].append(series)
    return chart


measureTexts = {"p":{"name":"Active Power", "axis":"Power", "unit":"W", "color":"#CD1C09"}, 
                "q":{"name":"Reactive Power", "axis":"Power", "unit":"var", "color": "#0079C0"}, 
                "s":{"name":"Apparent Power", "axis":"Power", "unit":"VA", "color": "#E59D01"},
                "v":{"name":"Voltage", "axis":"Voltage", "unit":"V", "color": "#00CC2B"},
                "i":{"name":"Current", "axis":"Current","unit":"A", "color": "#00A1FF"},
                "v_rms":{"name":"RMS Voltage", "axis":"Voltage", "unit":"V", "color": "#00CC2B"},
                "i_rms":{"name":"RMS Current", "axis":"Current", "unit":"A", "color": "#00A1FF"},
                }

def getColor(measure):
    if measure.split("_l")[0] in measureTexts:
        return measureTexts[measure.split("_l")[0]]["color"]
    return None


def responseForInitChart(dataDict, measures=None):
    ms = []
    if measures is not None:
        for m in measures:
            if m in dataDict["measures"]: ms.append(m)
    
    if len(ms) == 0:
        preferredKeys = ["s", "s_l1", "p", "p_l1"]
        usableKeys = list(set(preferredKeys) & set(dataDict["measures"]))
        m = dataDict["measures"][0]
        if len(usableKeys) > 0: m = usableKeys[0]
        ms.append(m)

    duration = dataDict["duration"]

    startTs = dataDict["timestamp"]
    stopTs = startTs + dataDict["duration"]
    title = "unknown"
    device = "unknown"
    if "title" in dataDict: 
        device = dataDict["title"].replace("_", " ")
        title = dataDict["title"].replace("_", " ")
        if (dataDict["timestamp"] != 0): title += " day: " + datetime.fromtimestamp(dataDict["timestamp"]).strftime("%m/%d/%Y")
    
    c = get(title, ms)
    if "info" in dataDict and dataDict["info"] is not None:
        c['subtitle'] = {'text': str(dataDict["info"])}
    c['yAxis']['startOnTick'] = False


    for i, m in enumerate(ms):
        samplingrate = min(dataDict["samplingrate"], dataHp.srBasedOnDur(duration, m))
        data = dataHp.resample(dataDict["data"][m], dataDict["samplingrate"], samplingrate) 
        timestamps = np.linspace(startTs*1000, stopTs*1000, len(data))
        data = [[t, float(d)] for d,t in zip(data, timestamps)]
        c['series'][i]['data'] = data
        c['series'][i]['id'] = m
        c['series'][i]['pointStart'] = startTs*1000
        c['series'][i]['pointInterval'] = (1/samplingrate)*1000
        
    subs = []
    if 'subs' in dataDict:
        for sub in dataDict["subs"]:
            subs.append({"startTs":sub.start/1000.0, "stopTs":sub.end/1000.0, "text":sub.text})
    response = {'chart':c, 'labels':subs, 'device': device,'startTs':startTs}
    # Set timezone
    if 'tz' in dataDict: 
        response['timeZone'] = dataDict["tz"]
        ts = dataDict["timestamp"]
        if "utc_timestamp" in dataDict: ts = dataDict["utc_timestamp"]
        date = datetime.fromtimestamp(ts, pytz.UTC).astimezone(pytz.timezone(dataDict["tz"]))
        response['timeZoneOffset'] = date.utcoffset().total_seconds()/60

    # Set day
    if (dataDict["timestamp"] == 0): response['day'] = None
    else: response['day'] = datetime.strftime(datetime.fromtimestamp(dataDict["timestamp"]), "%m_%d_%Y")

    return response 

def responseForData(dataDict, measures, startTs, stopTs):
    chartData = {"series":[]}

    duration = stopTs - startTs
    for m in measures:
        samplingrate = min(dataDict["samplingrate"], dataHp.srBasedOnDur(duration, m))
        data = dataHp.resample(dataDict["data"][m], dataDict["samplingrate"], samplingrate) 
        timestamps = np.linspace(startTs*1000, stopTs*1000, len(data))
        data = [[t, float(d)] for d,t in zip(data, timestamps)]
        c = {"data": data, "id": m, "pointStart":startTs*1000, "pointInterval":(1/samplingrate)*1000}

        measureText, unit = getMeasureUnit(m)
        chartData["series"].append({"data":data, "id":m, "startTs": startTs, "interval": 1/samplingrate})
    return chartData

def getAxisTitles(measures):
    texts = []
    for measure in measures:
        if measure.split("_l")[0] in measureTexts:
            if measureTexts[measure.split("_l")[0]]["axis"] not in texts:
                texts.append(measureTexts[measure.split("_l")[0]]["axis"])
    if len(texts) > 0: return ", ".join(texts)
    else: return "Unknown"

def getMeasureUnit(measure):
    measureText = "Unknown"
    unit = ""
    if measure.split("_l")[0] in measureTexts:
        measureText = measureTexts[measure.split("_l")[0]]["name"]
        if len(measure.split("_l")) > 1: measureText += " L" + measure.split("_l")[-1]
        unit = measureTexts[measure.split("_l")[0]]["unit"]
    return measureText, unit
