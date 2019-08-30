# This file is part of ts_FiberSpectrograph.
#
# Developed for the LSST Data Management System.
# This product includes software developed by the LSST Project
# (https://www.lsst.org).
# See the COPYRIGHT file at the top-level directory of this distribution
# for details of code ownership.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

__all__ = ["FiberSpectrograph", "AvsIdentity", "DeviceConfig", "AvsReturnCode"]

import ctypes
import enum
import logging
import struct


class FiberSpectrograph:
    """Interface for the Avantes fiber spectrograph AvaSpec library.

    This class follows Resource acquisition is initialization (RAII): when
    instantiated, it opens a connection; if it cannot open a connection, it
    raises an exception. To reconnect, delete the object and create a new one.

    This class requires that ``libavs.so`` be installed in ``/usr/local/lib``.
    It is compatible with libavs version 0.2.0.

    Parameters
    ----------
    serial_number: `str`, optional
        The serial number of the USB device to connect to. If `None`, then
        connect to the only available USB device, or raise RuntimeError
        if multiple devices are connected.

    Raises
    ------
    LookupError
        Raised if there is no device with the specified serial number.
    RuntimeError
        * Raised if multiple devices are connected and no serial number
        was specified.
        * Raised if there is an error connecting to the requested device.
    """
    handle = None
    """The handle of the connected spectrograph.
    """
    device = None
    """`AvsIdentityType` of the connected spectrograph.
    """

    def __init__(self, serial_number=None):
        self.log = logging.getLogger('FiberSpectrograph')
        self.log.setLevel(logging.DEBUG)

        # dump everything to stdout, to aid debugging
        import sys
        logging.getLogger().addHandler(logging.StreamHandler(sys.stdout))

        self.libavs = ctypes.CDLL("/usr/local/lib/libavs.so.0.2.0")

        # NOTE: init(0) initializes the USB library, not device 0.
        self.libavs.AVS_Init(0)

        self._connect(serial_number)

    def _connect(self, serial_number=None):
        """Establish a connection with a single USB spectrograph.

        Parameters
        ----------
        serial_number: `str`, optional
            The serial number of the USB device to connect to. If `None`, then
            connect to the only available USB device, or raise RuntimeError
            if multiple devices are connected.

        Raises
        ------
        LookupError
            Raised if there is no device with the specified serial number.
        RuntimeError
            * Raised if multiple devices are connected and no serial number
            was specified.
            * Raised if there is an error connecting to the requested device.
        """
        n_devices = self.libavs.AVS_UpdateUSBDevices()
        if n_devices == 0:
            raise RuntimeError("No attached USB Avantes devices found.")
        self.log.debug("Found %d attached USB Avantes device(s).", n_devices)

        required_size = _getUIntPointer(n_devices * AvsIdentity.size)
        device_list = _getAvsIdentityArrayPointer(n_devices)

        code = self.libavs.AVS_GetList(required_size.contents.value, required_size, device_list)
        if code == AvsReturnCode.invalidSize:
            raise RuntimeError(f"Fatal Error: did not allocate necessary space for device list.")
        device_list = [x for x in device_list]  # unpack the array pointer
        self.log.debug("Found devices: %s", device_list)

        if serial_number is None:
            if len(device_list) > 1:
                raise RuntimeError(f"Multiple devices found, but no serial number specified."
                                   f" Attached devices: {device_list}")
            device = device_list[0]
        else:
            for device in device_list:
                if serial_number == device.SerialNumber.decode('ascii'):
                    break
            else:
                msg = f"Device serial number {serial_number} not found in device list: {device_list}"
                raise LookupError(msg)

        self.handle = self.libavs.AVS_Activate(device)
        print(self.handle)
        if self.handle == AvsReturnCode.invalidHandle:
            raise RuntimeError(f"Invalid device handle; cannot activate device {device}.")
        self.log.info("Activated connection (handle=%s) with USB device %s.", self.handle, device)
        self.device = device

    def disconnect(self):
        """Close the connection with the connected USB spectrograph.
        If the attempt to disconnect fails, log an error messages.
        """
        if self.handle is not None:
            result = self.libavs.AVS_Deactivate(self.handle)
            if not result:
                self.log.error("Could not deactivate device %s with handle %s.", self.device, self.handle)
            self.libavs.AVS_Done()

    async def get_status(self):
        """Get the status of the currently connected spectrograph.

        Returns
        -------
        status : `StatusClass?`
            The current status of the spectrograph, including temperature,
            exposure status, etc.
        """
        pass

    async def expose(self, duration):
        """Take an exposure with the currently connected spectrograph.

        Returns
        -------
        spectrum : `numpy.ndarray`
            The 1-d spectrum measured by the instrument.
        """
        pass

    async def stop_exposure(self):
        """Cancel a currently running exposure and reset the spectrograph.
        """
        pass

    def __del__(self):
        self.disconnect()


