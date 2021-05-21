"""
Useful funtions used by multiple scripts throughout all modules are listed here.

Import them as:

.. code-block:: python3

    from measurement.usefulFunctions import axLabel, time_format_ymdhms

"""
import sys
import os
import numpy as np
import datetime



def axLabel(value, unit):
    """
    Return axis label for given strings.

    :param value: Value for axis label
    :type  value: int
    :param unit: Unit for axis label
    :type  unit: str

    :return: Axis label as \"<value> (<unit>)\"
    :rtype: str
    """
    return str(value) + " (" + str(unit) + ")"


def filenameToTimestamp(filename, format="%Y_%m_%d__%H_%M_%S"):
    timestr = os.path.basename(filename).split(".")[0]
    timestr = "_".join(timestr.split("_")[1:])
    d = decodeDateStr(timestr, format)
    if d is not None:
        return d.timestamp()
    return None
    
def time_format_store_ymdhms(dt, addMilliseconds=True):
    """
    Return time format as y_m_d__h_m_s[_ms].

    :param dt: The timestamp or date to convert to string
    :type  dt: datetime object or timestamp
    :param addMilliseconds: If milliseconds should be added
    :type  addMilliseconds: bool

    :return: Timeformat as \"y_m_d__h_m_s[_ms]\"
    :rtype: str
    """
    if dt is None:
        return "UUPs its (None)"
    import datetime
    if (isinstance(dt, datetime.datetime) is False
            and isinstance(dt, datetime.timedelta) is False):
        dt = datetime.datetime.fromtimestamp(dt)
    if addMilliseconds:
        return "%s:%s" % (
            dt.strftime('%Y_%m_%d__%H_%M_%S'),
            str("%03i" % (int(dt.microsecond/1000)))
        )
    else:
        return "%s" % (
            dt.strftime('%Y_%m_%d__%H_%M_%S')
        )


def time_format_ymdhms(dt):
    """
    Return time format as y.m.d h:m:s.

    :param dt: The timestamp or date to convert to string
    :type  dt: datetime object or timestamp

    :return: Timeformat as \"y.m.d h:m:s\"
    :rtype: str
    """
    if dt is None:
        return "UUPs its (None)"
    import datetime
    if (isinstance(dt, datetime.datetime) is False
            and isinstance(dt, datetime.timedelta) is False):
        dt = datetime.datetime.fromtimestamp(dt)
    return "%s.%s" % (
        dt.strftime('%Y.%m.%d %H:%M:%S'),
        str("%03i" % (int(dt.microsecond/1000)))
    )

def time_format_hms(dt):
    """
    Return time format as h:m:s.ms.

    :param dt: The timestamp or date to convert to string
    :type  dt: datetime object or timestamp

    :return: Timeformat as \"h:m:s.ms\"
    :rtype: str
    """
    if dt is None:
        return "UUPs its (None)"
    import datetime
    if (isinstance(dt, datetime.datetime) is False
            and isinstance(dt, datetime.timedelta) is False):
        dt = datetime.datetime.fromtimestamp(dt)
    if isinstance(dt, datetime.timedelta):
        d = divmod(dt.total_seconds(), 86400)  # days
        h = divmod(d[1], 3600)  # hours
        m = divmod(h[1], 60)  # minutes
        s = m[1]  # seconds(d[0],h[0],m[0],s)
        return ("" + str(int(d[0])) + ":" + str(int(h[0])) + ":"
                + str(int(m[0])) + ":" + str(round(s, 3)))
    else:
        return "%s:%.3f" % (
            dt.strftime('%H:%M'),
            float("%.3f" % (dt.second + dt.microsecond / 1e6))
        )

