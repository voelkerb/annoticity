"""Class for Measurement Data."""

import sys
import os
import numpy as np
import math
import time
import warnings
from scipy.spatial import distance
import scipy.fftpack as fftp
from scipy import signal

def zerocrossings(data):
    signs = np.sign(data)
    # Since np.sign(0) yields 0,
    # we treat them as negative sign here
    signs[signs == 0] = -1
    return len(np.where(np.diff(signs))[0])

def zcr(data):
    """
    Return the Zero Crossing Rate.

    :param data: Data
    :type  data: list
    :return: Zero Crossing Rate
    :rtype: float
    """
    signs = np.sign(data)
    # Since np.sign(0) yields 0,
    # we treat them as negative sign here
    signs[signs == 0] = -1
    return len(np.where(np.diff(signs))[0])/len(data)

def rms(data, axis=None):
    """
    Return the RMS value of the data.

    :param data: Data
    :type  data: list
    :param axis: Currently not in use
    :type  axis: None
    :return: Root Mean Square of the data
    :rtype: float
    """
    return np.sqrt(data.dot(data)/data.size)

def normalizedZCR(data, samplingRate, LINE_FREQUENCY=50.0):
    r"""
    Return the normalized Zero Crossing Rate.

    It is normalized by the expected value which is 2*50 crossings
    per second in 50Hz networks. Therefore a value of 1 corresponds to
    50 Zero Crossings in 1 second. If the length of the data given is
    smaller than 1 second, the data is scaled down
    2*50/2  in 0.5s
    2*50/10 in 0.1s etc.
    It is further normalized by making it mean free. If the data is lifted
    and oscillates around an offset. The offset is guessed and subtracted.
    The maximum of the meanfree and untouched ZCR is returned.

    TODO: If the data is not symmetric, the mean is not a good estimate

    :param data: Data
    :type  data: list
    :param samplingRate: Numbers of data samples per second
    :type  samplingRate: int
    :param LINE_FREQUENCY: 50 or 60 Hz, default=50
    :type  LINE_FREQUENCY: float
    :return: Normalized Zero Crossing Rate
    :rtype: float
    """
    # we make data meanfree
    mean = np.mean(data)
    signs = np.sign(data-mean)
    signs2 = np.sign(data)
    # Since np.sign(0) yields 0,
    # we treat them as negative sign here
    signs[signs == 0] = -1
    signs2[signs2 == 0] = -1
    # get expected ZCR
    samplesPerPhase = int(samplingRate/LINE_FREQUENCY)
    expectedZeroCrossings = len(data)/samplesPerPhase * 2
    zcrNoMean = len(np.where(np.diff(signs2))[0])/expectedZeroCrossings
    zcrMean = len(np.where(np.diff(signs))[0])/expectedZeroCrossings
    return max(zcrNoMean, zcrMean)


def calcFullPowers(voltage, current, samplingRate, LINE_FREQUENCY=50.0):
    """
    Calculate Active, Reactive and Apparent power from voltage and current.

    :param voltage:      Voltage in volt
    :type  voltage:      list or np.array
    :param current:      Current in milli ampere
    :type  current:      list or np.array
    :param samplingRate: Samplingrate for phase calculation
    :type  samplingRate: int
    :param LINE_FREQUENCY: 50 or 60 Hz, default=50
    :type  LINE_FREQUENCY: float
    :return: Active, Reactive and Apparent Power with 50Hz samplingrate
    :rtype: Tuple
    """
    sfos = int(samplingRate/LINE_FREQUENCY)
    p = []
    s = []
    q = []
    # Calculate active power from voltage and current
    for i in range(len(voltage)-sfos):
        start = i
        u = np.array(voltage[start:start+sfos])
        i = np.array(current[start:start+sfos])
        temp = 0.001*np.mean(u*i)
        p.append(temp if temp > 0 else 0)
        urms = np.sqrt(u.dot(u)/u.size)
        irms = np.sqrt(i.dot(i)/i.size)
        s.append(0.001*urms*irms)
        q.append(math.sqrt(abs(s[-1]*s[-1] - p[-1]*p[-1])))
    return p, q, s


