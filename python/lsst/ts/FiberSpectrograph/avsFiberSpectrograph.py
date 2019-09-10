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

__all__ = ["AvsFiberSpectrograph", "AvsIdentity", "DeviceConfig", "AvsReturnCode", "AvsReturnError"]

import asyncio
import ctypes
import dataclasses
import enum
import logging
import struct

import numpy as np

# Fully-qualified path to the vendor-provided libavs AvaSpec library.
# If installed via the vendor packages, it will be in `/usr/local/lib`.
LIBRARY_PATH = "/usr/local/lib/libavs.so.0.2.0"


class AvsReturnError(Exception):
    """Exception raised if an ``AVS_*`` C function returns an error code.

    Parameters
    ----------
    code : `int`
        The error code returned by the failing function.
    what : `str`
        The function that was called that returned this error code.
    """
    def __init__(self, code, what):
        try:
            self.code = AvsReturnCode(code)
            self._valid = True
        except ValueError:
            # unknown error codes are handled with a separate message.
            self._valid = False
            self.code = code
        self.what = what

    def __str__(self):
        if self._valid is False:
            return (f"Unknown Error ({self.code}) calling `{self.what}`;"
                    " Please consult Avantes documentation and update `AvsReturnCode` to include this code.")
        if self.code == AvsReturnCode.ERR_INVALID_SIZE:
            return f"Fatal Error {self.code!r} calling `{self.what}`: allocated size too small for data."
        else:
            return f"Error calling `{self.what}` with error code {self.code!r}"

    def __repr__(self):
        return f"{type(self).__name__}({self!s})"


def assert_avs_code(code, what):
    """Raise if the code returned from an AVS function call is an error.

    Parameters
    ----------
    code : `int`
        The value returned from a call to an AVS function.
    what : `str`
        The function that was called that returned this error code.

    Raises
    ------
    AvsReturnError
        Raised if ``code`` is a non-success error code.
    """
    if code < 0:
        raise AvsReturnError(code, what)


