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

from lsst.ts.FiberSpectrograph import fibspec, FiberSpectrograph


class TestFiberSpectrograph(unittest.TestCase):
    """Tests of the python API for the Avantes AvaSpec-ULS-RS-TEC.
    """
    def setUp(self):
        """This setUp configures the mock for a "no error conditions" use case,
        with all methods behaving as if one device is connected and behaving.
        """
        self.n_devices = 1  # Pretend one device is connected
        self.serial_number = 123456789
        self.handle = 314159

        patcher = unittest.mock.patch("ctypes.CDLL")
        self.patch = patcher.start()
        self.addCleanup(patcher.stop)

        name = b"Fake Spectrograph"
        # DeviceStatus (char): 0=unknown, 1=available, 2=in use by this,
        # 3=in use by other, >3 = irrelevant to USB
        status = 0x01
        self.id0 = fibspec.AvsIdentityType(bytes(str(self.serial_number), "ascii"), name, status)

        def mock_getList(a_listSize, a_pRequiredSize, a_pList):
            """`AVS_GetList` either fills pRequiredSize or pList, depending
            on whether listSize is 0, or the number of devices."""
            if a_listSize == 0:
                a_pRequiredSize[0] = self.n_devices * fibspec.AVS_IDENTITY_SIZE
            else:
                a_pList[0] = self.id0
            return self.n_devices

        def mock_getParameter(handle, a_Size, a_pRequiredSize, a_pData):
            """`AVS_GetParameter` either fills pRequiredSize or pData,
            depending on whether Size is 0, or the number of devices."""
            if a_Size == 0:
                a_pRequiredSize[0] = self.n_devices * fibspec.DEVICE_CONFIG_SIZE
            else:
                config = fibspec.DeviceConfigType()
                a_pData[0] = config
            return self.n_devices

        # successful init() and updateUSBDevices() return the number of devices
        self.patch.return_value.AVS_Init.return_value = self.n_devices
        self.patch.return_value.AVS_UpdateUSBDevices.return_value = self.n_devices

        self.patch.return_value.AVS_GetList.side_effect = mock_getList
        self.patch.return_value.AVS_GetParameter.side_effect = mock_getParameter

        # successful activate() returns the handle of the connected device
        self.patch.return_value.AVS_Activate.return_value = self.handle
        # successful disconnect() returns True
        self.patch.return_value.AVS_Deactivate.return_value = True

    def test_connect(self):
        """Test connecting to the first device."""
        fiber_spec = FiberSpectrograph()
        self.patch.return_value.AVS_UpdateUSBDevices.assert_called_once()
        self.patch.return_value.AVS_GetList.assert_called()
        self.patch.return_value.AVS_Activate.assert_called_with(self.id0)
        self.assertEqual(fiber_spec.device, self.id0)

    def test_connect_serial_number(self):
        """Test connecting to a device with a specific serial number."""
        serial_number = 54321
        self.n_devices = 2
        id1 = fibspec.AvsIdentityType(bytes(str(serial_number), "ascii"), b"Fake Spectrograph 2", 1)

        def mock_getList(a_listSize, a_pRequiredSize, a_pList):
            """Pretend that two devices are connected."""
            if a_listSize == 0:
                a_pRequiredSize[0] = self.n_devices * fibspec.AVS_IDENTITY_SIZE
            else:
                a_pList[0] = self.id0
                a_pList[1] = id1
            return self.n_devices

        self.patch.return_value.AVS_GetList.side_effect = mock_getList
        self.patch.return_value.AVS_UpdateUSBDevices.return_value = self.n_devices

        fiber_spec = FiberSpectrograph(serial_number=serial_number)
        self.patch.return_value.AVS_UpdateUSBDevices.assert_called_once()
        self.patch.return_value.AVS_GetList.assert_called()
        self.patch.return_value.AVS_Activate.assert_called_with(id1)
        self.assertEqual(fiber_spec.device, id1)

    def test_connect_no_serial_number_two_devices_fails(self):
        serial_number = 54321
        self.n_devices = 2
        id1 = fibspec.AvsIdentityType(bytes(str(serial_number), "ascii"), b"Fake Spectrograph 2", 1)

        def mock_getList(a_listSize, a_pRequiredSize, a_pList):
            """Pretend that two devices are connected."""
            if a_listSize == 0:
                a_pRequiredSize[0] = self.n_devices * fibspec.AVS_IDENTITY_SIZE
            else:
                a_pList[0] = self.id0
                a_pList[1] = id1
            return self.n_devices

        self.patch.return_value.AVS_GetList.side_effect = mock_getList
        self.patch.return_value.AVS_UpdateUSBDevices.return_value = self.n_devices

        msg = "Multiple devices found, but no serial number specified. Attached devices: "
        with self.assertRaisesRegex(RuntimeError, msg):
            FiberSpectrograph()

    def test_connect_bad_serial_number_fails(self):
        """Test that connect raises an exception if the requested device does
        not exist.
        """
        serial_number = 54321

        with self.assertRaises(LookupError):
            FiberSpectrograph(serial_number=serial_number)
        self.patch.return_value.AVS_UpdateUSBDevices.assert_called_once()
        self.patch.return_value.AVS_GetList.assert_called()
        self.patch.return_value.AVS_Activate.assert_not_called()

    def test_connect_bad_handle_fails(self):
        """Test that connect raises an exception if the device cannot be
        activated.
        """
        self.patch.return_value.AVS_Activate.return_value = fibspec.AVS.INVALID_AVS_HANDLE_VALUE

        with self.assertRaises(RuntimeError):
            FiberSpectrograph()
        self.patch.return_value.AVS_UpdateUSBDevices.assert_called_once()
        self.patch.return_value.AVS_GetList.assert_called()
        self.patch.return_value.AVS_Activate.assert_called_once()

    def test_disconnect(self):
        """Test a successful USB disconnect command."""
        fiber_spec = FiberSpectrograph()
        fiber_spec.disconnect()
        self.patch.return_value.AVS_Deactivate.assert_called_once_with(self.handle)

    def test_disconnect_fails_logged(self):
        """Test that a "failed" Deactivate emits an error."""
        self.patch.return_value.AVS_Deactivate.return_value = False
        fiber_spec = FiberSpectrograph()
        with self.assertLogs(fiber_spec.log, "ERROR"):
            fiber_spec.disconnect()
        self.patch.return_value.AVS_Deactivate.assert_called_once_with(self.handle)

    def test_disconnect_on_delete(self):
        """Test that the connection is closed if the object is deleted."""
        fiber_spec = FiberSpectrograph()
        del fiber_spec
        self.patch.return_value.AVS_Deactivate.assert_called_once_with(self.handle)


if __name__ == "__main__":
    unittest.main()