def calcPowers(voltage, current, samplingRate, upsamplingMethod=None, LINE_FREQUENCY=50):
    """
    Calculate Active, Reactive and Apparent power from voltage and current.

    :param voltage:      Voltage in volt
    :type  voltage:      list or np.array
    :param current:      Current in milli ampere
    :type  current:      list or np.array
    :param samplingRate: Samplingrate for phase calculation
    :type  samplingRate: int
    :param upsamplingMethod: If final data should be same samplingrate as input data, default=None
                             One in [\"linear\",\"repeat\"]
    :type  upsamplingMethod: str
    :param LINE_FREQUENCY: 50 or 60 Hz, default=50
    :type  LINE_FREQUENCY: float
    :return: Active, Reactive and Apparent Power as np.arrays
    :rtype: Tuple
    """
    sfos = int(samplingRate/LINE_FREQUENCY)
    numPoints = len(voltage)
    reshaping = int(math.floor(numPoints/sfos))
    end = reshaping*sfos

    # Make both mean free
    v = voltage[:end]
    c = current[:end]
    momentary = 0.001*np.array(v[:end]*c[:end])

    # # moving avg. over sfos 
    # ones = np.ones((sfos,))/sfos
    # momentary = np.convolve(momentary, ones, mode='valid')

    # bringing down to 50 Hz by using mean
    momentary = momentary.reshape((-1, sfos))
    p = np.mean(momentary, axis=1)

    v = v[:end].reshape((-1, sfos))
    i = c[:end].reshape((-1, sfos))

    # quicker way to do this
    vrms = np.sqrt(np.einsum('ij,ij->i', v, v)/sfos)
    irms = np.sqrt(np.einsum('ij,ij->i', i, i)/sfos)

    # Because unit of current is in mA
    s = 0.001*vrms*irms
    q = np.sqrt(np.abs(s*s - p*p))

    # Handle upsampling here
    if upsamplingMethod is not None:
        if upsamplingMethod == "linear":
            x = np.linspace(0, end/samplingRate, end/samplingRate*LINE_FREQUENCY)
            x_new = np.linspace(0, end/samplingRate, end)
            s = np.interp(x_new, x, s)
            p = np.interp(x_new, x, p)
            q = np.interp(x_new, x, q)
        elif upsamplingMethod == "repeat":
            s = np.repeat(s, sfos)
            p = np.repeat(p, sfos)
            q = np.repeat(q, sfos)
        if end != numPoints:
            s = np.append(s, np.repeat(s[-1], numPoints-end))
            p = np.append(p, np.repeat(p[-1], numPoints-end))
            q = np.append(q, np.repeat(q[-1], numPoints-end))
    return p,q,s


def lowpass(data, fs, order, fc):
    nyq = 0.5 * fs  # Calculate the Nyquist frequency.
    cut = fc / nyq  # Calculate the cutoff frequency (-3 dB).
    lp_b, lp_a = signal.butter(order, cut, btype='lowpass')  # Design and apply the low-pass filter.
    lp_data = list(signal.filtfilt(lp_b, lp_a, data))  # Apply forward-backward filter with linear phase.
    return lp_data

def index2Freq(i, sampleRate, nFFT):
    """
    Return the frequency for a given FTT index.

    :param i: Index
    :type  i: int
    :param sampleRate: Numbers of data samples per second
    :type  sampleRate: int
    :param nFFT: Length of fourier transform
    :type  nFFT: int
    :return: Frequency at the given FFT index
    :rtype: int
    """
    return (i * (sampleRate / (nFFT*2)))

