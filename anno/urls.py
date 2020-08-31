"""anno URL Configuration"""

from django.urls import path
from django.conf.urls import url, include
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    # url(r'', views.index, name='index'),
    path('data/FIRED/dev=<str:meter>&measure=<str:measure>&startTs=<int:startTs>&stopTs=<int:stopTs>', views.getDeviceData, name='getDeviceData'),
    path('data/FIRED/dev=<str:meter>&measure=<str:measure>&day=<str:day>', views.initChart, name='initChart'),
    path('data/REDD/house=<int:house>&channel=<int:channel>&day=<str:day>', views.getREDDData, name='getREDDData'),
    path('data/REDD/startTs=<int:startTs>&stopTs=<int:stopTs>', views.getREDDDataRange, name='getREDDDataRange'),
    # path('data/uploaded/pow=<str:measure>', views.initChartUploaded, name='initChartUploaded'),
    path('data/uploaded/measure=<str:measure>&startTs=<int:startTs>&stopTs=<int:stopTs>', views.getDataUploaded, name='getDataUploaded'),
    path('data/downloadMKV/', views.downloadMKV, name='downloadMKV'),
    path('data/uploadLabel/', views.labelUpload, name='labelUpload'),
    path('data/uploadFile/', views.dataUpload, name='dataUpload'),
    path('data/autoLabel/', views.autoLabel, name='autoLabel'),
]
