"""
Identifiers for physical values and units.
Try to use all these identifiers in the code, to avoid having explicit, potentially changing strings inside the code.

e.g. To access the voltage waveform stored in a MKV file, use

.. code-block:: python3

    # Load the mkv file into a list of all streams
    dataList = mkv.loadAudio(<filePath>)
    # Get recarray of first stream
    data = dataList[0]["data"]
    # Get only the voltage waveform
    voltage = data[vu.VOLTAGE[0]]
    # Get only the current waveform
    voltage = data[vu.CURRENT[0]]

"""
# Only done like this to make Sphinx docu more nice. I know that this is shit
from vu_identifiers import *
from vu_units import *
from vu_names import *
from vu_features import *