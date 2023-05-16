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
import itertools
import pathlib
import unittest
import unittest.mock
import urllib.parse

import astropy.io.fits
import pytest
from lsst.ts import fiberspectrograph, salobj
from lsst.ts.idl.enums.FiberSpectrograph import ExposureState

STD_TIMEOUT = 5  # standard command timeout (sec)
LONG_TIMEOUT = 20  # timeout for starting SAL components (sec)

TEST_CONFIG_DIR = pathlib.Path(__file__).parent / "data" / "config"


class TestFiberSpectrographCsc(
    salobj.BaseCscTestCase, unittest.IsolatedAsyncioTestCase
):
    """Test the functionality of the FiberSpectrographCsc, using a mocked
    spectrograph connection.

    These tests use an instance of `lsst.ts.fiberspectrograph.AvsSimulator`,
    to mock patch the fiber spectrograph vendor C library.
    The CSC uses the same simulator class when in ``Spectrograph``
    simulation mode to simulate the fiber spectrograph, but that simulator
    is held independently of the mock patch used for testing here.
    Having the CSC patch the AVS library (when going into simulation mode)
    separately from the unit test patching the same library allows us to test
    the functionality of turning simulation mode on and off; we want to treat
    the use of `unittest.mock` by the CSC simulator as an internal detail.
    """

    def setUp(self):
        self.patcher = fiberspectrograph.AvsSimulator()
        self.patch = self.patcher.start(testCase=self)
        super().setUp()

    def basic_make_csc(self, initial_state, config_dir, simulation_mode, index=-1):
        return fiberspectrograph.FiberSpectrographCsc(
            initial_state=initial_state,
            config_dir=config_dir,
            simulation_mode=simulation_mode,
            index=index,
        )

    async def check_exposureState(self, remote, expect):
        """Check the value of the ExposureState event."""
        state = await remote.evt_exposureState.next(flush=False, timeout=STD_TIMEOUT)
        assert state.status == expect

    async def check_summaryState(self, remote, expect):
        """Check the value of the SummaryState event."""
        state = await remote.evt_summaryState.next(flush=False, timeout=STD_TIMEOUT)
        assert state.summaryState == expect

    async def check_temperature(self, remote, temperature, setpoint):
        """Check the value of the temperature telemetry."""
        state = await remote.tel_temperature.next(flush=False, timeout=STD_TIMEOUT)
        assert state.temperature == pytest.approx(temperature)
        assert state.setpoint == pytest.approx(setpoint)

    async def test_standard_state_transitions(self):
        """Test that state changes connect/disconnect the spectrograph
        correctly.
        """
        async with self.make_csc(
            initial_state=salobj.State.STANDBY, config_dir=TEST_CONFIG_DIR
        ):
            await self.assert_next_sample(
                topic=self.remote.evt_softwareVersions,
                cscVersion=fiberspectrograph.__version__,
                subsystemVersions="",
            )

            await self.check_standard_state_transitions(
                enabled_commands=("cancelExposure", "expose")
            )

    async def test_connect_by_index(self):
        """Test that changing the index number changes the serial number
        that we attempt to connect to.
        """
        # Mock two connected devices (we will connect to the second).
        n_devices = 2
        index = fiberspectrograph.SalIndex.BROAD
        serial_number = fiberspectrograph.SERIAL_NUMBERS[index]
        id1 = fiberspectrograph.AvsIdentity(
            bytes(str(serial_number), "ascii"),
            b"Fake Spectrograph 2",
            fiberspectrograph.AvsDeviceStatus.USB_AVAILABLE.value,
        )

        def mock_getList(a_listSize, a_pRequiredSize, a_pList):
            """Pretend that two devices are connected."""
            a_pList[:] = [self.patcher.id0, id1]
            return n_devices

        self.patch.return_value.AVS_GetList.side_effect = mock_getList
        self.patch.return_value.AVS_UpdateUSBDevices.return_value = n_devices

        async with self.make_csc(
            initial_state=salobj.State.DISABLED, index=index, config_dir=TEST_CONFIG_DIR
        ):
            await self.assert_next_summary_state(salobj.State.DISABLED)
            assert self.csc.device.device == id1

    async def test_enable_fails(self):
        """Test that exceptions raised when connecting cause a fault when
        switching the CSC from STANDBY to DISABLED.
        """
        self.patch.return_value.AVS_Activate.return_value = (
            fiberspectrograph.AvsReturnCode.invalidHandle.value
        )
        async with self.make_csc(
            initial_state=salobj.State.STANDBY, config_dir=TEST_CONFIG_DIR
        ):
            # Check that we are properly in STANDBY at the start
            await self.assert_next_summary_state(salobj.State.STANDBY)
            error = await self.assert_next_sample(
                topic=self.remote.evt_errorCode, errorCode=0, errorReport=""
            )

            msg = "Failed to connect"
            with salobj.assertRaisesAckError(
                ack=salobj.SalRetCode.CMD_FAILED, result_contains=msg
            ):
                await self.remote.cmd_start.start(timeout=STD_TIMEOUT)
            await self.assert_next_summary_state(salobj.State.FAULT)
            error = await self.remote.evt_errorCode.next(
                flush=False, timeout=STD_TIMEOUT
            )
            assert "RuntimeError" in error.errorReport
            assert "Invalid device handle; cannot activate device" in error.errorReport
            assert self.csc.device is None

    async def test_expose_good(self):
        """Test that we can take an exposure and that appropriate events are
        emitted.
        """
        async with self.make_csc(
            initial_state=salobj.State.ENABLED,
            simulation_mode=fiberspectrograph.SimulationMode.S3Server,
            index=fiberspectrograph.SalIndex.RED,
            config_dir=TEST_CONFIG_DIR,
        ):
            # Check that we are properly in ENABLED at the start
            await self.assert_next_summary_state(salobj.State.ENABLED)
            assert self.csc.s3bucket_name == self.csc.s3bucket.name
            self.csc.image_service_client.get_next_obs_id = unittest.mock.AsyncMock(
                return_value=([1], "FS1_O_20221130_000001")
            )

            duration = 2  # seconds
            task = asyncio.create_task(
                self.remote.cmd_expose.set_start(
                    timeout=STD_TIMEOUT + duration, duration=duration
                )
            )
            await self.check_exposureState(self.remote, ExposureState.INTEGRATING)
            # Wait for the exposure to finish.
            await task
            await self.check_exposureState(self.remote, ExposureState.DONE)

            # Check the large file event.
            data = await self.remote.evt_largeFileObjectAvailable.next(
                flush=False, timeout=STD_TIMEOUT
            )
            parsed_url = urllib.parse.urlparse(data.url)
            assert parsed_url.scheme == "https"
            assert (
                parsed_url.netloc
                == urllib.parse.urlparse(
                    self.csc.s3bucket.service_resource.meta.client.meta.endpoint_url
                ).netloc
            )

            # Minimally check the data written to s3
            key = parsed_url.path[1:].split("/", maxsplit=1)[
                1
            ]  # Strip leading "rubinobs-lfa-test/"
            fileobj = await self.csc.s3bucket.download(key)
            hdulist = astropy.io.fits.open(fileobj)

            assert len(hdulist) == 2
            assert hdulist[0].header["CSCNAME"] == "FiberSpectrographCsc"
            assert hdulist[0].header["INSTRUME"] == "FiberSpectrograph.Red"
            # Check that out of range durations do not put us in FAULT,
            # and do not change the exposure state.
            duration = 1e-9  # seconds
            with salobj.assertRaisesAckError(
                ack=salobj.SalRetCode.CMD_FAILED,
                result_contains="Exposure duration",
            ):
                await asyncio.create_task(
                    self.remote.cmd_expose.set_start(
                        timeout=STD_TIMEOUT, duration=duration
                    )
                )
            # No ExposureState message should have been emitted.
            with pytest.raises(asyncio.TimeoutError):
                await self.remote.evt_exposureState.next(
                    flush=False, timeout=STD_TIMEOUT
                )
            # We should not have left ENABLED.
            with pytest.raises(asyncio.TimeoutError):
                await self.remote.evt_exposureState.next(
                    flush=False, timeout=STD_TIMEOUT
                )

    async def test_expose_failed_s3_upload(self):
        """Test that we can take an exposure and that the file is saved locally
        if s3 upload fails
        """
        async with self.make_csc(
            initial_state=salobj.State.ENABLED,
            simulation_mode=fiberspectrograph.SimulationMode.S3Server,
            index=fiberspectrograph.SalIndex.RED,
            config_dir=TEST_CONFIG_DIR,
        ):
            # Check that we are properly in ENABLED at the start
            await self.assert_next_summary_state(salobj.State.ENABLED)
            assert self.csc.s3bucket_name == self.csc.s3bucket.name
            self.csc.image_service_client.get_next_obs_id = unittest.mock.AsyncMock(
                return_value=([1], "FS1_O_20221130_000001")
            )

            def bad_upload(*args, **kwargs):
                raise RuntimeError("Failed on purpose")

            self.csc.s3bucket.upload = bad_upload

            duration = 2  # seconds
            task = asyncio.create_task(
                self.remote.cmd_expose.set_start(
                    timeout=STD_TIMEOUT + duration, duration=duration
                )
            )
            await self.check_exposureState(self.remote, ExposureState.INTEGRATING)
            # Wait for the exposure to finish.
            await task
            await self.check_exposureState(self.remote, ExposureState.DONE)

            # Check the large file event.
            data = await self.remote.evt_largeFileObjectAvailable.next(
                flush=False, timeout=STD_TIMEOUT
            )
            parsed_url = urllib.parse.urlparse(data.url)
            filepath = urllib.parse.unquote(parsed_url.path)
            assert parsed_url.scheme == "file"
            desired_path_start = "/tmp/" + self.csc.s3bucket.name + "/"
            start_nchar = len(desired_path_start)
            assert filepath[0:start_nchar] == desired_path_start

            # Minimally check the data file
            hdulist = astropy.io.fits.open(filepath)
            assert len(hdulist) == 2
            assert hdulist[0].header["CSCNAME"] == "FiberSpectrographCsc"
            assert hdulist[0].header["INSTRUME"] == "FiberSpectrograph.Red"

            # Check that out of range durations do not put us in FAULT,
            # and do not change the exposure state.
            duration = 1e-9  # seconds
            with salobj.assertRaisesAckError(
                ack=salobj.SalRetCode.CMD_FAILED,
                result_contains="Exposure duration",
            ):
                await asyncio.create_task(
                    self.remote.cmd_expose.set_start(
                        timeout=STD_TIMEOUT, duration=duration
                    )
                )
            # No ExposureState message should have been emitted.
            with pytest.raises(asyncio.TimeoutError):
                await self.remote.evt_exposureState.next(
                    flush=False, timeout=STD_TIMEOUT
                )
            # We should not have left ENABLED.
            with pytest.raises(asyncio.TimeoutError):
                await self.remote.evt_exposureState.next(
                    flush=False, timeout=STD_TIMEOUT
                )
            # Delete the file on success; leave it on failure, for diagnosis
            pathlib.Path(filepath).unlink()

    async def test_expose_fails(self):
        """Test that a failed exposure puts us in the FAULT state, which will
        disconnect the device.
        """
        # Make `GetScopeData` (which is called to get the measured output from
        # the device) return an error code, so that the device controller
        # raises an exception inside `expose()`.
        self.patch.return_value.AVS_GetScopeData.side_effect = None
        self.patch.return_value.AVS_GetScopeData.return_value = (
            fiberspectrograph.AvsReturnCode.ERR_INVALID_MEAS_DATA.value
        )
        async with self.make_csc(
            initial_state=salobj.State.ENABLED, config_dir=TEST_CONFIG_DIR
        ):
            # Check that we are properly in ENABLED at the start.
            await self.assert_next_summary_state(salobj.State.ENABLED)
            error = await self.assert_next_sample(
                topic=self.remote.evt_errorCode, errorCode=0, errorReport=""
            )

            msg = "Failed to take exposure"
            with salobj.assertRaisesAckError(
                ack=salobj.SalRetCode.CMD_FAILED, result_contains=msg
            ):
                await self.remote.cmd_expose.set_start(
                    timeout=STD_TIMEOUT, duration=0.5
                )
            # The exposure state should be Integrating during the exposure.
            await self.check_exposureState(self.remote, ExposureState.INTEGRATING)
            # The exposure state should be Failed after the exposure has
            # completed, because GetScopeData returned an error code.
            await self.assert_next_summary_state(salobj.State.FAULT)
            error = await self.remote.evt_errorCode.next(
                flush=False, timeout=STD_TIMEOUT
            )
            errorMsg = str(
                fiberspectrograph.AvsReturnError(
                    fiberspectrograph.AvsReturnCode.ERR_INVALID_MEAS_DATA.value,
                    "GetScopeData",
                )
            )
            assert errorMsg in error.errorReport
            # Going into FAULT should close the device connection.
            assert self.csc.device is None
            # the exposure state should be FAILED after a failed exposure
            await self.check_exposureState(self.remote, ExposureState.FAILED)

            # Test recovery from fault state
            await self.remote.cmd_standby.start(timeout=STD_TIMEOUT)
            await self.assert_next_summary_state(salobj.State.STANDBY)
            error = await self.assert_next_sample(
                topic=self.remote.evt_errorCode, errorCode=0, errorReport=""
            )

    async def test_expose_timeout(self):
        """Test that an exposure whose read times out puts us in FAULT and
        exposureState is set to TIMEOUT.
        """
        # Have the PollScan just run forever.
        self.patch.return_value.AVS_PollScan.side_effect = itertools.repeat(0)

        async with self.make_csc(
            initial_state=salobj.State.ENABLED, config_dir=TEST_CONFIG_DIR
        ):
            # Check that we are properly in ENABLED at the start.
            await self.assert_next_summary_state(salobj.State.ENABLED)

            msg = "Timeout waiting for exposure"
            duration = 0.1
            with salobj.assertRaisesAckError(
                ack=salobj.SalRetCode.CMD_FAILED, result_contains=msg
            ):
                await self.remote.cmd_expose.set_start(
                    timeout=STD_TIMEOUT + duration, duration=duration
                )
            # The exposure state should be Integrating during the exposure.
            await self.check_exposureState(self.remote, ExposureState.INTEGRATING)
            await self.check_exposureState(self.remote, ExposureState.TIMEDOUT)
            await self.assert_next_summary_state(salobj.State.FAULT)

    async def test_cancelExposure(self):
        """Test that we can stop an active exposure, and that the exposureState
        is changed appropriately.
        """
        async with self.make_csc(
            initial_state=salobj.State.ENABLED, config_dir=TEST_CONFIG_DIR
        ):
            # Check that we are properly in ENABLED at the start
            await self.assert_next_summary_state(salobj.State.ENABLED)

            duration = 5  # seconds
            task = asyncio.create_task(
                self.remote.cmd_expose.set_start(
                    timeout=STD_TIMEOUT + duration, duration=duration
                )
            )
            # Wait for the exposure to start integrating.
            await self.check_exposureState(self.remote, ExposureState.INTEGRATING)
            await self.remote.cmd_cancelExposure.set_start(timeout=STD_TIMEOUT)
            with salobj.assertRaisesAckError(ack=salobj.SalRetCode.CMD_ABORTED):
                await task
            await self.check_exposureState(self.remote, ExposureState.CANCELLED)

    async def test_telemetry(self):
        """Test that telemetry is emitted in the correct states.

        Notes
        -----
        If the CSC does not close the telemetry loop when the CSC is
        destroyed (e.g. via `close_tasks()`), you will see messages like
        `Task was destroyed but it is pending!` in the test output.
        """
        async with self.make_csc(
            initial_state=salobj.State.DISABLED, config_dir=TEST_CONFIG_DIR
        ):
            # Check that we are properly in STANDBY at the start
            await self.assert_next_summary_state(salobj.State.DISABLED)
            await self.check_temperature(
                self.remote,
                self.patcher.temperature,
                self.patcher.temperature_setpoint,
            )

            # If we leave DISABLED, the telemetry loop should be closed.
            await self.remote.cmd_standby.start(timeout=STD_TIMEOUT)
            await self.assert_next_summary_state(salobj.State.STANDBY)
            assert self.csc.telemetry_loop_task.done()

    async def test_bin_script(self):
        """Test the CSC command line script, by checking that it starts
        in STANDBY and can be commanded to exit.
        """
        await self.check_bin_script(
            name="FiberSpectrograph",
            index=-1,
            exe_name="run_fiberspectrograph",
            cmdline_args=("--simulate", "3"),
        )


if __name__ == "__main__":
    unittest.main()
