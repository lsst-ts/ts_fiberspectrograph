# This file is part of ts_fiberspectrograph.
#
# Developed for Vera C. Rubin Observatory Telescope and Site Systems.
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

import asyncio
import contextlib
import io
import itertools
import logging
import struct
import time
import unittest
import unittest.mock

import astropy.units as u
import numpy as np
import pytest
from lsst.ts.fiberspectrograph import (
    AvsDeviceConfig,
    AvsDeviceStatus,
    AvsFiberSpectrograph,
    AvsIdentity,
    AvsMeasureConfig,
    AvsReturnCode,
    AvsReturnError,
    AvsSimulator,
)
from lsst.ts.fiberspectrograph.avs_fiber_spectrograph import MAX_DURATION, MIN_DURATION


class TestAvsFiberSpectrograph(unittest.IsolatedAsyncioTestCase):
    """Tests of the python API for the Avantes AvaSpec-ULS spectrograph."""

    def setUp(self):
        """This setUp configures the mock for a "no error conditions" use case,
        with all methods behaving as if one device is connected and behaving.
        """
        patcher = AvsSimulator()
        self.patch = patcher.start(testCase=self)

        # extract some properties of the patcher to more easily test against
        self.handle = patcher.handle
        self.id0 = patcher.id0
        self.n_pixels = patcher.n_pixels
        self.temperature_setpoint = patcher.temperature_setpoint
        self.temperature = patcher.temperature
        self.wavelength = patcher.wavelength
        self.spectrum = patcher.spectrum
        self.fpga_version = patcher.fpga_version
        self.firmware_version = patcher.firmware_version
        self.library_version = patcher.library_version

        self.patcher = patcher

    def test_connect(self):
        """Test connecting to the first device."""
        spec = AvsFiberSpectrograph()
        self.patch.return_value.AVS_UpdateUSBDevices.assert_called_once()
        self.patch.return_value.AVS_GetList.assert_called_once()
        self.patch.return_value.AVS_Activate.assert_called_once_with(self.id0)
        self.patch.return_value.AVS_GetNumPixels.assert_called_once()
        assert spec.device == self.id0

    def test_create_with_logger(self):
        """Test that a passed-in logger is used for log messages."""
        log = logging.Logger("testingLogger")
        with self.assertLogs(log, logging.DEBUG):
            spec = AvsFiberSpectrograph(log=log)
        # simple check that the instance was created successfully
        assert spec.device == self.id0

    def test_create_with_stdout_log(self):
        """Test that the ``log_to_stdout`` init option works."""
        capture = io.StringIO()
        with contextlib.redirect_stdout(capture):
            spec = AvsFiberSpectrograph(log_to_stdout=True)
        assert "Found 1 attached USB Avantes device" in capture.getvalue()
        assert "Activated connection" in capture.getvalue()
        # simple check that the instance was created successfully
        assert spec.device == self.id0

    def test_connect_serial_number(self):
        """Test connecting to a device with a specific serial number."""
        serial_number = "54321"
        n_devices = 2
        id1 = AvsIdentity(
            bytes(str(serial_number), "ascii"),
            b"Fake Spectrograph 2",
            AvsDeviceStatus.USB_AVAILABLE.value,
        )

        def mock_getList(a_listSize, a_pRequiredSize, a_pList):
            """Pretend that two devices are connected."""
            a_pList[:] = [self.id0, id1]
            return n_devices

        self.patch.return_value.AVS_GetList.side_effect = mock_getList
        self.patch.return_value.AVS_UpdateUSBDevices.return_value = n_devices

        spec = AvsFiberSpectrograph(serial_number=serial_number)
        self.patch.return_value.AVS_UpdateUSBDevices.assert_called_once()
        self.patch.return_value.AVS_GetList.assert_called_once()
        self.patch.return_value.AVS_Activate.assert_called_with(id1)
        assert spec.device == id1

    def test_connect_no_serial_number_two_devices_fails(self):
        serial_number = "54321"
        n_devices = 2
        id1 = AvsIdentity(
            bytes(str(serial_number), "ascii"),
            b"Fake Spectrograph 2",
            AvsDeviceStatus.USB_AVAILABLE.value,
        )

        def mock_getList(a_listSize, a_pRequiredSize, a_pList):
            """Pretend that two devices are connected."""
            a_pList[0] = self.id0
            a_pList[1] = id1
            return n_devices

        self.patch.return_value.AVS_GetList.side_effect = mock_getList
        self.patch.return_value.AVS_UpdateUSBDevices.return_value = n_devices

        msg = (
            "Multiple devices found, but no serial number specified. Attached devices: "
        )
        with pytest.raises(RuntimeError, match=msg):
            AvsFiberSpectrograph()
        self.patch.return_value.AVS_UpdateUSBDevices.assert_called_once()
        self.patch.return_value.AVS_GetList.assert_called_once()
        self.patch.return_value.AVS_Activate.assert_not_called()

    def test_connect_bad_serial_number_fails(self):
        """Test that connect raises an exception if the requested device does
        not exist.
        """
        serial_number = "54321"

        with pytest.raises(LookupError, match=f"Device {serial_number=} not found"):
            AvsFiberSpectrograph(serial_number=serial_number)
        self.patch.return_value.AVS_UpdateUSBDevices.assert_called_once()
        self.patch.return_value.AVS_GetList.assert_called_once()
        self.patch.return_value.AVS_Activate.assert_not_called()

    def test_connect_bad_handle_fails(self):
        """Test that connect raises an exception if the device cannot be
        activated.
        """
        self.patch.return_value.AVS_Activate.return_value = (
            AvsReturnCode.invalidHandle.value
        )

        with pytest.raises(RuntimeError, match="Invalid device handle"):
            AvsFiberSpectrograph()
        self.patch.return_value.AVS_UpdateUSBDevices.assert_called_once()
        self.patch.return_value.AVS_GetList.assert_called_once()
        self.patch.return_value.AVS_Activate.assert_called_once()

    def test_connect_invalid_size(self):
        """Test that connect raises if GetList returns "Invalid Size"."""
        self.patch.return_value.AVS_GetList.side_effect = None
        self.patch.return_value.AVS_GetList.return_value = (
            AvsReturnCode.ERR_INVALID_SIZE.value
        )
        with pytest.raises(AvsReturnError, match="Fatal Error"):
            AvsFiberSpectrograph()
        self.patch.return_value.AVS_UpdateUSBDevices.assert_called_once()
        self.patch.return_value.AVS_GetList.assert_called_once()
        self.patch.return_value.AVS_Activate.assert_not_called()

    def test_connect_other_error(self):
        """Test that connect raises with a message containing the interpreted
        code if GetList returns an error code.
        """
        self.patch.return_value.AVS_GetList.side_effect = None
        self.patch.return_value.AVS_GetList.return_value = (
            AvsReturnCode.ERR_DLL_INITIALISATION.value
        )
        with pytest.raises(AvsReturnError, match="ERR_DLL_INITIALISATION"):
            AvsFiberSpectrograph()
        self.patch.return_value.AVS_UpdateUSBDevices.assert_called_once()
        self.patch.return_value.AVS_GetList.assert_called_once()
        self.patch.return_value.AVS_Activate.assert_not_called()

    def test_connect_no_devices(self):
        """Test that connect raises if no devices were found."""
        self.patch.return_value.AVS_UpdateUSBDevices.return_value = 0

        with pytest.raises(RuntimeError, match="No attached USB Avantes devices found"):
            AvsFiberSpectrograph()
        self.patch.return_value.AVS_UpdateUSBDevices.assert_called_once()
        self.patch.return_value.AVS_GetList.assert_not_called()
        self.patch.return_value.AVS_Activate.assert_not_called()

    def test_connect_single_device_already_connected(self):
        """Test that connect raises if the single device claims to already
        be connected in its AvsIdentity field.
        """
        self.id0.Status = AvsDeviceStatus.USB_IN_USE_BY_APPLICATION.value

        with pytest.raises(
            RuntimeError, match="Requested AVS device is already in use"
        ):
            AvsFiberSpectrograph()
        self.patch.return_value.AVS_UpdateUSBDevices.assert_called_once()
        self.patch.return_value.AVS_GetList.assert_called_once()
        self.patch.return_value.AVS_Activate.assert_not_called()

    def test_connect_device_serial_number_already_connected(self):
        """Test that connect raises if the device requested by serial number
        claims to already be connected in its AvsIdentity field.
        """
        n_devices = 2
        serial_number = "54321"
        id1 = AvsIdentity(
            bytes(str(serial_number), "ascii"),
            b"Fake Spectrograph 2",
            AvsDeviceStatus.USB_IN_USE_BY_OTHER.value,
        )

        def mock_getList(a_listSize, a_pRequiredSize, a_pList):
            """Pretend that the desired device is already connected."""
            a_pList[:] = [self.id0, id1]
            return n_devices

        self.patch.return_value.AVS_GetList.side_effect = mock_getList
        self.patch.return_value.AVS_UpdateUSBDevices.return_value = n_devices

        with pytest.raises(
            RuntimeError, match="Requested AVS device is already in use"
        ):
            AvsFiberSpectrograph(serial_number=serial_number)
        self.patch.return_value.AVS_UpdateUSBDevices.assert_called_once()
        self.patch.return_value.AVS_GetList.assert_called_once()
        self.patch.return_value.AVS_Activate.assert_not_called()

    def test_connect_Activate_fails(self):
        """Test that connect raises if the Activate command fails."""
        self.patch.return_value.AVS_Activate.return_value = (
            AvsReturnCode.ERR_DLL_INITIALISATION.value
        )

        with pytest.raises(AvsReturnError, match="Activate"):
            AvsFiberSpectrograph()
        self.patch.return_value.AVS_UpdateUSBDevices.assert_called_once()
        self.patch.return_value.AVS_GetList.assert_called_once()
        self.patch.return_value.AVS_Activate.assert_called_once()

    def test_connect_GetNumPixels_fails(self):
        """Test that connect ."""
        self.patch.return_value.AVS_GetNumPixels.side_effect = None
        self.patch.return_value.AVS_GetNumPixels.return_value = (
            AvsReturnCode.ERR_DEVICE_NOT_FOUND.value
        )

        with pytest.raises(AvsReturnError, match="GetNumPixels"):
            AvsFiberSpectrograph()
        self.patch.return_value.AVS_UpdateUSBDevices.assert_called_once()
        self.patch.return_value.AVS_GetList.assert_called_once()
        self.patch.return_value.AVS_Activate.assert_called_once()
        self.patch.return_value.AVS_GetNumPixels.assert_called_once()

    def test_disconnect(self):
        """Test a successful USB disconnect command."""
        spec = AvsFiberSpectrograph()
        spec.disconnect()
        self.patch.return_value.AVS_Deactivate.assert_called_once_with(self.handle)
        self.patch.return_value.AVS_Done.assert_called_once_with()
        assert spec.handle is None

    def test_disconnect_no_handle(self):
        """Test that we do not attempt to disconnect if there is no device
        handle.
        """
        spec = AvsFiberSpectrograph()
        spec.handle = None
        spec.disconnect()
        self.patch.return_value.AVS_Deactivate.assert_not_called()
        self.patch.return_value.AVS_Done.assert_called_once_with()

    def test_disconnect_bad_handle(self):
        """Do not attempt to disconnect if the device handle is bad."""
        spec = AvsFiberSpectrograph()
        spec.handle = AvsReturnCode.invalidHandle.value
        spec.disconnect()
        self.patch.return_value.AVS_Deactivate.assert_not_called()
        self.patch.return_value.AVS_Done.assert_called_once_with()

    def test_disconnect_fails_logged(self):
        """Test that a "failed" Deactivate emits an error."""
        self.patch.return_value.AVS_Deactivate.return_value = False
        spec = AvsFiberSpectrograph()
        with self.assertLogs(spec.log, "ERROR"):
            spec.disconnect()
        self.patch.return_value.AVS_Deactivate.assert_called_once_with(self.handle)
        self.patch.return_value.AVS_Done.assert_called_once_with()

    def test_disconnect_on_delete(self):
        """Test that the connection is closed if the object is deleted."""
        spec = AvsFiberSpectrograph()
        del spec
        self.patch.return_value.AVS_Deactivate.assert_called_once_with(self.handle)
        self.patch.return_value.AVS_Done.assert_called_once_with()

    def test_disconnect_other_exception(self):
        """Test that disconnect continues if there some other exception raised
        during disconnect.
        """
        self.patch.return_value.AVS_Deactivate.side_effect = RuntimeError
        spec = AvsFiberSpectrograph()
        with self.assertLogs(spec.log, "ERROR"):
            spec.disconnect()
        self.patch.return_value.AVS_Deactivate.assert_called_once_with(self.handle)
        self.patch.return_value.AVS_Done.assert_called_once_with()

    def test_get_status(self):
        spec = AvsFiberSpectrograph()
        status = spec.get_status()
        assert status.fpga_version == self.fpga_version
        assert status.firmware_version == self.firmware_version
        assert status.library_version == self.library_version
        assert status.n_pixels == self.n_pixels
        assert status.temperature_setpoint == self.temperature_setpoint
        np.testing.assert_allclose(status.temperature, self.temperature)
        assert status.config is None

        # Check that full=True returns a AvsDeviceConfig instead of None
        # (we're not worried about the contents of it here)
        status = spec.get_status(full=True)
        assert status.config is not None

    def test_get_status_getVersionInfo_fails(self):
        spec = AvsFiberSpectrograph()
        self.patch.return_value.AVS_GetVersionInfo.side_effect = None
        self.patch.return_value.AVS_GetVersionInfo.return_value = (
            AvsReturnCode.ERR_DEVICE_NOT_FOUND.value
        )
        with pytest.raises(
            AvsReturnError, match="GetVersionInfo.*ERR_DEVICE_NOT_FOUND"
        ):
            spec.get_status()

    def test_get_status_getParameter_fails(self):
        spec = AvsFiberSpectrograph()
        self.patch.return_value.AVS_GetParameter.side_effect = None
        self.patch.return_value.AVS_GetParameter.return_value = (
            AvsReturnCode.ERR_INVALID_DEVICE_ID.value
        )
        with pytest.raises(AvsReturnError, match="GetParameter.*ERR_INVALID_DEVICE_ID"):
            spec.get_status()

    def test_get_status_getAnalogIn_fails(self):
        spec = AvsFiberSpectrograph()
        self.patch.return_value.AVS_GetAnalogIn.side_effect = None
        self.patch.return_value.AVS_GetAnalogIn.return_value = (
            AvsReturnCode.ERR_TIMEOUT.value
        )
        with pytest.raises(AvsReturnError, match="GetAnalogIn.*ERR_TIMEOUT"):
            spec.get_status()

    async def test_expose(self):
        duration = 0.5  # seconds
        spec = AvsFiberSpectrograph()

        t0 = time.monotonic()
        result = await spec.expose(duration)
        t1 = time.monotonic()

        assert t1 - t0 > duration
        self.patch.return_value.AVS_PrepareMeasure.assert_called_once()
        # integration time is in ms, duration in seconds
        assert self.patcher.measure_config_sent.IntegrationTime == duration * 1000
        assert self.patcher.measure_config_sent.StartPixel == 0
        assert self.patcher.measure_config_sent.StopPixel == self.n_pixels - 1
        assert self.patcher.measure_config_sent.NrAverages == 1
        self.patch.return_value.AVS_Measure.assert_called_once_with(self.handle, 0, 1)
        assert self.patch.return_value.AVS_PollScan.call_count == 4
        np.testing.assert_array_equal(result[0].to_value(u.nm), self.wavelength)
        np.testing.assert_array_equal(result[1], self.spectrum)

    async def test_expose_raises_if_active_exposure(self):
        """Starting a new exposure while one is currently active should
        raise.
        """
        duration = 0.2  # seconds
        spec = AvsFiberSpectrograph()

        task = asyncio.create_task(spec.expose(duration))
        await asyncio.sleep(0.1)  # give the event loop time to start
        with pytest.raises(RuntimeError, match="Cannot start new exposure"):
            task2 = asyncio.create_task(spec.expose(duration))
            await task2
        await task
        # in addition to raising, should have only called these functions once
        self.patch.return_value.AVS_PrepareMeasure.assert_called_once()
        self.patch.return_value.AVS_Measure.assert_called_once_with(self.handle, 0, 1)
        self.patch.return_value.AVS_GetScopeData.assert_called_once()

    async def test_expose_prepare_fails(self):
        duration = 0.5  # seconds
        self.patch.return_value.AVS_PrepareMeasure.side_effect = None
        self.patch.return_value.AVS_PrepareMeasure.return_value = (
            AvsReturnCode.ERR_INVALID_PARAMETER.value
        )

        spec = AvsFiberSpectrograph()
        with pytest.raises(AvsReturnError, match="PrepareMeasure"):
            await spec.expose(duration)
        self.patch.return_value.AVS_PrepareMeasure.assert_called_once()
        self.patch.return_value.AVS_Measure.assert_not_called()

    async def test_expose_measure_fails(self):
        duration = 0.5  # seconds
        self.patch.return_value.AVS_Measure.side_effect = None
        self.patch.return_value.AVS_Measure.return_value = (
            AvsReturnCode.ERR_INVALID_STATE.value
        )

        spec = AvsFiberSpectrograph()
        with pytest.raises(AvsReturnError, match="Measure"):
            await spec.expose(duration)
        self.patch.return_value.AVS_PrepareMeasure.assert_called_once()
        self.patch.return_value.AVS_Measure.assert_called_once_with(self.handle, 0, 1)

    async def test_expose_GetLambda_fails(self):
        duration = 0.5  # seconds
        self.patch.return_value.AVS_GetLambda.side_effect = None
        self.patch.return_value.AVS_GetLambda.return_value = (
            AvsReturnCode.ERR_INVALID_DEVICE_ID.value
        )

        spec = AvsFiberSpectrograph()
        with pytest.raises(AvsReturnError, match="GetLambda"):
            await spec.expose(duration)
        self.patch.return_value.AVS_PrepareMeasure.assert_called_once()
        self.patch.return_value.AVS_Measure.assert_called_once_with(self.handle, 0, 1)
        self.patch.return_value.AVS_PollScan.assert_not_called()

    async def test_expose_PollScan_fails(self):
        duration = 0.5  # seconds
        self.patch.return_value.AVS_PollScan.side_effect = None
        self.patch.return_value.AVS_PollScan.return_value = (
            AvsReturnCode.ERR_INVALID_DEVICE_ID.value
        )

        spec = AvsFiberSpectrograph()
        with pytest.raises(AvsReturnError, match="PollScan"):
            await spec.expose(duration)
        self.patch.return_value.AVS_PrepareMeasure.assert_called_once()
        self.patch.return_value.AVS_Measure.assert_called_once_with(self.handle, 0, 1)
        self.patch.return_value.AVS_PollScan.assert_called_once_with(self.handle)

    async def test_expose_PollScan_timeout(self):
        """Test that `expose` raises if it has to wait too long when
        polling.
        """
        duration = 0.5  # seconds
        # Have the PollScan just run forever.
        self.patch.return_value.AVS_PollScan.side_effect = itertools.repeat(0)

        spec = AvsFiberSpectrograph()
        # asyncio.TimeoutError would be raised if the `wait_for` times out,
        # but the message would not include this text.
        with pytest.raises(
            asyncio.TimeoutError, match="Timeout polling for exposure to be ready"
        ):
            # Use `wait_for` to keep `expose` from hanging if there is a bug.
            await asyncio.wait_for(spec.expose(duration), 2)
        self.patch.return_value.AVS_PrepareMeasure.assert_called_once()
        self.patch.return_value.AVS_Measure.assert_called_once_with(self.handle, 0, 1)
        # PollScan will be called a hundred times or so.
        self.patch.return_value.AVS_PollScan.assert_called()

    async def test_expose_GetScopeData_fails(self):
        duration = 0.5  # seconds
        self.patch.return_value.AVS_GetScopeData.side_effect = None
        self.patch.return_value.AVS_GetScopeData.return_value = (
            AvsReturnCode.ERR_INVALID_MEAS_DATA.value
        )

        spec = AvsFiberSpectrograph()
        with pytest.raises(AvsReturnError, match="GetScopeData"):
            await spec.expose(duration)
        self.patch.return_value.AVS_PrepareMeasure.assert_called_once()
        self.patch.return_value.AVS_Measure.assert_called_once_with(self.handle, 0, 1)
        assert self.patch.return_value.AVS_PollScan.call_count == 4

    async def test_expose_duration_out_of_range(self):
        """The vendor docs specify 0.002ms - 600s as valid durations."""

        async def check_duration_fails(duration):
            spec = AvsFiberSpectrograph()
            with pytest.raises(
                RuntimeError, match="Exposure duration not in valid range:"
            ):
                # timeout=1s because the command should fail immediately.
                await asyncio.wait_for(spec.expose(duration), 1)
            self.patch.return_value.AVS_PrepareMeasure.assert_not_called()
            self.patch.return_value.AVS_Measure.assert_not_called()
            self.patch.return_value.AVS_PollScan.assert_not_called()
            self.patch.return_value.AVS_GetScopeData.assert_not_called()

        duration = MIN_DURATION - 1e-9
        await check_duration_fails(duration)
        duration = MAX_DURATION + 1e-9
        await check_duration_fails(duration)

    def test_check_expose_ok(self):
        duration = 2
        spec = AvsFiberSpectrograph()
        assert spec.check_expose_ok(duration) is None

        duration = 1e-6
        assert "Exposure duration not in valid range: " in spec.check_expose_ok(
            duration
        )

        duration = 2
        spec._expose_task = unittest.mock.NonCallableMock(
            spec=asyncio.Future, **{"done.return_value": False}
        )
        assert "Cannot start new exposure" in spec.check_expose_ok(duration)

    async def test_stop_exposure(self):
        """Test that `stop_exposure` ends the active `expose`."""
        duration = 5  # seconds
        spec = AvsFiberSpectrograph()

        t0 = time.monotonic()
        task = asyncio.create_task(spec.expose(duration))
        await asyncio.sleep(0.1)  # give the event loop time to start
        spec.stop_exposure()
        with pytest.raises(asyncio.CancelledError):
            await task
        t1 = time.monotonic()

        # cancelling the task should make it end much sooner than the duration
        assert t1 - t0 < 1
        self.patch.return_value.AVS_StopMeasure.assert_called_with(self.handle)

    async def test_stop_exposure_during_poll_loop(self):
        """Test that `stop_exposure` ends the active `expose` when called
        during the `PollData` loop.
        """
        duration = 0.2  # seconds
        # repeat "no data" forever, so that `stop` will trigger during polling
        self.patch.return_value.AVS_PollScan.side_effect = itertools.repeat(0)
        spec = AvsFiberSpectrograph()

        task = asyncio.create_task(spec.expose(duration))
        await asyncio.sleep(duration + 0.1)  # wait until we are in the poll loop
        spec.stop_exposure()
        with pytest.raises(asyncio.CancelledError):
            await task

        self.patch.return_value.AVS_StopMeasure.assert_called_with(self.handle)
        self.patch.return_value.AVS_PollScan.assert_called_with(self.handle)
        self.patch.return_value.AVS_GetScopeData.assert_not_called()

    async def test_stop_exposure_no_expose_running(self):
        """Test that stop_exposure does nothing if there is no active
        `expose` command.
        """
        spec = AvsFiberSpectrograph()
        spec.stop_exposure()
        self.patch.return_value.AVS_StopMeasure.assert_not_called()

    async def test_stop_exposure_fails(self):
        """Test `AVS_StopMeasure` returning an error: the existing exposure
        task should be cancelled, but `stop_exposure` should also raise."""
        duration = 5  # seconds
        self.patch.return_value.AVS_StopMeasure.return_value = (
            AvsReturnCode.ERR_TIMEOUT.value
        )
        spec = AvsFiberSpectrograph()

        t0 = time.monotonic()
        task = asyncio.create_task(spec.expose(duration))
        await asyncio.sleep(0.1)  # give the event loop time to start
        with pytest.raises(AvsReturnError, match="StopMeasure"):
            spec.stop_exposure()
        with pytest.raises(asyncio.CancelledError):
            await task
        t1 = time.monotonic()

        # cancelling the task should make it end much sooner than the duration
        assert t1 - t0 < 1
        self.patch.return_value.AVS_StopMeasure.assert_called_with(self.handle)

    async def test_disconnect_active_exposure(self):
        """Test that disconnecting cancels an active exposure."""
        duration = 5  # seconds
        spec = AvsFiberSpectrograph()

        t0 = time.monotonic()
        task = asyncio.create_task(spec.expose(duration))
        await asyncio.sleep(0.1)  # give the event loop time to start
        spec.disconnect()
        with pytest.raises(asyncio.CancelledError):
            await task
        t1 = time.monotonic()

        # cancelling the task should make it end much sooner than the duration
        assert t1 - t0 < 1
        self.patch.return_value.AVS_StopMeasure.assert_called_with(self.handle)
        self.patch.return_value.AVS_Deactivate.assert_called_once_with(self.handle)
        self.patch.return_value.AVS_Done.assert_called_once_with()
        assert spec.handle is None

    async def test_disconnect_stop_exposure_exception(self):
        """Test that `disconnect` does not raise if `stop_exposure` raises, but
        does log an error message, and continues with deactivating the device.
        """
        duration = 5  # seconds
        spec = AvsFiberSpectrograph()
        self.patch.return_value.AVS_StopMeasure.return_value = (
            AvsReturnCode.ERR_INVALID_PARAMETER.value
        )

        t0 = time.monotonic()
        task = asyncio.create_task(spec.expose(duration))
        await asyncio.sleep(0.1)  # give the event loop time to start
        try:
            with self.assertLogs(spec.log, "ERROR"):
                spec.disconnect()
        except AvsReturnError:
            self.fail(
                "disconnect() should not raise an exception, even if `stop_exposure` does."
            )
        with pytest.raises(asyncio.CancelledError):
            await task
        t1 = time.monotonic()

        # cancelling the task should make it end much sooner than the duration
        assert t1 - t0 < 1
        self.patch.return_value.AVS_StopMeasure.assert_called_with(self.handle)
        self.patch.return_value.AVS_Deactivate.assert_called_once_with(self.handle)
        self.patch.return_value.AVS_Done.assert_called_once_with()
        assert spec.handle is None


