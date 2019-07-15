#!/usr/bin/env python3
import os
import platform
import sys
import time
from fibspec import *


class FiberSpectrograph(object):

    def __init__(self):
        self.serialNumber = 0
        self.configuration = MeasConfigType
        self.devCon = DeviceConfigType
        self.dev_handle = 0
        self.pixels = 4095
        self.spectralData = [0.0] * 4096
        self.waveLength = [0.0] * 4096
        self.f = AVS()
        self.f.init(0)
        print(f"init(0) -> {self.f.init(0)}")
        NumDevices = self.f.getNumberOfDevices()
        print(f"getNumberOfDevices() -> {NumDevices}")
        a, b = self.f.getList()
        print(f"getList() -> {a} {b}")
        self.serialNumber = str(b[0].SerialNumber.decode("utf-8"))
        print(f"SerialNumber -> {self.serialNumber}")
        self.dev_handle=self.f.activate(b[0])
        print(f"devHandle -> {self.dev_handle}")
        self.devcon=DeviceConfigType
        ret=self.f.getParameter(self.dev_handle,0)
        print(f"AVS_GetParameter(self.dev_handle, 0) -> {ret}")

    def closeComm(self):
#        callbackclass.callback(self, 0, 0)
        pass

    def captureSpectImage(self, m_IntegrationTime, m_NrAverages, nummeas):
        ret = self.f.useHighResADC(self.dev_handle, True)
        print(f"useHighResADC(self.dev_handle, True) -> {ret}")
        measconfig = MeasConfigType()
        measconfig.m_StartPixel = 0
        measconfig.m_StopPixel = 2047
        measconfig.m_IntegrationTime = m_IntegrationTime
        measconfig.m_IntegrationDelay = 0
        measconfig.m_NrAverages = m_NrAverages
        measconfig.m_CorDynDark_m_Enable = 0  # nesting of types does NOT work!!
        measconfig.m_CorDynDark_m_ForgetPercentage = 0
        measconfig.m_Smoothing_m_SmoothPix = 0
        measconfig.m_Smoothing_m_SmoothModel = 0
        measconfig.m_SaturationDetection = 0
        measconfig.m_Trigger_m_Mode = 0
        measconfig.m_Trigger_m_Source = 0
        measconfig.m_Trigger_m_SourceType = 0
        measconfig.m_Control_m_StrobeControl = 0
        measconfig.m_Control_m_LaserDelay = 0
        measconfig.m_Control_m_LaserWidth = 0
        measconfig.m_Control_m_LaserWaveLength = 0.0
        measconfig.m_Control_m_StoreToRam = 0
        ret = self.f.prepareMeasure(self.dev_handle, measconfig)
        print(f"prepareMeasure({self.dev_handle}, measconfig) -> {ret}")
        ret = self.f.measure(self.dev_handle, 1)
        print(f"measure({(self.dev_handle,1)} -> {ret}")
        dataready = False    
        while (dataready == False):
            dataready = (self.f.pollScan(self.dev_handle) == True)
            print(f"dataready is -> {dataready}")
            time.sleep(0.001)
        if dataready == True:
               self.handle_newdata()

        return


    def stopMeas(self):
        ret = self.f.stopMeasure(self.dev_handle)
        return ret

    def handle_newdata(self):
        print("In handle_newdata")
        ret, measurement = self.f.getLambda(self.dev_handle, 4096)
        print(f"AVS_getLambda data -> {ret}")
        print("The first 10 measurement points are %s." % measurement[:10])
        ret, self.spectralData, intensity = self.f.getScopeData(self.dev_handle, 4096)
        print("The first 10 intensity points are %s." % intensity[:10])
   
        return


 