class AvsFiberSpectrograph:
    """Interface for the Avantes fiber spectrograph AvaSpec library.

    This class follows Resource acquisition is initialization (RAII): when
    instantiated, it opens a connection; if it cannot open a connection, it
    raises an exception. To reconnect, delete the object and create a new one.

    This class requires that ``libavs.so`` be installed in ``/usr/local/lib``.
    It is compatible with libavs version 0.2.0.

    Parameters
    ----------
    serial_number : `str`, optional
        The serial number of the USB device to connect to. If `None`, then
        connect to the only available USB device, or raise RuntimeError
        if multiple devices are connected.
    log : `logging.Logger`, optional
        A Logger instance to send log messages to.
    log_to_stdout : `bool`
        Send all log info from DEBUG up to stdout. Useful when debugging the
        spectrograph in a python terminal.

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

    def __init__(self, serial_number=None, log=None, log_to_stdout=False):
        if log is None:
            self.log = logging.getLogger('FiberSpectrograph')
        if log_to_stdout:
            self.log.setLevel(logging.DEBUG)
            import sys
            logging.getLogger().addHandler(logging.StreamHandler(sys.stdout))

        # create a "done" future
        self._expose_task = asyncio.Future()
        self._expose_task.set_result(None)

        self.libavs = ctypes.CDLL(LIBRARY_PATH)

        # NOTE: AVS_Init(0) initializes the USB library, not device 0.
        self.libavs.AVS_Init(0)

        self._configure_ctypes()

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
            Raised if multiple devices are connected and no serial number
            was specified.
        AvsReturnError
            Raised if there is an error connecting to the requested device.
        """
        n_devices = self.libavs.AVS_UpdateUSBDevices()
        if n_devices == 0:
            raise RuntimeError("No attached USB Avantes devices found.")
        self.log.debug("Found %d attached USB Avantes device(s).", n_devices)

        required_size = _getUIntPointer(n_devices * ctypes.sizeof(AvsIdentity))
        device_list = _getAvsIdentityArrayPointer(n_devices)

        code = self.libavs.AVS_GetList(required_size.contents.value, required_size, device_list)
        assert_avs_code(code, "GetList (device list)")
        device_list = list(device_list)  # unpack the array pointer
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
        assert_avs_code(self.handle, "Activate")
        if self.handle == AvsReturnCode.invalidHandle:
            raise RuntimeError(f"Invalid device handle; cannot activate device {device}.")
        self.log.info("Activated connection (handle=%s) with USB device %s.", self.handle, device)
        self.device = device

        # store the number of pixels for use when taking exposures.
        n_pixels = _getUShortPointer()
        code = self.libavs.AVS_GetNumPixels(self.handle, n_pixels)
        assert_avs_code(code, "GetNumPixels")
        self._n_pixels = n_pixels.contents.value

    def disconnect(self):
        """Close the connection with the connected USB spectrograph.
        If the attempt to disconnect fails, log an error messages.
        """
        if self.handle is not None and self.handle != AvsReturnCode.invalidHandle:
            self.stop_exposure()  # stop any active exposure
            result = self.libavs.AVS_Deactivate(self.handle)
            if not result:
                self.log.error("Could not deactivate device %s with handle %s. Assuming it is safe to "
                               "close the communication port anyway.", self.device, self.handle)
            self.handle = None
        self.libavs.AVS_Done()

    def get_status(self, full=False):
        """Get the status of the currently connected spectrograph.

        Parameters
        ----------
        full : `bool`
            Include the full `DeviceConfig` structure in the returned status.
            This can be useful for understanding what other information is
            available from the spectrograph, but requires having the Avantes
            manual on hand to decode it.

        Returns
        -------
        status : `DeviceStatus`
            The current status of the spectrograph, including temperature,
            exposure status, etc.

        Raises
        ------
        AvsReturnError
            Raised if there is an error querying the device.
        """
        fpga_version = (ctypes.c_ubyte * 16)()
        firmware_version = (ctypes.c_ubyte * 16)()
        library_version = (ctypes.c_ubyte * 16)()
        code = self.libavs.AVS_GetVersionInfo(self.handle, fpga_version, firmware_version, library_version)
        assert_avs_code(code, "GetVersionInfo")

        config = DeviceConfig()
        code = self.libavs.AVS_GetParameter(self.handle,
                                            ctypes.sizeof(config),
                                            _getUIntPointer(ctypes.sizeof(config)),
                                            config)
        assert_avs_code(code, "GetParameter")

        voltage = _getFloatPointer()
        code = self.libavs.AVS_GetAnalogIn(self.handle, 0, voltage)
        assert_avs_code(code, "GetAnalogIn")
        temperature = np.polynomial.polynomial.polyval(voltage.contents.value, config.Temperature_3_m_aFit)

        def decode(value):
            """Return a byte string decoded to ASCII with NULLs stripped."""
            return bytes(value).decode('ascii').split('\x00', 1)[0]

        status = DeviceStatus(n_pixels=self._n_pixels,
                              fpga_version=decode(fpga_version),
                              firmware_version=decode(firmware_version),
                              library_version=decode(library_version),
                              temperature_setpoint=config.TecControl_m_Setpoint,
                              temperature=temperature,
                              config=config if full else None)
        return status

    async def expose(self, duration):
        """Take an exposure with the currently connected spectrograph.

        Returns `None` if the exposure was cancelled.

        Parameters
        ----------
        duration : `float`
            Integration time of the exposure in seconds.

        Returns
        -------
        wavelength : `np.ndarray`
            The 1-d wavelength solution provided by the instrument.
        spectrum : `numpy.ndarray`
            The 1-d spectrum measured by the instrument.

        Raises
        ------
        AvsReturnError
            Raised if there is an error in preparation, measurement, or
            readout from the device.
        """
        config = MeasureConfig()
        config.IntegrationTime = duration * 1000  # seconds->milliseconds
        config.StartPixel = 0
        config.StopPixel = self._n_pixels - 1
        config.NrAverages = 1
        self.log.debug("Preparing %ss measurement.", duration)
        code = self.libavs.AVS_PrepareMeasure(self.handle, config)
        assert_avs_code(code, "PrepareMeasure")

        self.log.info("Beginning %ss measurement.", duration)
        code = self.libavs.AVS_Measure(self.handle, 0, 1)
        assert_avs_code(code, "Measure")

        # get the wavelength range while we wait for the exposure.
        wavelength = (ctypes.c_double * self._n_pixels)()
        code = self.libavs.AVS_GetLambda(self.handle, wavelength)
        assert_avs_code(code, "GetLambda")

        self._expose_task = asyncio.create_task(asyncio.sleep(duration))
        try:
            await self._expose_task
        except asyncio.CancelledError:
            self.log.info("Running exposure cancelled.")
            return None

        data_available = 0
        while data_available != 1:
            self.log.debug("Polling for measurement.")
            data_available = self.libavs.AVS_PollScan(self.handle)
            assert_avs_code(data_available, "PollScan")
            # Avantes docs say not to poll too rapidly, or it will overwhelm
            # the spectrograph CPU. They suggest waiting at least 1 ms.
            await asyncio.sleep(0.001)

        self.log.debug("Reading measured data from spectrograph.")
        time_label = _getUIntPointer()  # NOTE: it's not clear from the docs what this is for
        spectrum = (ctypes.c_double * self._n_pixels)()
        code = self.libavs.AVS_GetScopeData(self.handle, time_label, spectrum)
        assert_avs_code(code, "GetScopeData")
        return np.array(wavelength), np.array(spectrum)

    def stop_exposure(self):
        """Cancel a currently running exposure and reset the spectrograph.

        If there is no currently active exposure, this does nothing.

        Raises
        ------
        AvsReturnError
            Raised if there is an error stopping the exposure on the device.
        """
        if not self._expose_task.done():
            # only cancel a running exposure
            self.log.info("Cancelling running exposure...")
            code = self.libavs.AVS_StopMeasure(self.handle)
            self._expose_task.cancel()
            assert_avs_code(code, "StopMeasure")

    def __del__(self):
        self.disconnect()

    def _configure_ctypes(self):
        """Configure function arguments for communication with libavs.

        Some of the functions in libavs need to have their types and/or
        return values explicitly defined as pointers for python to be able
        to pass them in correctly using the `ctypes` interface. Any C function
        that manipulates a ctypes pointer should have its argument types
        defined here.
        """
        self.libavs.AVS_GetList.argtypes = [ctypes.c_long,
                                            ctypes.POINTER(ctypes.c_uint),
                                            ctypes.POINTER(AvsIdentity)]
        self.libavs.AVS_Activate.argtypes = [ctypes.POINTER(AvsIdentity)]
        self.libavs.AVS_GetNumPixels.argtypes = [ctypes.c_long,
                                                 ctypes.POINTER(ctypes.c_ushort)]
        self.libavs.AVS_GetParameter.argtypes = [ctypes.c_long,
                                                 ctypes.c_uint,
                                                 ctypes.POINTER(ctypes.c_uint),
                                                 ctypes.POINTER(DeviceConfig)]
        self.libavs.AVS_GetVersionInfo.argtypes = [ctypes.c_long,
                                                   ctypes.POINTER(ctypes.c_ubyte),
                                                   ctypes.POINTER(ctypes.c_ubyte),
                                                   ctypes.POINTER(ctypes.c_ubyte)]
        self.libavs.AVS_GetAnalogIn.argtypes = [ctypes.c_long,
                                                ctypes.c_ubyte,
                                                ctypes.POINTER(ctypes.c_float)]
        self.libavs.AVS_PrepareMeasure.argtypes = [ctypes.c_long,
                                                   ctypes.POINTER(MeasureConfig)]
        # Measure's second argument is the callback function pointer, but we
        # aren't using callbacks here, so it will always be NULL==0.
        self.libavs.AVS_Measure.argtypes = [ctypes.c_long,
                                            ctypes.c_int,
                                            ctypes.c_short]
        self.libavs.AVS_GetLambda.argtypes = [ctypes.c_long,
                                              ctypes.POINTER(ctypes.c_double)]