def toShortForm(feat):
    """
    Converts feature names into short form.

    :param feat: Feature names
    :type  feat: str

    :return: short form of given feature name
    :rtype: str
    """
    if feat == vu.RAW_DATA:
        return "RD"
    elif feat == vu.AVG_VOLTAGE:
        return "AVG_V"
    elif feat == vu.AVG_CURRENT:
        return "AVG_C"
    elif feat == vu.MAX_CURRENT:
        return "MAX_C"
    elif feat == vu.RMS_CURRENT:
        return "RMS_C"
    elif feat == vu.AVG_ACTIVE_POWER:
        return "AVG_AP"
    elif feat == vu.MAX_ACTIVE_POWER:
        return "MAX_AP"
    elif feat == vu.ACTIVE_POWER_BEFORE_DOWN:
        return "AP_BD"
    elif feat == vu.AVG_REACTIVE_POWER:
        return "AVG_RP"
    elif feat == vu.MAX_REACTIVE_POWER:
        return "MAX_RP"
    elif feat == vu.REACTIVE_POWER_BEFORE_DOWN:
        return "RP_BD"
    elif feat == vu.WAVEFORM_ANALYSIS:
        return "WA"
    elif feat == vu.TRISTIMULUS:
        return "Tri"
    elif feat == vu.FORM_FACTOR:
        return "FF"
    elif feat == vu.CREST_FACTOR:
        return "CF"
    elif feat == vu.RESISTANCE:
        return "R"
    elif feat == vu.TEMPORAL_CENTROID:
        return "TC"
    elif feat == vu.SPECTRAL_CENTROID:
        return "SC"
    elif feat == vu.PHASE_ANGLE:
        return "PHI"
    else:
        return feat

def decodeDateStr(s, format):
        import datetime
        # Format <Year>_<Month>_<Day>.mkv
        try: d = datetime.datetime.strptime(s, format)
        except ValueError: d = None
        return d

def decodeDateString(s):
    """
    Try to decode datestring into a datetime object.

    :param s: The time as string
    :type  s: str

    :return: Datetime object of passed string, None if it cannot be decoded
    :rtype: datetime or None
    """
    # other formats are not supported
    formats = ["%Y_%m_%d", "%Y_%m_%d__%H_%M_%S", "%Y_%m_%d__%H_%M_%S.%f"]
    for format in formats:
        date = decodeDateStr(s, format)
        if date is not None: return date
        parts = s.split("__")
        for i in range(1,len(parts)):
            s_ = "__".join([parts[j] for j in range(-i, 0)])
            date = decodeDateStr(s_, format)
            if date is not None: return date
    return None



def fields_view(array, fields):
    """
    Return array which only contains fields passed

    :param array: Data as recarray with fieldnames
    :type  array: numpy.recarray 
    :param fields: Names of column in numpy.recarray
    :type  fields: list of str
    :return: Recarray with new fields
    :rtype: numpy.recarray
    """
    return array.getfield(np.dtype(
        {name: array.dtype.fields[name] for name in fields}
    ))

def toRecarray(data, fieldnames):
    """
    Return recarray with new fields appended, will override if exists.

    :param data: Data
    :type  data: list of lists
    :param fieldnames: Names of new column in numpy.recarray
    :type  fieldnames: list of str
    :return: Recarray with new field appended
    :rtype: numpy.recarray
    """
    recdata = np.core.records.fromarrays(data, dtype={'names': fieldnames, 'formats': ['f4']*len(fieldnames)})
    return recdata

def appendFieldsToRecarray(recarray, data, fieldnames):
    """
    Return recarray with new fields appended, will override if exists.

    :param recarray: Recarray to append to
    :type  recarray: list
    :param data: Data
    :type  data: list or np.array
    :param fieldnames: Names of new column in numpy.recarray
    :type  fieldnames: list of str
    :return: Recarray with new field appended
    :rtype: numpy.recarray
    """
    from numpy.lib.recfunctions import append_fields, drop_fields
    if isinstance(data, list):
        if recarray.size != len(data[0]):
            print("Warning: Cannot append array of size " + str(len(data)) +
                         " to recarray of size " + str(recarray.size))
            return recarray
    else:
        if recarray.size != data.size:
            print("Warning: Cannot append array of size " + str(data.size) +
                         " to recarray of size " + str(recarray.size))
            return recarray
    rec = drop_fields(recarray, fieldnames)
    dtypes = ['f4']*len(fieldnames)
    rec = append_fields(rec, np.array(fieldnames), data, dtypes=dtypes, asrecarray=True,
                        usemask=False)
    return rec