# size of these character fields in bytes
AVS_USER_ID_LEN = 64
AVS_SERIAL_LEN = 10


class AvsIdentity(ctypes.Structure):
    """Python structure to represent the `AvsIdentityType` C struct."""
    size = 75  # total size of this structure in bytes

    # size of these character fields in bytes
    AVS_SERIAL_LEN = 10

    _pack_ = 1
    _fields_ = [("SerialNumber", ctypes.c_char * AVS_SERIAL_LEN),
                ("UserFriendlyName", ctypes.c_char * AVS_USER_ID_LEN),
                ("Status", ctypes.c_char)]

    def __repr__(self):
        serial = self.SerialNumber.decode('ascii')
        name = self.UserFriendlyName.decode('ascii')
        status = struct.unpack('B', self.Status)[0]
        return f'AvaIdentity("{serial}", "{name}", {status})'

    def __eq__(self, other):
        return (self.SerialNumber == other.SerialNumber and
                self.UserFriendlyName == other.UserFriendlyName and
                self.Status == other.Status)


class DeviceConfig(ctypes.Structure):
    """Python structure to represent the `DeviceConfigType` C struct."""
    _pack_ = 1
    _fields_ = [("Len", ctypes.c_uint16),
                ("ConfigVersion", ctypes.c_uint16),
                ("aUserFriendlyId", ctypes.c_char * AVS_USER_ID_LEN),
                ("Detector_m_SensorType", ctypes.c_uint8),
                ("Detector_m_NrPixels", ctypes.c_uint16),
                ("Detector_m_aFit", ctypes.c_float * 5),
                ("Detector_m_NLEnable", ctypes.c_bool),
                ("Detector_m_aNLCorrect", ctypes.c_double * 8),
                ("Detector_m_aLowNLCounts", ctypes.c_double),
                ("Detector_m_aHighNLCounts", ctypes.c_double),
                ("Detector_m_Gain", ctypes.c_float * 2),
                ("Detector_m_Reserved", ctypes.c_float),
                ("Detector_m_Offset", ctypes.c_float * 2),
                ("Detector_m_ExtOffset", ctypes.c_float),
                ("Detector_m_DefectivePixels", ctypes.c_uint16 * 30),
                ("Irradiance_m_IntensityCalib_m_Smoothing_m_SmoothPix", ctypes.c_uint16),
                ("Irradiance_m_IntensityCalib_m_Smoothing_m_SmoothModel", ctypes.c_uint8),
                ("Irradiance_m_IntensityCalib_m_CalInttime", ctypes.c_float),
                ("Irradiance_m_IntensityCalib_m_aCalibConvers", ctypes.c_float * 4096),
                ("Irradiance_m_CalibrationType", ctypes.c_uint8),
                ("Irradiance_m_FiberDiameter", ctypes.c_uint32),
                ("Reflectance_m_Smoothing_m_SmoothPix", ctypes.c_uint16),
                ("Reflectance_m_Smoothing_m_SmoothModel", ctypes.c_uint8),
                ("Reflectance_m_CalInttime", ctypes.c_float),
                ("Reflectance_m_aCalibConvers", ctypes.c_float * 4096),
                ("SpectrumCorrect", ctypes.c_float * 4096),
                ("StandAlone_m_Enable", ctypes.c_bool),
                ("StandAlone_m_Meas_m_StartPixel", ctypes.c_uint16),
                ("StandAlone_m_Meas_m_StopPixel", ctypes.c_uint16),
                ("StandAlone_m_Meas_m_IntegrationTime", ctypes.c_float),
                ("StandAlone_m_Meas_m_IntegrationDelay", ctypes.c_uint32),
                ("StandAlone_m_Meas_m_NrAverages", ctypes.c_uint32),
                ("StandAlone_m_Meas_m_CorDynDark_m_Enable", ctypes.c_uint8),
                ("StandAlone_m_Meas_m_CorDynDark_m_ForgetPercentage", ctypes.c_uint8),
                ("StandAlone_m_Meas_m_Smoothing_m_SmoothPix", ctypes.c_uint16),
                ("StandAlone_m_Meas_m_Smoothing_m_SmoothModel", ctypes.c_uint8),
                ("StandAlone_m_Meas_m_SaturationDetection", ctypes.c_uint8),
                ("StandAlone_m_Meas_m_Trigger_m_Mode", ctypes.c_uint8),
                ("StandAlone_m_Meas_m_Trigger_m_Source", ctypes.c_uint8),
                ("StandAlone_m_Meas_m_Trigger_m_SourceType", ctypes.c_uint8),
                ("StandAlone_m_Meas_m_Control_m_StrobeControl", ctypes.c_uint16),
                ("StandAlone_m_Meas_m_Control_m_LaserDelay", ctypes.c_uint32),
                ("StandAlone_m_Meas_m_Control_m_LaserWidth", ctypes.c_uint32),
                ("StandAlone_m_Meas_m_Control_m_LaserWaveLength", ctypes.c_float),
                ("StandAlone_m_Meas_m_Control_m_StoreToRam", ctypes.c_uint16),
                ("StandAlone_m_Nmsr", ctypes.c_int16),
                ("StandAlone_m_Reserved", ctypes.c_uint8 * 12),
                ("Temperature_1_m_aFit", ctypes.c_float * 5),
                ("Temperature_2_m_aFit", ctypes.c_float * 5),
                ("Temperature_3_m_aFit", ctypes.c_float * 5),
                ("TecControl_m_Enable", ctypes.c_bool),
                ("TecControl_m_Setpoint", ctypes.c_float),
                ("TecControl_m_aFit", ctypes.c_float * 2),
                ("ProcessControl_m_AnalogLow", ctypes.c_float * 2),
                ("ProcessControl_m_AnalogHigh", ctypes.c_float * 2),
                ("ProcessControl_m_DigitalLow", ctypes.c_float * 10),
                ("ProcessControl_m_DigitalHigh", ctypes.c_float * 10),
                ("EthernetSettings_m_IpAddr", ctypes.c_uint32),
                ("EthernetSettings_m_NetMask", ctypes.c_uint32),
                ("EthernetSettings_m_Gateway", ctypes.c_uint32),
                ("EthernetSettings_m_DhcpEnabled", ctypes.c_uint8),
                ("EthernetSettings_m_TcpPort", ctypes.c_uint16),
                ("EthernetSettings_m_LinkStatus", ctypes.c_uint8),
                ("Reserved", ctypes.c_uint8 * 9720),
                ("OemData", ctypes.c_uint8 * 4096)]

    def __repr__(self):
        attrs = ', '.join(f"{x[0]}: {getattr(self, x[0])}" for x in self._fields_)
        return f"DeviceConfigType({attrs})"


