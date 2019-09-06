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

import unittest
import unittest.mock

import numpy as np

from lsst.ts.FiberSpectrograph import AvsFiberSpectrograph
from lsst.ts.FiberSpectrograph import AvsReturnCode, AvsReturnError
from lsst.ts.FiberSpectrograph import AvsIdentity
from lsst.ts.FiberSpectrograph import DeviceConfig


class TestFiberSpectrograph(unittest.TestCase):
    """Tests of the python API for the Avantes AvaSpec-ULS-RS-TEC.
    """
    def setUp(self):
        """This setUp configures the mock for a "no error conditions" use case,
        with all methods behaving as if one device is connected and behaving.
        """
        self.n_devices = 1  # Pretend one device is connected
        self.serial_number = "123456789"
        self.handle = 314159

        patcher = unittest.mock.patch("ctypes.CDLL")
        self.patch = patcher.start()
        self.addCleanup(patcher.stop)

        name = b"Fake Spectrograph"
        # DeviceStatus (char): 0=unknown, 1=available, 2=in use by this,
        # 3=in use by other, >3 = irrelevant to USB
        status = 0x01
        self.id0 = AvsIdentity(bytes(str(self.serial_number), "ascii"), name, status)

        def mock_getList(a_listSize, a_pRequiredSize, a_pList):
            """Pretend only one device is connected, and that the correct
            amount of space was allocated for the list."""
            a_pList[0] = self.id0
            return self.n_devices
        self.patch.return_value.AVS_GetList.side_effect = mock_getList

        self.n_pixels = 3141
        self.temperature_setpoint = -273.0
        # thermistor voltage is converted to temperature via a polynomial
        self.tec_coefficients = np.array((12, 34, 56, 78, 90), dtype=np.float32)
        self.tec_voltage = 6.4
        self.temperature = sum(x*self.tec_voltage**i for i, x in enumerate(self.tec_coefficients))

        def mock_getParameter(handle, a_Size, a_pRequiredSize, config):
            """Assume a_pData has the correct amount of space allocated."""
            config.Detector_m_NrPixels = self.n_pixels
            config.TecControl_m_Setpoint = self.temperature_setpoint
            config.Temperature_3_m_aFit[:] = self.tec_coefficients
            return 0

        self.patch.return_value.AVS_GetParameter.side_effect = mock_getParameter

        self.fpga_version = "fpga12345678901"
        self.firmware_version = "firmware123456"
        self.library_version = "library123456"

        def mock_getVersionInfo(handle, a_pFPGAVersion, a_pFirmwareVersion, a_pLibVersion):
            a_pFPGAVersion[:15] = self.fpga_version.encode('ascii')
            a_pFirmwareVersion[:14] = self.firmware_version.encode('ascii')
            a_pLibVersion[:13] = self.library_version.encode('ascii')
            return 0

        self.patch.return_value.AVS_GetVersionInfo.side_effect = mock_getVersionInfo

        def mock_getAnalogIn(handle, a_AnalogInId, a_pAnalogIn):
            """Return a fake temperature measurement."""
            if a_AnalogInId == 0:
                a_pAnalogIn.contents.value = self.tec_voltage
            return 0

        self.patch.return_value.AVS_GetAnalogIn.side_effect = mock_getAnalogIn

        # successful init() and updateUSBDevices() return the number of devices
        self.patch.return_value.AVS_Init.return_value = self.n_devices
        self.patch.return_value.AVS_UpdateUSBDevices.return_value = self.n_devices

        # successful activate() returns the handle of the connected device
        self.patch.return_value.AVS_Activate.return_value = self.handle
        # successful disconnect() returns True
        self.patch.return_value.AVS_Deactivate.return_value = True

    def test_connect(self):
        """Test connecting to the first device."""
        fiber_spec = AvsFiberSpectrograph()
        self.patch.return_value.AVS_UpdateUSBDevices.assert_called_once()
        self.patch.return_value.AVS_GetList.assert_called_once()
        self.patch.return_value.AVS_Activate.assert_called_with(self.id0)
        self.assertEqual(fiber_spec.device, self.id0)

    def test_connect_serial_number(self):
        """Test connecting to a device with a specific serial number."""
        serial_number = "54321"
        self.n_devices = 2
        id1 = AvsIdentity(bytes(str(serial_number), "ascii"), b"Fake Spectrograph 2", 1)

        def mock_getList(a_listSize, a_pRequiredSize, a_pList):
            """Pretend that two devices are connected."""
            a_pList[:] = [self.id0, id1]
            return self.n_devices

        self.patch.return_value.AVS_GetList.side_effect = mock_getList
        self.patch.return_value.AVS_UpdateUSBDevices.return_value = self.n_devices

        fiber_spec = AvsFiberSpectrograph(serial_number=serial_number)
        self.patch.return_value.AVS_UpdateUSBDevices.assert_called_once()
        self.patch.return_value.AVS_GetList.assert_called_once()
        self.patch.return_value.AVS_Activate.assert_called_with(id1)
        self.assertEqual(fiber_spec.device, id1)

    def test_connect_no_serial_number_two_devices_fails(self):
        serial_number = "54321"
        self.n_devices = 2
        id1 = AvsIdentity(bytes(str(serial_number), "ascii"), b"Fake Spectrograph 2", 1)

        def mock_getList(a_listSize, a_pRequiredSize, a_pList):
            """Pretend that two devices are connected."""
            a_pList[0] = self.id0
            a_pList[1] = id1
            return self.n_devices

        self.patch.return_value.AVS_GetList.side_effect = mock_getList
        self.patch.return_value.AVS_UpdateUSBDevices.return_value = self.n_devices

        msg = "Multiple devices found, but no serial number specified. Attached devices: "
        with self.assertRaisesRegex(RuntimeError, msg):
            AvsFiberSpectrograph()
        self.patch.return_value.AVS_UpdateUSBDevices.assert_called_once()
        self.patch.return_value.AVS_GetList.assert_called_once()
        self.patch.return_value.AVS_Activate.assert_not_called()

    def test_connect_bad_serial_number_fails(self):
        """Test that connect raises an exception if the requested device does
        not exist.
        """
        serial_number = "54321"

        with self.assertRaisesRegex(LookupError, f"Device serial number {serial_number} not found"):
            AvsFiberSpectrograph(serial_number=serial_number)
        self.patch.return_value.AVS_UpdateUSBDevices.assert_called_once()
        self.patch.return_value.AVS_GetList.assert_called_once()
        self.patch.return_value.AVS_Activate.assert_not_called()

    def test_connect_bad_handle_fails(self):
        """Test that connect raises an exception if the device cannot be
        activated.
        """
        self.patch.return_value.AVS_Activate.return_value = AvsReturnCode.invalidHandle.value

        with self.assertRaisesRegex(RuntimeError, "Invalid device handle"):
            AvsFiberSpectrograph()
        self.patch.return_value.AVS_UpdateUSBDevices.assert_called_once()
        self.patch.return_value.AVS_GetList.assert_called_once()
        self.patch.return_value.AVS_Activate.assert_called_once()

    def test_connect_invalid_size(self):
        """Test that connect raises if GetList returns "Invalid Size"."""
        self.patch.return_value.AVS_GetList.side_effect = None
        self.patch.return_value.AVS_GetList.return_value = AvsReturnCode.ERR_INVALID_SIZE.value
        with self.assertRaisesRegex(AvsReturnError, "Fatal Error"):
            AvsFiberSpectrograph()
        self.patch.return_value.AVS_UpdateUSBDevices.assert_called_once()
        self.patch.return_value.AVS_GetList.assert_called_once()
        self.patch.return_value.AVS_Activate.assert_not_called()

    def test_connect_other_error(self):
        """Test that connect raises with a message containing the interpreted
        code if GetList returns an error code.
        """
        self.patch.return_value.AVS_GetList.side_effect = None
        self.patch.return_value.AVS_GetList.return_value = AvsReturnCode.ERR_DLL_INITIALISATION.value
        with self.assertRaisesRegex(AvsReturnError, "ERR_DLL_INITIALISATION"):
            AvsFiberSpectrograph()
        self.patch.return_value.AVS_UpdateUSBDevices.assert_called_once()
        self.patch.return_value.AVS_GetList.assert_called_once()
        self.patch.return_value.AVS_Activate.assert_not_called()

    def test_connect_no_devices(self):
        """Test that connect raises if no devices were found."""
        self.patch.return_value.AVS_UpdateUSBDevices.return_value = 0

        with self.assertRaisesRegex(RuntimeError, "No attached USB Avantes devices found"):
            AvsFiberSpectrograph()
        self.patch.return_value.AVS_UpdateUSBDevices.assert_called_once()
        self.patch.return_value.AVS_GetList.assert_not_called()
        self.patch.return_value.AVS_Activate.assert_not_called()

    def test_connect_Activate_fails(self):
        """Test that connect raises if no devices were found."""
        self.patch.return_value.AVS_Activate.return_value = AvsReturnCode.ERR_DLL_INITIALISATION.value

        with self.assertRaisesRegex(AvsReturnError, "Activate"):
            AvsFiberSpectrograph()
        self.patch.return_value.AVS_UpdateUSBDevices.assert_called_once()
        self.patch.return_value.AVS_GetList.assert_called_once()
        self.patch.return_value.AVS_Activate.assert_called_once()

    def test_disconnect(self):
        """Test a successful USB disconnect command."""
        fiber_spec = AvsFiberSpectrograph()
        fiber_spec.disconnect()
        self.patch.return_value.AVS_Deactivate.assert_called_once_with(self.handle)
        self.patch.return_value.AVS_Done.assert_called_once_with()
        self.assertIsNone(fiber_spec.handle)

    def test_disconnect_no_handle(self):
        """Test that we do not attempt to disconnect if there is no device
        handle.
        """
        fiber_spec = AvsFiberSpectrograph()
        fiber_spec.handle = None
        fiber_spec.disconnect()
        self.patch.return_value.AVS_Deactivate.assert_not_called()
        self.patch.return_value.AVS_Done.assert_called_once_with()

    def test_disconnect_bad_handle(self):
        """Do not attempt to disconnect if the device handle is bad.
        """
        fiber_spec = AvsFiberSpectrograph()
        fiber_spec.handle = AvsReturnCode.invalidHandle.value
        fiber_spec.disconnect()
        self.patch.return_value.AVS_Deactivate.assert_not_called()
        self.patch.return_value.AVS_Done.assert_called_once_with()

    def test_disconnect_fails_logged(self):
        """Test that a "failed" Deactivate emits an error."""
        self.patch.return_value.AVS_Deactivate.return_value = False
        fiber_spec = AvsFiberSpectrograph()
        with self.assertLogs(fiber_spec.log, "ERROR"):
            fiber_spec.disconnect()
        self.patch.return_value.AVS_Deactivate.assert_called_once_with(self.handle)
        self.patch.return_value.AVS_Done.assert_called_once_with()

    def test_disconnect_on_delete(self):
        """Test that the connection is closed if the object is deleted."""
        fiber_spec = AvsFiberSpectrograph()
        del fiber_spec
        self.patch.return_value.AVS_Deactivate.assert_called_once_with(self.handle)
        self.patch.return_value.AVS_Done.assert_called_once_with()

    def test_get_status(self):
        spec = AvsFiberSpectrograph()
        status = spec.get_status()
        self.assertEqual(status.fpga_version, self.fpga_version)
        self.assertEqual(status.firmware_version, self.firmware_version)
        self.assertEqual(status.library_version, self.library_version)
        self.assertEqual(status.n_pixels, self.n_pixels)
        self.assertEqual(status.temperature_setpoint, self.temperature_setpoint)
        np.testing.assert_allclose(status.temperature, self.temperature)
        self.assertIsNone(status.config)

        # Check that full=True returns a DeviceConfig instead of None
        # (we're not worried about the contents of it here)
        status = spec.get_status(full=True)
        self.assertIsNotNone(status.config)

    def test_get_status_getVersionInfo_fails(self):
        spec = AvsFiberSpectrograph()
        self.patch.return_value.AVS_GetVersionInfo.side_effect = None
        self.patch.return_value.AVS_GetVersionInfo.return_value = AvsReturnCode.ERR_DEVICE_NOT_FOUND.value
        with self.assertRaisesRegex(AvsReturnError, "GetVersionInfo.*ERR_DEVICE_NOT_FOUND"):
            spec.get_status()

    def test_get_status_getParameter_fails(self):
        spec = AvsFiberSpectrograph()
        self.patch.return_value.AVS_GetParameter.side_effect = None
        self.patch.return_value.AVS_GetParameter.return_value = AvsReturnCode.ERR_INVALID_DEVICE_ID.value
        with self.assertRaisesRegex(AvsReturnError, "GetParameter.*ERR_INVALID_DEVICE_ID"):
            spec.get_status()

    def test_get_status_getAnalogIn_fails(self):
        spec = AvsFiberSpectrograph()
        self.patch.return_value.AVS_GetAnalogIn.side_effect = None
        self.patch.return_value.AVS_GetAnalogIn.return_value = AvsReturnCode.ERR_TIMEOUT.value
        with self.assertRaisesRegex(AvsReturnError, "GetAnalogIn.*ERR_TIMEOUT"):
            spec.get_status()


