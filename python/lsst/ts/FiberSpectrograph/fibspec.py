import ctypes
import enum
import struct

AVS_SERIAL_LEN = 10
USER_ID_LEN = 64
WM_MEAS_READY = 0x401
AVS_IDENTITY_SIZE = 75
DEVICE_CONFIG_SIZE = 63484


class AVAReturnCodes(enum.Enum):
    Success = 0
    InvalidParameter = -1
    OperationNotSupported = -2
    DeviceNotFound = -3
    InvalidDeviceId = -4
    OperationPending = -5
    Timeout = -6
    InvalidPassword = -7
    InvalidMeasurementData = -8
    InvalidSize = -9
    InvalidPixelRange = -10
    InvalidIntegrationTime = -11
    InvalidCombination = -12
    InvalidConfiguration = -13
    NoMeasurementBufferAvailable = -14
    Unknown = -15
    CommunicationError = -16
    NoSpectraInRam = -17
    InvalidDLLVersion = -18
    NoMemory = -19
    DllInitialisationError = -20
    InvalidState = -21
    InvalidReply = -22
    ConnectionFailure = -16
    AccessError = 24
    InvalidParameterNumberPixels = -100
    InvalidParameterADCGain = -101
    InvalidParameterADCOffset = -102
    InvalidMeasurementParameterAvgSat2 = -110
    InvalidMeasurementParameterAvgRam = -111
    InvalidMeasurementParameterSyncRam = -112
    # You can copy the rest from the .h file at the very end if needed


