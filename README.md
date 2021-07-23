# Annoticity

A smart labelling tool specially designed for electricity data.


Annoticity is implemented as an interactive web application. Manual labeling and inspection is performed on the client side while data fetching and automatic labeling is performed on the server. The workflow is depicted in the following Figure:

<img src="/docu/figures/flow.jpg">

The server backend is written in python using the _Django_ framework. The backend’s main purpose is to load the data and prepare it for visualization, perform the task of automatic labeling and provide file downloads. Data can be uploaded through the web application. Currently, Matroska multimedia containers (```mkv```) and ```CSV``` files are supported. The [REDD](http://redd.csail.mit.edu), [UK-DALE](https://data.ukedc.rl.ac.uk/browse/edc/efficiency/residential/EnergyConsumption/Domestic/UK-DALE-2017/ReadMe_DALE-2017.html), [BLOND](https://mediatum.ub.tum.de/1375836), [ECO](https://www.vs.inf.ethz.ch/res/show.html?what=eco-data) and the [FIRED](https://github.com/voelkerb/FIRED_dataset_helper) datasets can be directly selected (more will be added). The backend resamples the data to a reasonable sampling rate according to the current time-span selected by the user. If the dataset already contains labels they will be displayed to the user. Additionally, a file containing labels can be uploaded and modified. The supported formats are ```csv```, ```srt``` and ```ass```. An automatic labeling algorithm generates labels from the data by identifying events. These events are clustered, pre-labeled and sent to the client side for inspection and validation.
The client side is implemented in _HTML_ and _JavaScript_ and provides the frontend to the user. 

<img src="/docu/figures/gui.jpg">

After either uploading a file or selecting a timespan and device of an available dataset, the user can visually inspect the data. Different measures (e.g. active and reactive power) can be selected, and data can be zoomed in which leads to a data download at a higher sampling rate. The user can add a label by clicking at the slope where an event occurs, remove the label by clicking on the vertical bar, or modify the label. Each label consists of a start time and a (possibly empty) text description. The frontend also allows to set the parameters of the automatic labeling algorithm. Labels are stored either as plain ```csv```, ```ass``` or ```srt``` files or embedded into a ```mkv``` file together with the original data.

Even though the tool is optimized to label electricity data, it can be applied to other time series data as well.

## Hosting
Annoticity is hosted at the University of Freiburg at [https://earth.informatik.uni-freiburg.de/annoticity](https://earth.informatik.uni-freiburg.de/annoticity).

## Reference

Please cite our publications if you compare to or use this system:

* Benjamin Völker, Marc Pfeifer, Philipp M. Scholl, and Bernd Becker. 2020. "Annoticity: A Smart Annotation Tool and Data Browser for Electricity Datasets." Proceedings of the 5th International Workshop on Non-Intrusive Load Monitoring. 2020. DOI:https://doi.org/10.1145/3427771.3427844

* Benjamin Völker, Marc Pfeifer, Philipp M. Scholl, and Bernd Becker. 2021. A Framework to Generate and Label Datasets for Non-Intrusive Load Monitoring. Energies 2021, 14, 75. DOI:https://doi.org/10.3390/en14010075