class TestAvsReturnError(unittest.TestCase):
    """Tests of the string representations of AvsReturnError exceptions."""
    def test_valid_code(self):
        """Test that an valid code results in a useful message."""
        code = -24
        what = "valid test"
        err = AvsReturnError(code, what)
        msg = "Error calling `valid test` with error code <AvsReturnCode.ERR_ACCESS: -24>"
        self.assertIn(msg, repr(err))

    def test_invalid_size(self):
        """Test that the "invalid size" code results in a useful message."""
        code = -9
        what = "invalid size test"
        err = AvsReturnError(code, what)
        msg = f"Fatal Error <AvsReturnCode.ERR_INVALID_SIZE: -9> calling `invalid size test`"
        self.assertIn(msg, repr(err))

    def test_invalid_code(self):
        """Test that an invalid code still results in a useful message."""
        code = -123456321
        what = "invalid code test"
        err = AvsReturnError(code, what)
        msg = f"Unknown Error (-123456321) calling `invalid code test`; Please consult Avantes documentation"
        self.assertIn(msg, repr(err))


class TestDeviceConfig(unittest.TestCase):
    def test_str(self):
        """Test some specific aspects of the (long) string representation."""
        config = DeviceConfig()
        string = str(config)
        self.assertIn("TecControl_m_Enable=False", string)
        self.assertNotIn("SpectrumCorrect", string)
        self.assertNotIn("OemData", string)


if __name__ == "__main__":
    unittest.main()
