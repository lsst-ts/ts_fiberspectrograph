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

import asyncio
import contextlib
import io
import logging
import struct
import unittest

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
    """Tests of the Avantes controller with the concrete simulator."""

    def setUp(self):
        self.simulator = AvsSimulator()

    def make_spec(self, **kwargs):
        return AvsFiberSpectrograph(libavs=self.simulator, **kwargs)

    def test_connect(self):
        spec = self.make_spec()
        assert spec.device == self.simulator.id0
        assert self.simulator.call_counts["AVS_UpdateUSBDevices"] == 1
        assert self.simulator.call_counts["AVS_GetList"] == 1
        assert self.simulator.call_counts["AVS_Activate"] == 1
        assert self.simulator.call_counts["AVS_GetNumPixels"] == 1

    def test_connect_by_serial_number(self):
        identity = AvsIdentity(b"54321", b"Fake Spectrograph 2", AvsDeviceStatus.USB_AVAILABLE.value)
        self.simulator.devices.append(identity)
        spec = self.make_spec(serial_number="54321")
        assert spec.device == identity

    def test_connect_rejects_ambiguous_or_missing_devices(self):
        self.simulator.devices.append(
            AvsIdentity(b"54321", b"Fake Spectrograph 2", AvsDeviceStatus.USB_AVAILABLE.value)
        )
        with pytest.raises(RuntimeError, match="Multiple devices"):
            self.make_spec()
        with pytest.raises(LookupError, match="not found"):
            self.make_spec(serial_number="99999")

    def test_connect_rejects_in_use_device(self):
        self.simulator.id0.Status = AvsDeviceStatus.USB_IN_USE_BY_APPLICATION.value
        with pytest.raises(RuntimeError, match="already in use"):
            self.make_spec()
        assert self.simulator.call_counts["AVS_Activate"] == 0

    def test_connect_errors(self):
        cases = (
            ("AVS_GetList", AvsReturnCode.ERR_INVALID_SIZE.value, "Fatal Error"),
            ("AVS_Activate", AvsReturnCode.ERR_DLL_INITIALISATION.value, "Activate"),
            ("AVS_GetNumPixels", AvsReturnCode.ERR_DEVICE_NOT_FOUND.value, "GetNumPixels"),
        )
        for method, code, match in cases:
            with self.subTest(method=method):
                self.setUp()
                self.simulator.return_codes[method] = code
                with pytest.raises(AvsReturnError, match=match):
                    self.make_spec()

    def test_connect_bad_handle(self):
        self.simulator.return_codes["AVS_Activate"] = AvsReturnCode.invalidHandle.value
        with pytest.raises(RuntimeError, match="Invalid device handle"):
            self.make_spec()

    def test_create_with_logger(self):
        log = logging.Logger("testingLogger")
        with self.assertLogs(log, logging.DEBUG):
            assert self.make_spec(log=log).device == self.simulator.id0

    def test_create_with_stdout_log(self):
        capture = io.StringIO()
        with contextlib.redirect_stdout(capture):
            self.make_spec(log_to_stdout=True)
        assert "Found 1 attached USB Avantes device" in capture.getvalue()
        assert "Activated connection" in capture.getvalue()

    def test_disconnect(self):
        spec = self.make_spec()
        spec.disconnect()
        assert self.simulator.call_counts["AVS_Deactivate"] == 1
        assert self.simulator.call_counts["AVS_Done"] == 1
        assert spec.handle is None

    def test_disconnect_continues_after_failure(self):
        spec = self.make_spec()
        self.simulator.return_codes["AVS_Deactivate"] = False
        with self.assertLogs(spec.log, "ERROR"):
            spec.disconnect()
        assert self.simulator.call_counts["AVS_Done"] == 1

    def test_disconnect_continues_after_exception(self):
        spec = self.make_spec()
        self.simulator.exceptions["AVS_Deactivate"] = RuntimeError()
        with self.assertLogs(spec.log, "ERROR"):
            spec.disconnect()
        assert self.simulator.call_counts["AVS_Done"] == 1

    def test_get_status(self):
        spec = self.make_spec()
        status = spec.get_status()
        assert status.fpga_version == self.simulator.fpga_version
        assert status.firmware_version == self.simulator.firmware_version
        assert status.library_version == self.simulator.library_version
        assert status.n_pixels == self.simulator.n_pixels
        assert status.temperature_setpoint == self.simulator.temperature_setpoint
        np.testing.assert_allclose(status.temperature, self.simulator.temperature)
        assert status.config is None
        assert spec.get_status(full=True).config is not None

    def test_status_diagnostics_are_bounded(self):
        spec = self.make_spec()
        for _ in range(1000):
            spec.get_status()
        assert self.simulator.call_counts["AVS_GetParameter"] == 1000
        assert self.simulator.measure_config_sent is None
        assert not hasattr(self.simulator, "mock_calls")

    def test_get_status_errors(self):
        cases = (
            ("AVS_GetVersionInfo", AvsReturnCode.ERR_DEVICE_NOT_FOUND.value, "GetVersionInfo"),
            ("AVS_GetParameter", AvsReturnCode.ERR_INVALID_DEVICE_ID.value, "GetParameter"),
            ("AVS_GetAnalogIn", AvsReturnCode.ERR_TIMEOUT.value, "GetAnalogIn"),
        )
        for method, code, match in cases:
            with self.subTest(method=method):
                self.setUp()
                spec = self.make_spec()
                self.simulator.return_codes[method] = code
                with pytest.raises(AvsReturnError, match=match):
                    spec.get_status()

    async def test_expose(self):
        spec = self.make_spec()
        result = await spec.expose(0.01)
        config = self.simulator.measure_config_sent
        assert config.IntegrationTime == 10
        assert config.StartPixel == 0
        assert config.StopPixel == self.simulator.n_pixels - 1
        assert config.NrAverages == 1
        assert self.simulator.call_counts["AVS_Measure"] == 1
        assert self.simulator.call_counts["AVS_PollScan"] == 4
        np.testing.assert_array_equal(result[0].to_value(u.nm), self.simulator.wavelength)
        np.testing.assert_array_equal(result[1], self.simulator.spectrum)

    async def test_expose_resets_polling(self):
        spec = self.make_spec()
        await spec.expose(0.01)
        await spec.expose(0.01)
        assert self.simulator.call_counts["AVS_Measure"] == 2
        assert self.simulator.call_counts["AVS_PollScan"] == 8

    async def test_expose_errors(self):
        cases = (
            ("AVS_PrepareMeasure", AvsReturnCode.ERR_INVALID_PARAMETER.value, "PrepareMeasure"),
            ("AVS_Measure", AvsReturnCode.ERR_INVALID_STATE.value, "Measure"),
            ("AVS_GetLambda", AvsReturnCode.ERR_INVALID_DEVICE_ID.value, "GetLambda"),
            ("AVS_PollScan", AvsReturnCode.ERR_INVALID_DEVICE_ID.value, "PollScan"),
            ("AVS_GetScopeData", AvsReturnCode.ERR_INVALID_MEAS_DATA.value, "GetScopeData"),
        )
        for method, code, match in cases:
            with self.subTest(method=method):
                self.setUp()
                self.simulator.return_codes[method] = code
                with pytest.raises(AvsReturnError, match=match):
                    await self.make_spec().expose(0.01)

    async def test_expose_timeout(self):
        self.simulator.polls_until_ready = float("inf")
        with pytest.raises(asyncio.TimeoutError, match="Timeout polling"):
            await self.make_spec().expose(0.01)

    async def test_expose_rejects_invalid_duration_and_overlap(self):
        spec = self.make_spec()
        for duration in (MIN_DURATION - 1e-9, MAX_DURATION + 1e-9):
            with pytest.raises(RuntimeError, match="Exposure duration"):
                await spec.expose(duration)
        task = asyncio.create_task(spec.expose(0.2))
        await asyncio.sleep(0)
        with pytest.raises(RuntimeError, match="Cannot start new exposure"):
            await spec.expose(0.2)
        await task

    async def test_stop_exposure(self):
        spec = self.make_spec()
        task = asyncio.create_task(spec.expose(5))
        await asyncio.sleep(0.01)
        spec.stop_exposure()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert self.simulator.call_counts["AVS_StopMeasure"] == 1

    async def test_stop_exposure_error_still_cancels(self):
        spec = self.make_spec()
        task = asyncio.create_task(spec.expose(5))
        await asyncio.sleep(0.01)
        self.simulator.return_codes["AVS_StopMeasure"] = AvsReturnCode.ERR_TIMEOUT.value
        with pytest.raises(AvsReturnError, match="StopMeasure"):
            spec.stop_exposure()
        with pytest.raises(asyncio.CancelledError):
            await task

    async def test_disconnect_cancels_active_exposure(self):
        spec = self.make_spec()
        task = asyncio.create_task(spec.expose(5))
        await asyncio.sleep(0.01)
        spec.disconnect()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert self.simulator.call_counts["AVS_Deactivate"] == 1
        assert self.simulator.call_counts["AVS_Done"] == 1