class TestAvsReturnError(unittest.TestCase):
    """Tests of the string representations of AvsReturnError exceptions."""

    def test_valid_code(self):
        """Test that an valid code results in a useful message."""
        code = -24
        what = "valid test"
        err = AvsReturnError(code, what)
        msg = (
            "Error calling `valid test` with error code <AvsReturnCode.ERR_ACCESS: -24>"
        )
        assert msg in repr(err)

    def test_invalid_size(self):
        """Test that the "invalid size" code results in a useful message."""
        code = -9
        what = "invalid size test"
        err = AvsReturnError(code, what)
        msg = "Fatal Error <AvsReturnCode.ERR_INVALID_SIZE: -9> calling `invalid size test`"
        assert msg in repr(err)

    def test_invalid_code(self):
        """Test that an invalid code still results in a useful message."""
        code = -123456321
        what = "invalid code test"
        err = AvsReturnError(code, what)
        msg = "Unknown Error (-123456321) calling `invalid code test`; Please consult Avantes documentation"
        assert msg in repr(err)


class TestAvsDeviceConfig(unittest.TestCase):
    def test_str(self):
        """Test some specific aspects of the (long) string representation."""
        config = AvsDeviceConfig()
        string = str(config)
        assert "AvsDeviceConfig" in string
        assert "TecControl_m_Enable=False" in string
        assert "SpectrumCorrect" not in string
        assert "OemData" not in string

    def test_frozen(self):
        """Test that we cannot assign new attributes to this struct,
        but that we can modify existing attributes.
        """
        config = AvsDeviceConfig()

        with pytest.raises(TypeError, match="is a frozen class; 'blahblah'"):
            config.blahblah = 101010

        # Can we modify an existing value?
        assert not config.TecControl_m_Enable
        config.TecControl_m_Enable = True
        assert config.TecControl_m_Enable


