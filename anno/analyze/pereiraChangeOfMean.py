"""Main file."""
# !/usr/bin/python3

import numpy as np
import time

def getChangePoints(power, likelihoods, windowSize=50, minDist=50):
    changeIndices = []
    win = int(windowSize/2)
    absolutLikelihood = np.abs(likelihoods)
    newPower = np.array(power)

    nonZero = np.where(absolutLikelihood > 0)[0]
    checkIndex = 0

    newGroups = []
    if len(nonZero) > 0:
        groupednonZero = np.split(nonZero, np.where(np.diff(nonZero) != 1)[0]+1)
        newGroups = groupednonZero

        for group in newGroups:
            if len(group) > 2:
                if checkIndex > group[0]: 
                    continue
                myGroup = group
                i = np.argmax(absolutLikelihood[myGroup])+group[0]
                checkIndex = i + minDist
                changeIndices.append(i)

    return changeIndices

def getChangePoints2(likelihoods, windowSize=50, minDist=50):
    """
    Returns the changepoints in the likelihoods data.

    Apply a voting window of windowSize to the likelihoods data.
    Loop over all points. If this point is the larges point in the window
    of <windowSize> samples, a change is assumed. The next change has to be
    <minDist> samples away

    :param likelihoods: the likelihoods list or np array
    :type  likelihoods: list
    :param windowSize: the size of the window, default: 50
    :type  windowSize: int
    :param minDist: the minimum distance between changepoints in samples, default: 50
    :type  minDist: int
    :return: chanepoint indices
    :rtype: list
    """
    changeIndices = []
    win = int(windowSize/2)
    absolutLikelihood = [abs(number) for number in likelihoods]
    w = -1
    # Enumeration seems faster as for loop, this is why its implemented this crappy
    for j, l in enumerate(absolutLikelihood):
        if w >= 0:
            w -= 1
            continue
        if l == 0: continue
        i = max(0, j-win)
        k = min(len(likelihoods), j+win)
        subList = absolutLikelihood[i:k]
        # print(np.argmax(subList))
        if i+np.argmax(subList) == j:
            changeIndices.append(j)
            w = minDist
    return changeIndices

def rolling_window(a, window):
    pad = np.ones(len(a.shape), dtype=np.int32)
    pad[-1] = window-1
    pad = list(zip(pad, np.zeros(len(a.shape), dtype=np.int32)))
    a = np.pad(a, pad,mode='reflect')
        
    shape = a.shape[:-1] + (a.shape[-1] - window + 1, window)
    strides = a.strides + (a.strides[-1],)
    return np.lib.stride_tricks.as_strided(a, shape=shape, strides=strides)

def pereiraLikelihood(theData, threshold=5.0, preEventLength=150, postEventLength=100, verbose=False, linearFactor=0.005, clean=True):
    from scipy.signal import medfilt
    data = medfilt(theData, kernel_size=9)
    # data = theData
    eventLikelihoods = np.zeros(len(data))
    # start = time.time()
    # means_0 = np.convolve(data[0:len(data)-postEventLength], np.ones((preEventLength,))/preEventLength, mode='valid')
    # means_1 = np.convolve(data[preEventLength:], np.ones((postEventLength,))/postEventLength, mode='valid')
    # print("mean: " + str(time.time()-start))
    start = time.time()
    means_0 = np.mean(rolling_window(data, preEventLength), axis=-1)
    means_1 = np.mean(rolling_window(data, postEventLength), axis=-1)
    start = time.time()
    std_0 = np.std(rolling_window(data, preEventLength), axis=-1)
    std_1 = np.std(rolling_window(data, postEventLength), axis=-1)


    std_0[np.where(std_0 < 0.01)] = 0.01
    std_1[np.where(std_1 < 0.01)] = 0.01        # Those values don't happen in reality, so increase them
         
    start = time.time()
    leng = len(data)
    for i in range(preEventLength, leng - postEventLength):
        j = i+postEventLength
        thres = threshold + means_0[i]*linearFactor
        if clean:
            if abs(means_1[j] - means_0[i]) < thres or std_1[j] == 0 or std_0[i] == 0:
                continue
        likelihood = np.log(std_0[i]/std_1[j]) + (data[i] - means_0[i])**2/(2*std_0[i]**2) - (data[i] - means_1[j])**2/(2*std_1[j]**2)
        eventLikelihoods[i] = likelihood
    # import matplotlib
    # import matplotlib.pyplot as plt
    # leng = 50*60*60*2
    # fig = plt.gcf()
    # plt.plot(np.arange(0, leng, 1), data[:leng])
    # plt.plot(np.arange(0, leng, 1), means_0[:leng])
    # plt.plot(np.arange(preEventLength, leng, 1), means_1[:leng-preEventLength])
    # plt.plot(np.arange(0, leng, 1), eventLikelihoods[:leng])
    # plt.show()
    # fig.savefig("test.pdf")

    return eventLikelihoods