@enum.unique
class AvsReturnCode(enum.IntEnum):
    success = 0
    invalidParameter = -1
    operationNotSupported = -2
    deviceNotFound = -3
    invalidDeviceId = -4
    operationPending = -5
    timeout = -6
    invalidPassword = -7
    invalidMeasurementData = -8
    invalidSize = -9
    invalidPixelRange = -10
    invalidIntegrationTime = -11
    invalidCombination = -12
    invalidConfiguration = -13
    noMeasurementBufferAvailable = -14
    unknown = -15
    communicationError = -16
    noSpectraInRam = -17
    invalidDLLVersion = -18
    noMemory = -19
    dllInitialisationError = -20
    invalidState = -21
    invalidReply = -22
    accessError = -24
    invalidParameterNumberPixels = -100
    invalidParameterADCGain = -101
    invalidParameterADCOffset = -102
    invalidMeasurementParameterAvgSat2 = -110
    invalidMeasurementParameterAvgRam = -111
    invalidMeasurementParameterSyncRam = -112
    invalidHandle = 1000


def _getUIntPointer(value=0):
    """Return a pointer to a ctypes unsigned int."""
    return ctypes.POINTER(ctypes.c_uint)(ctypes.c_uint(value))


def _getUShortPointer(value=0):
    """Return a pointer to a ctypes unsigned short."""
    return ctypes.POINTER(ctypes.c_ushort)(ctypes.c_ushort(value))


def _getAvsIdentityArrayPointer(count):
    """Return a pointer to an arry of `AvsIdentity`."""
    return (AvsIdentity * count)()