def freq2Index(freq, sampleRate, nFFT):
    """
    Return the FTT index for a given frequency.

    :param freq: Frequency, of which the bins should be returned
    :type  freq: int
    :param sampleRate: Numbers of data samples per second
    :type  sampleRate: int
    :param nFFT: Length of fourier transform
    :type  nFFT: int
    :return: FFT index of the given frequency
    :rtype: int
    """
    return int(round(freq / (sampleRate / (nFFT*2)), 3))

def fftBinsForFreqs(freqs, sample_rate, data):
    """
    Return the fft bin(s) (value) corresponding to given frequency.

    :param freqs: Frequencies, of which the bins should be returned
    :type  freqs: list
    :param sample_rate: Numbers of data samples per second
    :type  sample_rate: int
    :param data: Fourier transform
    :type  data: list
    :return: Bins corresponding to given frequencies
    :rtype: list
    """
    magnitudes = []
    for freq in freqs:
        bin = freq2Index(freq, sample_rate, len(data))
        magnitudes.append(data[int(bin)])
    return magnitudes

def fftBinIndexesForFreqs(freqs, sample_rate, data):
    """
    Return the fft bin(s) (index) corresponding to given frequencies.

    :param freqs: Frequencies, of which the bins should be returned
    :type  freqs: list
    :param sample_rate: Numbers of data samples per second
    :type  sample_rate: int
    :param data: Fourier transform
    :type  data: list
    :return: Bins that correspond to the given frequencies
    :rtype: list
    """
    bins = []
    # We can only reconstruct half the samplingRate
    for freq in freqs:
        bin = freq2Index(freq, sample_rate, len(data))
        bins.append(bin)
    return bins