def pereiraLikelihood2(theData, threshold=5.0, preEventLength=150, postEventLength=100, verbose=False, linearFactor=0.005):
    """
    Returns a Likelihood of a state change according to an equation by lucas pereira (maybe phd thesis).

    :param data: the likelihoods list or np array
    :type  data: list
    :param threshold: A threshold, a change of mean has to be in watt, default: 5 watt
    :type  threshold: float
    :param preEventLength: the window used to calculate the precious mean, default: 150
    :type  preEventLength: int
    :param postEventLength: the window used to calculate the new mean, default: 100
    :type  postEventLength: int
    :param linearFactor: the threshold is increased for larger P using this factor as
                         thre = threshold + linearFactor*mean_preWindow, default: 0.005
    :type  linearFactor: float
    :param verbose: enable verbose output
    :type  verbose: bool
    :return: glr likelihoods
    :rtype: list
    """
    from scipy.signal import medfilt
    start = time.time()
    data = medfilt(theData, kernel_size=5)
    # data = theData
    eventLikelihoods = np.zeros(len(data))
    mean_0 = data[0]
    mean_1 = np.mean(data[0:postEventLength])

    start = time.time()
    for j, p in enumerate(data):
        i = max(j-preEventLength,0)
        k = min(j+postEventLength,len(data))
        # Substract old value and add new value
        if i > 0:
            mean_0 = mean_0 - ( ( data[i-1] - data[j-1] ) / float( j-i ) )
        elif j > 0:
            mean_0 = np.mean(data[i:j])

        if k < len(data) and j > 0:
            mean_1 = mean_1 - ( ( data[j-1] - data[k-1] ) / float( k-j ) )
        else:
            mean_1 = np.mean(data[j:k])
        thres = threshold + mean_0*linearFactor
        # thres = max(threshold, mean_0*linearFactor)
        if j <= i or j+1 >= k:
            continue
        std_0 = np.std(data[i:j])
        std_1 = np.std(data[j:k])
        if abs(mean_1 - mean_0) < thres:# or std_1 == 0 or std_0 == 0:
            likelihood = 0
        else:
            # Those values don't happen in reality, so increase them
            if std_0 < 0.01: std_0 = 0.01
            if std_1 < 0.01: std_1 = 0.01
            likelihood = np.log(std_0/std_1) + (p - mean_0)**2/(2*std_0**2) - (p - mean_1)**2/(2*std_1**2)
        # likelihood = np.log(std_0/std_1) + (p - mean_0)**2/(2*std_0**2) - (p - mean_1)**2/(2*std_1**2)
        eventLikelihoods[j] = likelihood
    if verbose:
        print("Took: " + str(time.time()-start))
        print("#samples: " + str(len(data)))
        print("#samples i(x): " + str(len(eventLikelihoods)))

    return eventLikelihoods

def cleanLikelihoods(likelihoods, thres):
    cleaned = likelihoods
    for i,l in enumerate(likelihoods):
        if abs(l) < thres: cleaned[i] = 0
    return cleaned