class TestAvsMeasureConfig(unittest.TestCase):
    def test_frozen(self):
        """Test that we cannot assign new attributes to this struct,
        but that we can modify existing attributes.
        """
        config = AvsMeasureConfig()

        with pytest.raises(TypeError, match="is a frozen class; 'blahblah'"):
            config.blahblah = 101010

        # Can we modify an existing value?
        assert not config.StartPixel
        config.StartPixel = True
        assert config.StartPixel


class TestAvsIdentity(unittest.TestCase):
    def test_str(self):
        """Test some specific aspects of the string representation."""
        serial_number = "12345"
        name = "some name"
        identity = AvsIdentity(
            bytes(str(serial_number), "ascii"),
            bytes(str(name), "ascii"),
            AvsDeviceStatus.USB_IN_USE_BY_OTHER.value,
        )
        string = str(identity)
        assert "AvsIdentity" in string
        assert serial_number in string
        assert name in string
        assert "USB_IN_USE_BY_OTHER" in string  # from the "Status" field

    def test_frozen(self):
        """Test that we cannot assign new attributes to this struct,
        but that we can modify existing attributes.
        """
        serial_number = "12345"
        name = "some name"
        identity = AvsIdentity(
            bytes(str(serial_number), "ascii"),
            bytes(str(name), "ascii"),
            AvsDeviceStatus.USB_IN_USE_BY_OTHER.value,
        )

        with pytest.raises(TypeError, match="is a frozen class; 'blahblah'"):
            identity.blahblah = 101010

        # Can we modify an existing value?
        identity.Status = AvsDeviceStatus.USB_AVAILABLE.value
        assert struct.unpack("B", identity.Status)[0] == AvsDeviceStatus.USB_AVAILABLE


if __name__ == "__main__":
    unittest.main()
