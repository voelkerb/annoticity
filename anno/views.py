from django.shortcuts import render
import json

from . import redd
from . import fired
from . import blond
from . import eco
from . import ukdale

def index(request):
    """ view function for sales app """
    reddInfo = redd.info()
    firedInfo = fired.info()
    blondInfo = blond.info()
    ecoInfo = eco.info()
    ukdaleInfo = ukdale.info()
    context = {"FIREDInfo": json.dumps(firedInfo), "navbar":"FIRED", "UKDALEInfo": json.dumps(ukdaleInfo), "ECOInfo": json.dumps(ecoInfo), "BLONDInfo": json.dumps(blondInfo), "REDDInfo": json.dumps(reddInfo),'use_seconds':False}

    return render(request, 'eventLabeling.html', context=context)