# size of these character fields in bytes
AVS_USER_ID_LEN = 64
AVS_SERIAL_LEN = 10


class AvsIdentity(ctypes.Structure):
    """Python structure to represent the `AvsIdentityType` C struct."""
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
                ("StandAlone_m_Meas_m_DynamicDarkCorrection_m_Enable", ctypes.c_uint8),
                ("StandAlone_m_Meas_m_DynamicDarkCorrection_m_ForgetPercentage", ctypes.c_uint8),
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
        def to_str(value):
            """Try to unroll ctype arrays."""
            try:
                return str([x for x in value])
            except TypeError:
                return str(value)

        too_long = ["Irradiance_m_IntensityCalib_m_aCalibConvers",
                    "Reflectance_m_aCalibConvers",
                    "SpectrumCorrect",
                    "Reserved",
                    "OemData"]
        attrs = ', '.join(f"{x[0]}={to_str(getattr(self, x[0]))}" for x in self._fields_
                          if x[0] not in too_long)
        return f"DeviceConfigType({attrs})"


class MeasureConfig(ctypes.Structure):
    _pack_ = 1
    _fields_ = [("StartPixel", ctypes.c_uint16),
                ("StopPixel", ctypes.c_uint16),
                ("IntegrationTime", ctypes.c_float),  # milliseconds
                ("IntegrationDelay", ctypes.c_uint32),  # internal FGPA clock cycle
                ("NrAverages", ctypes.c_uint32),
                ("DynamicDarkCorrection_Enable", ctypes.c_uint8),
                ("DynamicDarkCorrection_ForgetPercentage", ctypes.c_uint8),
                ("Smoothing_SmoothPix", ctypes.c_uint16),
                ("Smoothing_SmoothModel", ctypes.c_uint8),
                ("SaturationDetection", ctypes.c_uint8),
                ("Trigger_Mode", ctypes.c_uint8),
                ("Trigger_Source", ctypes.c_uint8),
                ("Trigger_SourceType", ctypes.c_uint8),
                ("Control_StrobeControl", ctypes.c_uint16),
                ("Control_LaserDelay", ctypes.c_uint32),
                ("Control_LaserWidth", ctypes.c_uint32),
                ("Control_LaserWaveLength", ctypes.c_float),
                ("Control_StoreToRam", ctypes.c_uint16)]

    def __repr__(self):
        attrs = ', '.join(f"{x[0]}={getattr(self, x[0])}" for x in self._fields_)
        return f"MeasureConfig({attrs})"