class AvsIdentityType(ctypes.Structure):
    _pack_ = 1
    _fields_ = [("SerialNumber", ctypes.c_char * AVS_SERIAL_LEN),
                ("UserFriendlyName", ctypes.c_char * USER_ID_LEN),
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


class MeasConfigType(ctypes.Structure):
    _pack_ = 1
    _fields_ = [("m_StartPixel", ctypes.c_uint16),
                ("m_StopPixel", ctypes.c_uint16),
                ("m_IntegrationTime", ctypes.c_float),
                ("m_IntegrationDelay", ctypes.c_uint32),
                ("m_NrAverages", ctypes.c_uint32),
                ("m_CorDynDark_m_Enable", ctypes.c_uint8),
                ("m_CorDynDark_m_ForgetPercentage", ctypes.c_uint8),
                ("m_Smoothing_m_SmoothPix", ctypes.c_uint16),
                ("m_Smoothing_m_SmoothModel", ctypes.c_uint8),
                ("m_SaturationDetection", ctypes.c_uint8),
                ("m_Trigger_m_Mode", ctypes.c_uint8),
                ("m_Trigger_m_Source", ctypes.c_uint8),
                ("m_Trigger_m_SourceType", ctypes.c_uint8),
                ("m_Control_m_StrobeControl", ctypes.c_uint16),
                ("m_Control_m_LaserDelay", ctypes.c_uint32),
                ("m_Control_m_LaserWidth", ctypes.c_uint32),
                ("m_Control_m_LaserWaveLength", ctypes.c_float),
                ("m_Control_m_StoreToRam", ctypes.c_uint16)]


class DeviceConfigType(ctypes.Structure):
    _pack_ = 1
    _fields_ = [("m_Len", ctypes.c_uint16),
                ("m_ConfigVersion", ctypes.c_uint16),
                ("m_aUserFriendlyId", ctypes.c_char * USER_ID_LEN),
                ("m_Detector_m_SensorType", ctypes.c_uint8),
                ("m_Detector_m_NrPixels", ctypes.c_uint16),
                ("m_Detector_m_aFit", ctypes.c_float * 5),
                ("m_Detector_m_NLEnable", ctypes.c_bool),
                ("m_Detector_m_aNLCorrect", ctypes.c_double * 8),
                ("m_Detector_m_aLowNLCounts", ctypes.c_double),
                ("m_Detector_m_aHighNLCounts", ctypes.c_double),
                ("m_Detector_m_Gain", ctypes.c_float * 2),
                ("m_Detector_m_Reserved", ctypes.c_float),
                ("m_Detector_m_Offset", ctypes.c_float * 2),
                ("m_Detector_m_ExtOffset", ctypes.c_float),
                ("m_Detector_m_DefectivePixels", ctypes.c_uint16 * 30),
                ("m_Irradiance_m_IntensityCalib_m_Smoothing_m_SmoothPix", ctypes.c_uint16),
                ("m_Irradiance_m_IntensityCalib_m_Smoothing_m_SmoothModel", ctypes.c_uint8),
                ("m_Irradiance_m_IntensityCalib_m_CalInttime", ctypes.c_float),
                ("m_Irradiance_m_IntensityCalib_m_aCalibConvers", ctypes.c_float * 4096),
                ("m_Irradiance_m_CalibrationType", ctypes.c_uint8),
                ("m_Irradiance_m_FiberDiameter", ctypes.c_uint32),
                ("m_Reflectance_m_Smoothing_m_SmoothPix", ctypes.c_uint16),
                ("m_Reflectance_m_Smoothing_m_SmoothModel", ctypes.c_uint8),
                ("m_Reflectance_m_CalInttime", ctypes.c_float),
                ("m_Reflectance_m_aCalibConvers", ctypes.c_float * 4096),
                ("m_SpectrumCorrect", ctypes.c_float * 4096),
                ("m_StandAlone_m_Enable", ctypes.c_bool),
                ("m_StandAlone_m_Meas_m_StartPixel", ctypes.c_uint16),
                ("m_StandAlone_m_Meas_m_StopPixel", ctypes.c_uint16),
                ("m_StandAlone_m_Meas_m_IntegrationTime", ctypes.c_float),
                ("m_StandAlone_m_Meas_m_IntegrationDelay", ctypes.c_uint32),
                ("m_StandAlone_m_Meas_m_NrAverages", ctypes.c_uint32),
                ("m_StandAlone_m_Meas_m_CorDynDark_m_Enable", ctypes.c_uint8),
                ("m_StandAlone_m_Meas_m_CorDynDark_m_ForgetPercentage", ctypes.c_uint8),
                ("m_StandAlone_m_Meas_m_Smoothing_m_SmoothPix", ctypes.c_uint16),
                ("m_StandAlone_m_Meas_m_Smoothing_m_SmoothModel", ctypes.c_uint8),
                ("m_StandAlone_m_Meas_m_SaturationDetection", ctypes.c_uint8),
                ("m_StandAlone_m_Meas_m_Trigger_m_Mode", ctypes.c_uint8),
                ("m_StandAlone_m_Meas_m_Trigger_m_Source", ctypes.c_uint8),
                ("m_StandAlone_m_Meas_m_Trigger_m_SourceType", ctypes.c_uint8),
                ("m_StandAlone_m_Meas_m_Control_m_StrobeControl", ctypes.c_uint16),
                ("m_StandAlone_m_Meas_m_Control_m_LaserDelay", ctypes.c_uint32),
                ("m_StandAlone_m_Meas_m_Control_m_LaserWidth", ctypes.c_uint32),
                ("m_StandAlone_m_Meas_m_Control_m_LaserWaveLength", ctypes.c_float),
                ("m_StandAlone_m_Meas_m_Control_m_StoreToRam", ctypes.c_uint16),
                ("m_StandAlone_m_Nmsr", ctypes.c_int16),
                ("m_StandAlone_m_Reserved", ctypes.c_uint8 * 12),
                ("m_Temperature_1_m_aFit", ctypes.c_float * 5),
                ("m_Temperature_2_m_aFit", ctypes.c_float * 5),
                ("m_Temperature_3_m_aFit", ctypes.c_float * 5),
                ("m_TecControl_m_Enable", ctypes.c_bool),
                ("m_TecControl_m_Setpoint", ctypes.c_float),
                ("m_TecControl_m_aFit", ctypes.c_float * 2),
                ("m_ProcessControl_m_AnalogLow", ctypes.c_float * 2),
                ("m_ProcessControl_m_AnalogHigh", ctypes.c_float * 2),
                ("m_ProcessControl_m_DigitalLow", ctypes.c_float * 10),
                ("m_ProcessControl_m_DigitalHigh", ctypes.c_float * 10),
                ("m_EthernetSettings_m_IpAddr", ctypes.c_uint32),
                ("m_EthernetSettings_m_NetMask", ctypes.c_uint32),
                ("m_EthernetSettings_m_Gateway", ctypes.c_uint32),
                ("m_EthernetSettings_m_DhcpEnabled", ctypes.c_uint8),
                ("m_EthernetSettings_m_TcpPort", ctypes.c_uint16),
                ("m_EthernetSettings_m_LinkStatus", ctypes.c_uint8),
                ("m_Reserved", ctypes.c_uint8 * 9720),
                ("m_OemData", ctypes.c_uint8 * 4096)]


class AVS:
    INVALID_AVS_HANDLE_VALUE = 1000

    def __init__(self):
        self.lib = ctypes.CDLL("/usr/local/lib/libavs.so.0.2.0")

        # DLL_INT AVS_Init( short a_Port );
        self.lib.AVS_Init.argtypes = [ctypes.c_short]
        self.lib.AVS_Init.restype = ctypes.c_int

        # DLL_INT AVS_Done( void );
        self.lib.AVS_Done.argtypes = []
        self.lib.AVS_Done.restype = None

        # DLL_INT AVS_GetNrOfDevices(void);
        self.lib.AVS_GetNrOfDevices.argtypes = []
        self.lib.AVS_GetNrOfDevices.restype = ctypes.c_int

        # DLL_INT AVS_GetList(unsigned int a_ListSize, unsigned int*
        # a_pRequiredSize,AvsIdentityType* a_pList);
        self.lib.AVS_GetList.argtypes = [
            ctypes.c_int, ctypes.POINTER(ctypes.c_uint), ctypes.POINTER(AvsIdentityType)]
        self.lib.AVS_GetList.restype = ctypes.c_int

        # DLL_INT AVS_GetParameter( AvsHandle a_hDevice,unsigned int a_Size,
        # unsigned int* a_pRequiredSize,DeviceConfigType* a_pDeviceParm);
        self.lib.AVS_GetParameter.argtypes = [
            ctypes.c_int, ctypes.c_uint, ctypes.POINTER(ctypes.c_uint), ctypes.POINTER(DeviceConfigType)]
        self.lib.AVS_GetParameter.restype = ctypes.c_int

        # DLL_INT AVS_UpdateUSBDevices(void);
        self.lib.AVS_UpdateUSBDevices.argtypes = []
        self.lib.AVS_UpdateUSBDevices.restype = ctypes.c_int

        # DLL_INT AVS_GetNumPixels( AvsHandle a_hDevice, unsigned short*
        # a_pNumPixels );
        self.lib.AVS_GetNumPixels.argtypes = [ctypes.c_int, ctypes.POINTER(ctypes.c_ushort)]
        self.lib.AVS_GetNumPixels.restype = ctypes.c_int

        # DLL_INT AVS_GetLambda( AvsHandle a_hDevice, double* a_pWaveLength);
        self.lib.AVS_GetLambda.argtypes = [ctypes.c_int, ctypes.POINTER(ctypes.c_double)]
        self.lib.AVS_GetLambda.restype = ctypes.c_int

        # DLL_INT AVS_GetScopeData( AvsHandle a_hDevice,
        # unsigned int* a_pTimeLabel, double* a_pSpectrum );
        self.lib.AVS_GetScopeData.argtypes = [
            ctypes.c_int, ctypes.POINTER(ctypes.c_uint), ctypes.POINTER(ctypes.c_double)]
        self.lib.AVS_GetScopeData.restype = ctypes.c_int

        # DLL_INT AVS_PrepareMeasure( AvsHandle a_hDevice,
        # MeasConfigType* a_pMeasConfig );
        self.lib.AVS_PrepareMeasure.argtypes = [ctypes.c_int, ctypes.POINTER(MeasConfigType)]
        self.lib.AVS_PrepareMeasure.restype = ctypes.c_int

        # DLL_AvsHandle AVS_Activate( AvsIdentityType* a_pDeviceId );
        self.lib.AVS_Activate.argtypes = [ctypes.POINTER(AvsIdentityType)]
        self.lib.AVS_Activate.restype = ctypes.c_int

        # DLL_INT AVS_PollScan( AvsHandle a_hDevice );
        self.lib.AVS_PollScan.argtypes = [ctypes.c_int]
        self.lib.AVS_PollScan.restype = ctypes.c_int

        # DLL_INT AVS_Measure( AvsHandle a_hDevice, void *a_hWnd, short a_Nmsr)
        self.lib.AVS_Measure.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_short]
        self.lib.AVS_Measure.restype = ctypes.c_int

        # DLL_INT AVS_StopMeasure( AvsHandle a_hDevice );
        self.lib.AVS_StopMeasure.argtypes = [ctypes.c_int]
        self.lib.AVS_StopMeasure.restype = ctypes.c_int

        # DLL_INT AVS_SetParameter( AvsHandle a_hDevice,
        # DeviceConfigType* a_pDeviceParm);
        self.lib.AVS_SetParameter.argtypes = [ctypes.c_int, ctypes.POINTER(DeviceConfigType)]
        self.lib.AVS_SetParameter.restype = ctypes.c_int

        # DLL_INT AVS_UseHighResAdc( AvsHandle a_hDevice, bool a_Enable);
        self.lib.AVS_UseHighResAdc.argtypes = [ctypes.c_int, ctypes.c_bool]
        self.lib.AVS_UseHighResAdc.restype = ctypes.c_int

        # Define some pointer types
        self._ushortPointer = ctypes.POINTER(ctypes.c_ushort)
        self._uintPointer = ctypes.POINTER(ctypes.c_uint)
        self._doublePointer = ctypes.POINTER(ctypes.c_double)
        self._avsIdentityTypePointer = ctypes.POINTER(AvsIdentityType)
        self._deviceConfigTypePointer = ctypes.POINTER(DeviceConfigType)

    def init(self, port):
        # DLL_INT AVS_Init( short a_Port );
        return self.lib.AVS_Init(port)

    def done(self):
        # DLL_INT AVS_Done( void );
        return self.lib.AVS_Done()

    def getNumberOfDevices(self):
        # DLL_INT AVS_GetNrOfDevices(void);
        return self.lib.AVS_GetNrOfDevices()

    def updateUSBDevices(self):
        # DLL_INT AVS_UpdateUSBDevices(void);
        return self.lib.AVS_UpdateUSBDevices()

    def getNumberOfPixels(self, handle):
        # DLL_INT AVS_GetNumPixels( AvsHandle a_hDevice,
        # unsigned short* a_pNumPixels );
        numberOfPixels = self._getUShortPointer()
        result = self.lib.AVS_GetNumPixels(handle, numberOfPixels)
        return result, numberOfPixels[0]

    def useHighResADC(self, handle, boolVal):
        # DLL_INT AVS_UseHighResAdc( AvsHandle a_hDevice, bool a_Enable);
        result = self.lib.AVS_UseHighResAdc(handle, boolVal)
        return result

    def getList(self):
        # DLL_INT AVS_GetList(unsigned int a_ListSize,
        # unsigned int* a_pRequiredSize,AvsIdentityType* a_pList);
        requiredSize = self._getUIntPointer()
        resultList = self._getAvsIdentityTypeArrayPointer(0)
        # Get the number of AvsIdentityTypes that are required
        result = self.lib.AVS_GetList(0, requiredSize, resultList)
        count = int(requiredSize[0] / AVS_IDENTITY_SIZE)
        # Get the AvsIdentityType list using the number we just got
        resultList = self._getAvsIdentityTypeArrayPointer(count)
        result = self.lib.AVS_GetList(requiredSize[0], requiredSize, resultList)
        return result, [x for x in resultList]

    def activate(self, deviceID):
        # DLL_AvsHandle AVS_Activate( AvsIdentityType* a_pDeviceId );
        result = self.lib.AVS_Activate(deviceID)
        return result

    def pollScan(self, handle):
        # DLL_INT AVS_PollScan( AvsHandle a_hDevice );
        result = self.lib.AVS_PollScan(handle)
        return result

    def measure(self, handle, nummeas=1):
        result = self.lib.AVS_Measure(handle, 0, nummeas)
        return result

    def stopMeasure(self, handle):
        # DLL_INT AVS_StopMeasure( AvsHandle a_hDevice );
        result = self.lib.AVS_StopMeasure(handle)
        return result

    def prepareMeasure(self, handle, measConfig):
        # DLL_INT AVS_PrepareMeasure(AvsHandle a_hDevice,
        # MeasConfigType* a_pMeasConfig);
        result = self.lib.AVS_PrepareMeasure(handle, measConfig)
        # result = self.lib.AVS_PrepareMeasure(handle,
        # ctypes.byref(measConfig))
        return result, measConfig

    def getScopeData(self, handle, numberOfPixels=None):
        # DLL_INT AVS_GetScopeData( AvsHandle a_hDevice,
        # unsigned int* a_pTimeLabel, double* a_pSpectrum );
        if (numberOfPixels is None):
            result, tempNumberOfPixels = self.getNumberOfPixels(handle)
            if result == AVAReturnCodes.Success:
                numberOfPixels = tempNumberOfPixels
            else:
                raise "Bad number of pixels"
        timelabel = self._getUIntPointer(numberOfPixels)
        spectrum = self._getDoubleArrayPointer(numberOfPixels)
        result = self.lib.AVS_GetScopeData(handle, timelabel, spectrum)
        if (result == 0):
            intensity = [spectrum[counter] for counter in range(0, numberOfPixels)]
            return result, timelabel[0], intensity
        else:
            # ERROR handling will be updated this is just a placeholder
            raise RuntimeError("There is something wrong. The error code is %d." % result)

    def getParameter(self, handle, size):
        # DLL_INT AVS_GetParameter(AvsHandle a_hDevice, unsigned int a_Size,
        # unsigned int* a_pRequiredSize, DeviceConfigType*   a_pDeviceParm);
        requiredSize = self._getUIntPointer()
        deviceConfig = self._getDeviceConfigTypeArrayPointer(0)
        # Get the number of DeviceConfigTypes required
        result = self.lib.AVS_GetParameter(handle, 0, requiredSize, deviceConfig)
        count = int(requiredSize[0] / DEVICE_CONFIG_SIZE)
        # Get the DeviceConfigType list needed for the number of required items
        deviceConfig = self._getDeviceConfigTypeArrayPointer(count)
        result = self.lib.AVS_GetParameter(handle, requiredSize[0], requiredSize, deviceConfig)
        return result, [x for x in deviceConfig]

    def getLambda(self, handle, numberOfPixels=None):
        if (numberOfPixels is None):
            result, tempNumberOfPixels = self.getNumberOfPixels(handle)
            if (result == AVAReturnCodes.Success):
                numberOfPixels = tempNumberOfPixels
            else:
                raise "Bad number of pixels"
        # DLL_INT AVS_GetLambda( AvsHandle a_hDevice, double* a_pWaveLength);
        waveLength = self._getDoubleArrayPointer(numberOfPixels)
        result = self.lib.AVS_GetLambda(handle, waveLength)

        if (result == 0):
            measurement = [waveLength[counter] for counter in range(0, numberOfPixels)]
            return result, measurement
        else:
            # ERROR handling will be updated this is just a placeholder
            raise RuntimeError("There is something wrong. The error code is %d." % result)

    def _getUIntPointer(self, defaultValue=0):
        return self._uintPointer(ctypes.c_uint(defaultValue))

    def _getUShortPointer(self, defaultValue=0):
        return self._ushortPointer(ctypes.c_ushort(defaultValue))

    def _getDoubleArrayPointer(self, size):
        array = (ctypes.c_double * size)()
        return ctypes.cast(array, ctypes.POINTER(ctypes.c_double))

    def _getUIntArrayPointer(self, size):
        array = (ctypes.c_uint * size)()
        return ctypes.cast(array, ctypes.POINTER(ctypes.c_uint))

    def _getDeviceConfigTypeArrayPointer(self, count):
        return (DeviceConfigType * count)()

    def _getAvsIdentityTypeArrayPointer(self, count):
        return (AvsIdentityType * count)()
