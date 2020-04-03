# This file is part of ts_FiberSpectrograph.
#
# Developed for the LSST Telescope and Site Systems.
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

"""A unittest.mock-based simulator for an Avantes spectrograph, useable
in both tests and as an instrument simulator for a CSC.
"""

__all__ = ["AvsSimulator"]

import unittest.mock

import numpy as np

from . import constants
from .avsFiberSpectrograph import AvsIdentity, AvsDeviceStatus


class AvsSimulator:
    """Mock a libavs Avantes spectrograph connection; mocks enough of the
    ``AVS_*`` C free functions from ``libavs.0.2.0`` to allow connecting and
    disconnecting, getting status, and starting/stopping exposures.

    This configures the mock for a "no error conditions" use case,
    with all methods behaving as if one device is connected and behaving.
    """

    def __init__(self):
        self.mock = None

        # This will be passed into the patcher to configure the mock.
        config = dict()

        # Pretend one device is connected: the red spectrograph
        self.n_devices = 1
        self.serial_number = constants.SERIAL_NUMBERS[constants.SalIndex.RED]
        self.handle = 314159

        name = b"Fake Spectrograph"
        status = AvsDeviceStatus.USB_AVAILABLE.value
        self.id0 = AvsIdentity(bytes(str(self.serial_number), "ascii"), name, status)

        def mock_getList(a_listSize, a_pRequiredSize, a_pList):
            """Pretend only one device is connected, and that the correct
            amount of space was allocated for the list."""
            a_pList[0] = self.id0
            return self.n_devices

        config["return_value.AVS_GetList.side_effect"] = mock_getList

        # Have the number of pixels, and temperature values match the real
        # device, so that users aren't confused by simulation telemetry.
        self.n_pixels = 2048
        self.temperature_setpoint = 5
        # thermistor voltage is converted to temperature via a polynomial:
        # these coefficients should result in a temperature of 5.0
        self.tec_coefficients = np.array((1, 2, 0, 0.0, 0), dtype=np.float32)
        self.tec_voltage = 2
        self.temperature = sum(
            coeff * self.tec_voltage ** i
            for i, coeff in enumerate(self.tec_coefficients)
        )

        def mock_getParameter(handle, a_Size, a_pRequiredSize, config):
            """Assume a_pData has the correct amount of space allocated."""
            config.Detector_m_NrPixels = self.n_pixels
            config.TecControl_m_Setpoint = self.temperature_setpoint
            config.Temperature_3_m_aFit[:] = self.tec_coefficients
            return 0

        config["return_value.AVS_GetParameter.side_effect"] = mock_getParameter

        self.fpga_version = "fpga12345678901"
        self.firmware_version = "firmware123456"
        self.library_version = "library123456"

        def mock_getVersionInfo(
            handle, a_pFPGAVersion, a_pFirmwareVersion, a_pLibVersion
        ):
            a_pFPGAVersion[:15] = self.fpga_version.encode("ascii")
            a_pFirmwareVersion[:14] = self.firmware_version.encode("ascii")
            a_pLibVersion[:13] = self.library_version.encode("ascii")
            return 0

        config["return_value.AVS_GetVersionInfo.side_effect"] = mock_getVersionInfo

        def mock_getAnalogIn(handle, a_AnalogInId, a_pAnalogIn):
            """Return a fake temperature measurement."""
            if a_AnalogInId == 0:
                a_pAnalogIn.contents.value = self.tec_voltage
            return 0

        config["return_value.AVS_GetAnalogIn.side_effect"] = mock_getAnalogIn

        def mock_getNumPixels(handle, a_pNumPixels):
            a_pNumPixels.contents.value = self.n_pixels
            return 0

        self.wavelength = np.arange(0, self.n_pixels)
        config["return_value.AVS_GetNumPixels.side_effect"] = mock_getNumPixels

        def mock_getLambda(handle, a_pWavelength):
            a_pWavelength[:] = self.wavelength
            return 0

        config["return_value.AVS_GetLambda.side_effect"] = mock_getLambda

        # successful init() and updateUSBDevices() return the number of devices
        config["return_value.AVS_Init.return_value"] = self.n_devices
        config["return_value.AVS_UpdateUSBDevices.return_value"] = self.n_devices

        # successful activate() returns the handle of the connected device
        config["return_value.AVS_Activate.return_value"] = self.handle
        # successful disconnect() returns True
        config["return_value.AVS_Deactivate.return_value"] = True

        self.measure_config_sent = None

        def mock_prepareMeasure(handle, a_pMeasConfig):
            """Save the MeasureConfig input for checking against later."""
            self.measure_config_sent = a_pMeasConfig
            return 0

        config["return_value.AVS_PrepareMeasure.side_effect"] = mock_prepareMeasure

        # Measure doesn't have any obvious effects.
        config["return_value.AVS_Measure.return_value"] = 0

        # Require four polls of the device before a measurement is ready
        config["return_value.AVS_PollScan.side_effect"] = [0, 0, 0, 1]

        self.spectrum = np.arange(0, self.n_pixels) * 2

        def mock_getScopeData(handle, a_pTimeLabel, a_pSpectrum):
            a_pSpectrum[:] = self.spectrum
            return 0

        config["return_value.AVS_GetScopeData.side_effect"] = mock_getScopeData

        # StopMeasure doesn't have any obvious effects.
        config["return_value.AVS_StopMeasure.return_value"] = 0

        self.patcher = unittest.mock.patch("ctypes.CDLL", **config)

    def start(self, testCase=None):
        """Start the simulator by patching the spectrograph library.

        If the patch has already been started, just return the running mock.

        Parameters
        ----------
        testCase : `unittest.TestCase`, optional
            A test to add a cleanup stage to, to stop the patcher.

        Returns
        -------
        mock : `unittest.mock.Mock`
            The newly created libavs mock.
        """
        if self.mock is None:
            self.mock = self.patcher.start()

        if testCase is not None:
            testCase.addCleanup(self.stop)

        return self.mock

    def stop(self):
        """Disable the patched mock library."""
        # We have to check that the patch has been `start`ed, otherwise
        # `stop()` will raise an exception.
        # Note, this is fixed in py3.8: https://bugs.python.org/issue36366
        if self.mock is not None:
            self.patcher.stop()
        self.mock = None