@enum.unique
class AvsReturnCode(enum.IntEnum):
    """These codes were taken from avaspec.h and should match the code list in
    section 3.6.1 "Return Value Constants" (page 44) of the "Avantes Linux
    Library Manual" PDF version 9.6.0.0.
    """
    success = 0
    ERR_INVALID_PARAMETER = -1
    ERR_OPERATION_NOT_SUPPORTED = -2
    ERR_DEVICE_NOT_FOUND = -3
    ERR_INVALID_DEVICE_ID = -4
    ERR_OPERATION_PENDING = -5
    ERR_TIMEOUT = -6
    ERR_INVALID_PASSWORD = -7
    ERR_INVALID_MEAS_DATA = -8
    ERR_INVALID_SIZE = -9
    ERR_INVALID_PIXEL_RANGE = -10
    ERR_INVALID_INT_TIME = -11
    ERR_INVALID_COMBINATION = -12
    ERR_INVALID_CONFIGURATION = -13
    ERR_NO_MEAS_BUFFER_AVAIL = -14
    ERR_UNKNOWN = -15
    ERR_COMMUNICATION = -16
    ERR_NO_SPECTRA_IN_RAM = -17
    ERR_INVALID_DLL_VERSION = -18
    ERR_NO_MEMORY = -19
    ERR_DLL_INITIALISATION = -20
    ERR_INVALID_STATE = -21
    ERR_INVALID_REPLY = -22
    ERR_ACCESS = -24
    # Return error codes; DeviceData check
    ERR_INVALID_PARAMETER_NR_PIXELS = -100
    ERR_INVALID_PARAMETER_ADC_GAIN = -101
    ERR_INVALID_PARAMETER_ADC_OFFSET = -102
    # Return error codes; PrepareMeasurement check
    ERR_INVALID_MEASPARAM_AVG_SAT2 = -110
    ERR_INVALID_MEASPARAM_AVG_RAM = -111
    ERR_INVALID_MEASPARAM_SYNC_RAM = -112
    ERR_INVALID_MEASPARAM_LEVEL_RAM = -113
    ERR_INVALID_MEASPARAM_SAT2_RAM = -114
    ERR_INVALID_MEASPARAM_FWVER_RAM = -115
    ERR_INVALID_MEASPARAM_DYNDARK = -116
    # Return error codes; SetSensitivityMode check
    ERR_NOT_SUPPORTED_BY_SENSOR_TYPE = -120
    ERR_NOT_SUPPORTED_BY_FW_VER = -121
    ERR_NOT_SUPPORTED_BY_FPGA_VER = -122
    # Return error codes; SuppressStrayLight check
    ERR_SL_CALIBRATION_NOT_AVAILABLE = -140
    ERR_SL_STARTPIXEL_NOT_IN_RANGE = -141
    ERR_SL_ENDPIXEL_NOT_IN_RANGE = -142
    ERR_SL_STARTPIX_GT_ENDPIX = -143
    ERR_SL_MFACTOR_OUT_OF_RANGE = -144

    invalidHandle = 1000


@dataclasses.dataclass
class DeviceStatus:
    """The current status of the connected spectrograph."""
    n_pixels: int
    """The number of pixels in the instrument."""
    fpga_version: str
    """The FPGA software version."""
    firmware_version: str
    """The microcontroller software version."""
    library_version: str
    """The AvaSpec Library software version."""
    temperature_setpoint: float
    """The detector temperature set point (degrees Celsius)."""
    temperature: float
    """The temperature at the optical bench thermistor (degrees Celsius)."""
    config: DeviceConfig = None
    """The full DeviceConfig structure."""


def _getUIntPointer(value=0):
    """Return a pointer to a ctypes unsigned int."""
    return ctypes.POINTER(ctypes.c_uint)(ctypes.c_uint(value))


def _getUShortPointer(value=0):
    """Return a pointer to a ctypes unsigned short."""
    return ctypes.POINTER(ctypes.c_ushort)(ctypes.c_ushort(value))


def _getFloatPointer(value=0):
    """Return a pointer to a ctypes 32-bit float."""
    return ctypes.POINTER(ctypes.c_float)(ctypes.c_float(value))


def _getAvsIdentityArrayPointer(count):
    """Return a pointer to an arry of `AvsIdentity`."""
    return (AvsIdentity * count)()