class TestAvsReturnError(unittest.TestCase):
    def test_valid_code(self):
        assert "ERR_ACCESS" in repr(AvsReturnError(-24, "valid test"))

    def test_invalid_size(self):
        assert "Fatal Error" in repr(AvsReturnError(-9, "invalid size test"))

    def test_invalid_code(self):
        assert "Unknown Error" in repr(AvsReturnError(-123456321, "invalid code test"))


class TestAvsDeviceConfig(unittest.TestCase):
    def test_str(self):
        string = str(AvsDeviceConfig())
        assert "AvsDeviceConfig" in string
        assert "SpectrumCorrect" not in string

    def test_frozen(self):
        config = AvsDeviceConfig()
        with pytest.raises(TypeError, match="blahblah"):
            config.blahblah = 101010
        config.TecControl_m_Enable = True
        assert config.TecControl_m_Enable


class TestAvsMeasureConfig(unittest.TestCase):
    def test_frozen(self):
        config = AvsMeasureConfig()
        with pytest.raises(TypeError, match="blahblah"):
            config.blahblah = 101010
        config.StartPixel = True
        assert config.StartPixel


class TestAvsIdentity(unittest.TestCase):
    def test_str_and_frozen(self):
        identity = AvsIdentity(b"12345", b"some name", AvsDeviceStatus.USB_IN_USE_BY_OTHER.value)
        assert "USB_IN_USE_BY_OTHER" in str(identity)
        with pytest.raises(TypeError, match="blahblah"):
            identity.blahblah = 101010
        identity.Status = AvsDeviceStatus.USB_AVAILABLE.value
        assert struct.unpack("B", identity.Status)[0] == AvsDeviceStatus.USB_AVAILABLE