def fft2(data, nfft):
    """
    Calculate the fft of signal 'data'.

    The fft is comuted using the numpy.fft.fft.

    :param data: Data
    :type  data: list
    :param nfft: Length of fourier transform
    :type  nfft: int
    :return: Transformed input
    :rtype: list
    """
    if (len(data) > nfft):
        print("Warning: FFT size should be larger than data size.")
    N = nfft
    FFT = np.fft.fft(data, norm="ortho", n=N)[:N//2]/nfft
    return abs(FFT)

def fft(data, nfft):
    """
    Calculate the fft of signal 'data'.

    The fft is comuted using the scipy.fftpack.fft.

    :param data: Data
    :type  data: list
    :param nfft: Length of fourier transform
    :type  nfft: int
    :return: Transformed input
    :rtype: list
    """
    if (len(data) > nfft):
        print("Warning: size should be larger than data size.")
    FFT = fftp.fft(data, n=nfft)[:nfft//2]/nfft
    return abs(FFT)

def goertzel(samples, sample_rate, freqRanges):
    """
    Implement the Goertzel algorithm.

    Implementation of the Goertzel algorithm, useful for calculating
    individual terms of a discrete Fourier transform. Result are firstly
    the actual frequencies calculated and secondly the coefficients for
    each of those frequencies `(real part, imag part, power)`. For simple
    spectral analysis, the power is usually enough.

    :param samples: Windowed one-dimensional signal
    :type  samples: list
    :param sample_rate: Original rate the signal is sampled at
    :type  sample_rate: int
    :param freqRanges: Ranges of frequencies that are meant to be computed
    :type  freqRanges: list of tuples
    :return: The calculated frequencies and the coefficients (as 3-tuple)
    :rtype: list, list

    :Example:
        Calculating frequencies in ranges [400, 500] and [1000, 1100]
        of a windowed signal sampled at 44100 Hz.
        ``freqs, results = goertzel(some_samples, 44100,[(400, 500),
        (1000, 1100)])``
    """
    window_size = len(samples)
    f_step = sample_rate / float(window_size)
    f_step_normalized = 1.0 / window_size

    # Calculate all the DFT bins we have to compute to include frequencies
    # in `freqs`.
    bins = set()
    for f_range in freqRanges:
        f_start, f_end = f_range
        k_start = int(math.floor(round(f_start / f_step, 3)))
        k_end = int(math.ceil(round(f_end / f_step, 3)))
        if k_end > window_size - 1:
            raise ValueError('frequency out of range %s' % k_end)
        bins = bins.union(range(k_start, k_end))

    # For all the bins, calculate the DFT term
    n_range = range(0, window_size)
    freqs = []
    results = []
    for k in bins:

        # Bin frequency and coefficients for the computation
        f = k * f_step_normalized
        w_real = 2.0 * math.cos(2.0 * math.pi * f)
        w_imag = math.sin(2.0 * math.pi * f)

        # Doing the calculation on the whole sample
        d1, d2 = 0.0, 0.0
        for n in n_range:
            y = samples[n] + w_real * d1 - d2
            d2, d1 = d1, y

        # Storing results `(real part, imag part, power)`
        results.append((
            0.5 * w_real * d1 - d2, w_imag * d1,
            d2**2 + d1**2 - w_real * d1 * d2)
        )
        freqs.append(f * sample_rate)
    return freqs, results

def absDist(v1, v2):
    """
    Return absolut distance between two scalar values.

    :param v1: First value
    :type  v1: float
    :param v2: Second vector
    :type  v2: float
    :return: The absolute distance
    :rtype: float
    """
    if np.sign(v1) == np.sign(v2):
        return abs(abs(v1) - abs(v2))
    else:
        return abs(abs(v1) + abs(v2))

DEBUG = False

def euclideanDistance(vec1, vec2):
    r"""
    Calculate the euclidean distance of two given (feature) vectors.

    .. math::
       ||\vec{v_1} - \vec{v_2}|| = \sqrt{\sum_{K=1}^{N} (vec_{1,k} - vec_{2,k})^2}

    :param vec1: First vector
    :type  vec1: list
    :param vec2: Second vector
    :type  vec2: list
    :return: The euclidean distance
    :rtype: float
    """
    # return distance.euclidean(vec1, vec2)
    return np.linalg.norm(np.array(vec1)-np.array(vec2))

def quadraticDistance(vec1, vec2):
    r"""
    Calculate the quadratic distance of two given (feature) vectors.

    .. math::
       \sum_{K=1}^{N} (vec_{1,k} - vec_{2,k})^2

    :param vec1: First vector
    :type  vec1: list
    :param vec2: Second vector
    :type  vec2: list
    :return: The quadratic distance
    :rtype: float
    """
    return sum([(s1 - s2)**2 for s1, s2 in zip(vec1, vec2)])

def manhattan_distance(vec1, vec2):
    r"""
    Return the manhattan distance between two vectors.

    .. math::
       \sum_{K=1}^{N} vec_{1,k} - vec_{2,k}

    :param vec1: First vector
    :type  vec1: list
    :param vec2: Second vector
    :type  vec2: list
    :return: The manhattan distance
    :rtype: float
    """
    return sum(abs(a-b) for a, b in zip(vec1, vec2))

def compareSine(sine1, sine2, hard=True):
    """
    Compare two sinewaves and return true if similar enough.

    :param sine1: First sine
    :type  sine1: list
    :param sine2: Second sine
    :type  sine2: list
    :param hard: Sets the threshold to 0.01 if True, 0.02 if False
    :type  hard: bool
    :return: The quadratic distance
    :rtype: float
    """
    # Compare them two
    if len(sine1) != len(sine2):
        warnings.warn("Sinewaves need equal length for comparison")
        return False
    rms = rms(sine1)
    # calculate euclidean distance
    dst = distance.euclidean(sine1, sine2)/(len(sine1)*rms)
    rmsDst = absDist(rms, rms(sine2))
    meanDst = absDist(np.mean(sine1), np.mean(sine2))
    if hard is True:
        dstThreshold = 0.01
    else:
        dstThreshold = 0.02

    meanDstThreshold = max(rms*0.075, 5)
    rmsDstThreshold = max(rms*0.0075, 10)

    if (dst < dstThreshold and meanDst < meanDstThreshold and
            rmsDst < rmsDstThreshold):
        return True
    else:
        return False