def appendFieldToRecarray(recarray, data, fieldname):
    """
    Return recarray with new field appended, will override if exists.

    :param recarray: Recarray to append to
    :type  recarray: list
    :param data: Data
    :type  data: list
    :param fieldname: Name of new column in numpy.recarray
    :type  fieldname: str
    :return: Recarray with new field appended
    :rtype: numpy.recarray
    """
    from numpy.lib.recfunctions import append_fields, drop_fields
    if recarray.size != data.size:
        printWarning("Cannot append array of size " + str(data.size) +
                     " to recarray of size " + str(recarray.size))
        return recarray
    rec = drop_fields(recarray, fieldname)
    rec = append_fields(rec, fieldname, data, dtypes='f4', asrecarray=True,
                        usemask=False)
    return rec


def setProcessPriorityWindows(pid=None, priority=1):
    """ Set The Priority of a Windows Process.  Priority is a value between 0-5 where
        2 is normal priority.  Default sets the priority of the current
        python process but can take any valid process ID. """

    import win32api,win32process,win32con

    priorityclasses = [win32process.IDLE_PRIORITY_CLASS,
                       win32process.BELOW_NORMAL_PRIORITY_CLASS,
                       win32process.NORMAL_PRIORITY_CLASS,
                       win32process.ABOVE_NORMAL_PRIORITY_CLASS,
                       win32process.HIGH_PRIORITY_CLASS,
                       win32process.REALTIME_PRIORITY_CLASS]
    if pid == None:
        pid = win32api.GetCurrentProcessId()
    handle = win32api.OpenProcess(win32con.PROCESS_ALL_ACCESS, True, pid)
    win32process.SetPriorityClass(handle, priorityclasses[priority])

def setProcessPriority(pid=None, priority=20):
    """ Set The Priority of a Unix or Windows Process.  Priority is a value between -20-20 where
        20 is normal priority.  Default sets the priority of the current
        python process but can take any valid process ID. """
    import sys, psutil
    try:
        sys.getwindowsversion()
    except AttributeError:
        isWindows = False
    else:
        isWindows = True

    if isWindows:
        # Map priority from 20 - -20 to 0 - 5
        winPrio = int(float(1.0 - float(priority + 20.0 / 40.0) * 5.0))
        setProcessPriorityWindows(priority=winPrio%5)
    else:
        import os
        if pid is None:
            p = psutil.Process(os.getpid())
        else:
            p = psutil.Process(pid)
        if p is not None:
            p.nice(priority)

def getAllFilesInDirectory(paths, recursive=False, maxLevel=10, extensions=[]):
    """
    Return all files in the given directory.

    :param directory: Directory in which we look for files
    :type  directory: str
    :param recursive: If subdirectories should be included
    :type  recursive: bool, default: ``False``
    :param maxLevel: Maximum recursive level
    :type  maxLevel: int, default: ``10``
    :param extensions: List of file file extensions to include, default: all files
    :type  extensions: list, default: ``[]``
    :return: Set of file paths
    :rtype: set(str)
    """
    if isinstance(extensions, str): extensions = [extensions]
    import glob
    full_paths = [(os.path.join(os.getcwd(), path), 0) for path in paths]

    files = set()

    for path, level in full_paths:
        if os.path.isfile(path):
            filename, fileExt = os.path.splitext(path)
            if len(extensions) == 0 or fileExt in extensions:
                files.add(path)
        else:
            if recursive and level < maxLevel:
                newPaths = glob.glob(path + "/*")
                full_paths += [(newPath, level+1) for newPath in newPaths]

    return sorted(list(files))

def resampleRecord(data, inRate, outRate):
    if inRate == outRate: return data
    resampleFac = inRate/outRate
    # NOTE: This is done for each measure
    # TODO: Maybe we can make this quicker somehow
    oldX = np.arange(0, len(data))
    newX = np.arange(0, len(data), resampleFac)
    data2 = np.zeros(len(newX), dtype=data.dtype)
    for measure in data.dtype.names:
        data2[measure] = np.interp(newX, oldX, data[measure])
    data = data2
    return data