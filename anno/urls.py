"""anno URL Configuration"""

from django.urls import path
from django.conf.urls import url, include
from . import views
from . import labels
from . import fired
from . import redd
from . import uploaded
from . import autoLabel
from . import blond
from . import eco
from . import ukdale
from . import fileDownloader

urlpatterns = [
    path('', views.index, name='index'),
    # url(r'', views.index, name='index'),
    path('data/FIRED/startTs=<int:startTs>&stopTs=<int:stopTs>', fired.getData, name='getData'),
    path('data/FIRED/dev=<str:meter>&day=<str:day>', fired.initChart, name='initChart'),
    
    path('data/BLOND/startTs=<int:startTs>&stopTs=<int:stopTs>', blond.getData, name='getData'),
    path('data/BLOND/set=<str:set>&meter=<str:meter>&channel=<str:channel>&day=<str:day>', blond.initChart, name='initChart'),
    
    path('data/ECO/startTs=<int:startTs>&stopTs=<int:stopTs>', eco.getData, name='getData'),
    path('data/ECO/house=<str:house>&meter=<str:meter>&day=<str:day>', eco.initChart, name='initChart'),
        
    path('data/UKDALE/startTs=<int:startTs>&stopTs=<int:stopTs>', ukdale.getData, name='getData'),
    path('data/UKDALE/house=<str:house>&meter=<str:meter>&day=<str:day>', ukdale.initChart, name='initChart'),
    path('data/UKDALE/times/house=<str:house>&meter=<str:meter>', ukdale.getTimes, name='getTimes'),
    
    path('data/REDD/house=<int:house>&channel=<int:channel>&day=<str:day>', redd.initChart, name='initChart'),
    path('data/REDD/startTs=<int:startTs>&stopTs=<int:stopTs>', redd.getData, name='getData'),
    
    path('data/uploadFile/', uploaded.dataUpload, name='dataUpload'),
    path('data/Upload/startTs=<int:startTs>&stopTs=<int:stopTs>', uploaded.getData, name='getData'),
    
    path('data/downloadMKV/', fileDownloader.download, name='download'),
    path('data/uploadLabel/', labels.labelUpload, name='labelUpload'),
    path('data/autoLabel/', autoLabel.autoLabel, name='autoLabel'),
]
