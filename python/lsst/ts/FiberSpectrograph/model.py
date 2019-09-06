import time
import asyncio
from astropy.io import fits
import logging

import pathlib

from lsst.utils import getPackageDir

from lsst.ts.FiberSpectrograph.fibspec import MeasConfigType, DeviceConfigType, \
    AVS


class FiberSpec(object):

    def __init__(self):
        """Setup FiberSpectrograph
        Get information of the FiberSpectrograph: serial number, handle of the
        connected instrument. On start this method is executed.
        """
        self.serialNumber = 0
        self.configuration = MeasConfigType
        self.devCon = DeviceConfigType
        self.dev_handle = 0
        self.pixels = 4095
        self.spectralData = [0.0] * 4096
        self.waveLength = [0.0] * 4096
        self.f = AVS()
        self.f.init(0)

        self.modulePath = getPackageDir("ts_FiberSpectrograph")
        self.dataFolder = pathlib.Path(self.modulePath).joinpath("fits", "data")
        # self.folderString = self.dataFolder.as_posix()

        # Logfile name is set to log concatenated with current time in format
        # specified below
        self.timestr = time.strftime("%Y%m%d-%H%M%S")

        logfile = "log"+self.timestr+".txt"
        logging.basicConfig(filename=logfile, level=logging.DEBUG, format='%(asctime)s \
            - %(levelname)s - %(message)s')
        logging.debug(f"init(0) -> {self.f.init(0)}")
        # Number of usb FiberSpectrograph connected
        NumDevices = self.f.getNumberOfDevices()
        logging.debug(f"getNumberOfDevices() -> {NumDevices}")

        # List of FiberSpectrograph
        a, b = self.f.getList()
        logging.debug(f"getList() -> {a} {b}")

        # Serial Number of 1st FiberSpectrograph from the list
        self.serialNumber = str(b[0].SerialNumber.decode("utf-8"))
        logging.debug(f"SerialNumber -> {self.serialNumber}")

        # Activate 1st FiberSpectrograph and get the handle of the device
        self.dev_handle = self.f.activate(b[0])
        logging.debug(f"devHandle -> {self.dev_handle}")

        self.devcon = DeviceConfigType
        ret = self.f.getParameter(self.dev_handle, 0)
        logging.debug(f"AVS_GetParameter(self.dev_handle, 0) -> {ret}")

    def _checkErrorConditions(self):
        # Raise error if device handle is invalid and move to Fault state
        if (self.dev_handle <= 0 or self.NumDevices <= 0):
            raise ConnectionError("Device is OFF or lost connection to device")

    def closeComm(self):
        """Close communication and release all internal data storage
        The close function (AVS_Done()) closes the communication port(s) and
        releases all internal data storage.
        Return SUCCESS
        """
        self.f.done()
        return

    async def captureSpectImage(self, integrationTime, imageType, lamp):
        """Capture Spectrum for the integration time specified.
        Capture Spectrum for the integration time specified.
        """
        self._checkErrorConditions()

        self.fitsFilename = "Spectrum"+imageType+lamp+self.timestr+".fits"
        self.fitsFilePath = pathlib.Path(self.dataFolder.joinpath(self.fitsFilename))

        self.hdr = fits.ImageHDU()
        self.hdr.header['INTTIME'] = integrationTime
        self.hdr.header['IMGTYPE'] = imageType
        self.hdr.header['LIGHTUSED'] = lamp
        self.primary_hdu = fits.PrimaryHDU(header=self.hdr)

        ret = self.f.useHighResADC(self.dev_handle, True)
        logging.debug(f"useHighResADC(self.dev_handle, True) -> {ret}")
        measconfig = MeasConfigType()
        measconfig.m_StartPixel = 0
        measconfig.m_StopPixel = 2047
        measconfig.m_IntegrationTime = integrationTime*1000
        measconfig.m_IntegrationDelay = 0
        measconfig.m_NrAverages = 1
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

        # Prepares measurement on the spectrometer using the specified
        # measurement configuration.
        ret = self.f.prepareMeasure(self.dev_handle, measconfig)
        logging.debug(f"prepareMeasure({self.dev_handle}, measconfig) -> {ret}")

        # Starts measurement on the spectrometer
        ret = self.f.measure(self.dev_handle, 1)
        logging.debug(f"measure({(self.dev_handle,1)} -> {ret}")

        dataready = False
        while (dataready is False):
            dataready = (self.f.pollScan(self.dev_handle) is True)
            logging.debug(f"dataready is -> {dataready}")
            await asyncio.sleep(0.1)
        if (dataready is True):
            self.handle_newdata(self.imageType, self.lamp)

        return

    def stopMeas(self):
        """Stops the measurement
        Stops the measurements (needed if Nmsr = infinite), can also be used to
        stop a pending measurement with long integration time and/or
        high number of averages
        Returns
        -------
        integer
            0 for success
            error code as defined in AVAReturnCodes in fibSpec.py
        """
        ret = self.f.stopMeasure(self.dev_handle)
        return ret

    def handle_newdata(self, imageType, lamp):
        """After Capturing spectrum this method is used to get Wavelength data
        and intensity data
        PollScan is used to determine if the capture spectrum is complete.
        Once pollscan=1, data is ready and can be retrieved from the
        FiberSpectrograph instrument.
        getLambda and getScopeData is used to get the wavelength data and
        intensity of light respectively.
        """
        logging.debug("In handle_newdata")
        # Get Wavelength data for pixel index 0 to 4095
        ret, measurement = self.f.getLambda(self.dev_handle, 4096)
        fits.append(self.dataFolder, measurement, self.primary_hdu)
        logging.debug(f"AVS_getLambda data -> {ret}")
        logging.debug("The first 10 measurement points are %s." % measurement[:10])
        # Get intensity of measured light for pixel index 0 to 4095
        ret, self.spectralData, intensity = self.f.getScopeData(self.dev_handle, 4096)
        fits.append(self.dataFolder, intensity)
        logging.debug("The first 10 intensity points are %s." % intensity[:10])

        return
