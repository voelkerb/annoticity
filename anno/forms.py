from bootstrap_datepicker_plus import DatePickerInput
from django import forms

import sys
sys.path.insert(0, '/Users/voelkerb/Documents/smartenergy/datasets/FIRED')
import helper as hp

hp.FIRED_BASE_FOLDER = "/Users/voelkerb/dump/FIRED/"
# Create your views here.


class FIREDSelectionForm(forms.Form):

    meters = hp.getMeterList()
    devicePickerChoices = ((m, m) for m in meters)
    meter = forms.ChoiceField(choices=devicePickerChoices, label="Device")
    date = forms.DateField(
        widget=DatePickerInput(format='%m/%d/%Y')
    )