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

import asyncio
import unittest
import shutil

import asynctest

from lsst.ts import salobj
from lsst.ts.FiberSpectrograph import AvsSimulator
from lsst.ts.FiberSpectrograph import FiberSpectrographCsc
from lsst.ts.FiberSpectrograph import AvsReturnError, AvsReturnCode
from lsst.ts.idl.enums.FiberSpectrograph import ExposureState

STD_TIMEOUT = 2  # standard command timeout (sec)
LONG_TIMEOUT = 20  # timeout for starting SAL components (sec)


class Harness:
    """An configurable async context manager for setting up and starting a CSC,
    and any other pieces it needs to talk to."""
    def __init__(self, initial_state, config_dir=None):
        self.csc = FiberSpectrographCsc(
            initial_state=initial_state,
            initial_simulation_mode=0)
        self.remote = salobj.Remote(domain=self.csc.domain, name="FiberSpectrograph", index=0)

    async def __aenter__(self):
        await self.csc.start_task
        await self.remote.start_task
        return self

    async def __aexit__(self, *args):
        await self.csc.close()
        await self.remote.close()


class TestFiberSpectrographCsc(asynctest.TestCase):
    """Test the functionality of the FiberSpectrographCsc, using a mocked
    spectrograph connection.

    These tests use an instance of `lsst.ts.FiberSpectrograph.AvsSimulator`,
    to mock patch the fiber spectrograph vendor C library.
    The CSC uses the same simulator class when in "simulation mode" to simulate
    the fiber spectrograph, but that simulator is held independently of the
    mock patch used for testing here.
    Having the CSC patch the AVS library (when going into simulation mode)
    separately from the unit test patching the same library allows us to test
    the functionality of turning simulation mode on and off; we want to treat
    the use of `unittest.mock` by the CSC simulator as an internal detail.
    """
    def setUp(self):
        salobj.set_random_lsst_dds_domain()
        self.patcher = AvsSimulator()
        self.patch = self.patcher.start(testCase=self)

    async def check_exposureState(self, remote, expect):
        """Check the value of the ExposureState event."""
        state = await remote.evt_exposureState.next(flush=False, timeout=STD_TIMEOUT)
        self.assertEqual(state.status, expect)

    async def check_summaryState(self, remote, expect):
        """Check the value of the SummaryState event."""
        state = await remote.evt_summaryState.next(flush=False, timeout=STD_TIMEOUT)
        self.assertEqual(state.summaryState, expect)

    async def check_temperature(self, remote, temperature, setpoint):
        """Check the value of the temperature telemetry."""
        state = await remote.tel_temperature.next(flush=False, timeout=STD_TIMEOUT)
        self.assertAlmostEqual(state.temperature, temperature)
        self.assertAlmostEqual(state.setpoint, setpoint)

    async def test_state_changes(self):
        """Test that state changes connect/disconnect the spectrograph
        correctly.
        """
        async with Harness(initial_state=salobj.State.STANDBY) as harness:
            # in STANDBY, there should be no connected device
            await self.check_summaryState(harness.remote, salobj.State.STANDBY)
            self.assertIsNone(harness.csc.device)

            # In DISABLED, there should be a connected device.
            await harness.remote.cmd_start.start(timeout=STD_TIMEOUT)
            await self.check_summaryState(harness.remote, salobj.State.DISABLED)
            self.assertIsNotNone(harness.csc.device)
            # we only should try to activate once in this whole sequence
            self.patch.return_value.AVS_Activate.assert_called_once()
            # Switching to DISABLED should output the deviceInfo event
            state = await harness.remote.evt_deviceInfo.next(flush=False, timeout=STD_TIMEOUT)
            self.assertEqual(state.npixels, self.patcher.n_pixels)
            self.assertEqual(state.fpgaVersion, self.patcher.fpga_version)
            self.assertEqual(state.firmwareVersion, self.patcher.firmware_version)
            self.assertEqual(state.libraryVersion, self.patcher.library_version)

            # In ENABLED, there should still be a connected device.
            await harness.remote.cmd_enable.start(timeout=STD_TIMEOUT)
            await self.check_summaryState(harness.remote, salobj.State.ENABLED)
            self.assertIsNotNone(harness.csc.device)
            # we only should try to activate once in this whole sequence
            self.patch.return_value.AVS_Activate.assert_called_once()

            # In DISABLED, there should still be a connected device.
            await harness.remote.cmd_disable.start(timeout=STD_TIMEOUT)
            await self.check_summaryState(harness.remote, salobj.State.DISABLED)
            self.assertIsNotNone(harness.csc.device)
            # we only should try to activate once in this whole sequence
            self.patch.return_value.AVS_Activate.assert_called_once()

            # in STANDBY, there should be no connected device
            await harness.remote.cmd_standby.start(timeout=STD_TIMEOUT)
            await self.check_summaryState(harness.remote, salobj.State.STANDBY)
            self.assertIsNone(harness.csc.device)
            # Entering standby should close the connection; Done might be
            # called twice: once for the explicit `disconnect()` and  once
            # for the destruction of the device object (but due to python
            # garbage collection, the latter is not guaranteed to have happened
            # immediately).
            self.patch.return_value.AVS_Done.assert_called()

    async def test_enable_fails(self):
        """Test that exceptions raised when connecting cause a fault when
        switching the CSC from STANDBY to DISABLED.
        """
        self.patch.return_value.AVS_Activate.return_value = AvsReturnCode.invalidHandle.value
        async with Harness(initial_state=salobj.State.STANDBY) as harness:
            # Check that we are properly in STANDBY at the start
            await self.check_summaryState(harness.remote, salobj.State.STANDBY)

            msg = "Failed to connect"
            with salobj.assertRaisesAckError(ack=salobj.SalRetCode.CMD_FAILED, result_contains=msg):
                await harness.remote.cmd_start.start(timeout=STD_TIMEOUT)
            await self.check_summaryState(harness.remote, salobj.State.FAULT)
            error = await harness.remote.evt_errorCode.next(flush=False, timeout=STD_TIMEOUT)
            self.assertIn("RuntimeError", error.errorReport)
            self.assertIn("Invalid device handle; cannot activate device", error.errorReport)
            self.assertIsNone(harness.csc.device)

    async def test_expose(self):
        """Test that we can take an exposure and that appropriate events are
        emitted.
        """
        async with Harness(initial_state=salobj.State.ENABLED) as harness:
            # Check that we are properly in ENABLED at the start
            await self.check_summaryState(harness.remote, salobj.State.ENABLED)

            duration = 2  # seconds
            task = asyncio.create_task(harness.remote.cmd_expose.set_start(timeout=STD_TIMEOUT+duration,
                                                                           duration=duration))
            await self.check_exposureState(harness.remote, ExposureState.INTEGRATING)
            # Wait for the exposure to finish.
            await task
            await self.check_exposureState(harness.remote, ExposureState.DONE)

    async def test_expose_fails(self):
        """Test that a failed exposure puts us in the FAULT state, which will
        disconnect the device.
        """
        # Make `GetScopeData` (which is called to get the measured output from
        # the device) return an error code, so that the device controller
        # raises an exception inside `expose()`.
        self.patch.return_value.AVS_GetScopeData.side_effect = None
        self.patch.return_value.AVS_GetScopeData.return_value = AvsReturnCode.ERR_INVALID_MEAS_DATA.value
        async with Harness(initial_state=salobj.State.ENABLED) as harness:
            # Check that we are properly in ENABLED at the start.
            await self.check_summaryState(harness.remote, salobj.State.ENABLED)

            msg = "Failed to take exposure"
            with salobj.assertRaisesAckError(ack=salobj.SalRetCode.CMD_FAILED, result_contains=msg):
                await harness.remote.cmd_expose.set_start(timeout=STD_TIMEOUT, duration=.5)
            # The exposure state should be Integrating during the exposure.
            await self.check_exposureState(harness.remote, ExposureState.INTEGRATING)
            # The exposure state should be Failed after the exposure has
            # completed, because GetScopeData returned an error code.
            await self.check_summaryState(harness.remote, salobj.State.FAULT)
            error = await harness.remote.evt_errorCode.next(flush=False, timeout=STD_TIMEOUT)
            errorMsg = str(AvsReturnError(AvsReturnCode.ERR_INVALID_MEAS_DATA.value, "GetScopeData"))
            self.assertIn(errorMsg, error.errorReport)
            # Going into FAULT should close the device connection.
            self.assertIsNone(harness.csc.device)
            # the exposure state should be FAILED after a failed exposure
            await self.check_exposureState(harness.remote, ExposureState.FAILED)

    async def test_cancelExposure(self):
        """Test that we can stop an active exposure, and that the exposureState
        is changed appropriately.
        """
        async with Harness(initial_state=salobj.State.ENABLED) as harness:
            # Check that we are properly in ENABLED at the start
            await self.check_summaryState(harness.remote, salobj.State.ENABLED)

            duration = 5  # seconds
            task = asyncio.create_task(harness.remote.cmd_expose.set_start(timeout=STD_TIMEOUT + duration,
                                                                           duration=duration))
            # Wait for the exposure to start integrating.
            await self.check_exposureState(harness.remote, ExposureState.INTEGRATING)
            await harness.remote.cmd_cancelExposure.set_start(timeout=STD_TIMEOUT)
            with salobj.assertRaisesAckError(ack=salobj.SalRetCode.CMD_ABORTED):
                await task
            await self.check_exposureState(harness.remote, ExposureState.CANCELLED)

    async def test_simulator(self):
        """Test that we can turn the simulation mode on and off.

        We know we are in simulation mode if the device "library" loaded by
        the device is a different mock than `self.patch`, because the simulator
        that the CSC holds is independent of the mock patch that is created
        in `setUp` for these tests.
        """
        async with Harness(initial_state=salobj.State.STANDBY) as harness:
            # Check that we are properly in STANDBY at the start
            await self.check_summaryState(harness.remote, salobj.State.STANDBY)
            self.assertIsNone(harness.csc.device)

            setsm_data = harness.remote.cmd_setSimulationMode.DataType()
            setsm_data.mode = 1
            await harness.remote.cmd_setSimulationMode.start(setsm_data, timeout=STD_TIMEOUT)
            # nothing should happen until we switch to DISABLED
            self.assertIsNone(harness.csc.device)

            await harness.remote.cmd_start.start(timeout=STD_TIMEOUT)
            await self.check_summaryState(harness.remote, salobj.State.DISABLED)
            # The CSC's internal simulator should be different from our mock.
            self.assertNotEqual(self.patch.return_value, harness.csc.device.libavs)

            # It should remain different in ENABLED, and back to DISABLED
            await harness.remote.cmd_enable.start(timeout=STD_TIMEOUT)
            await self.check_summaryState(harness.remote, salobj.State.ENABLED)
            self.assertNotEqual(self.patch.return_value, harness.csc.device.libavs)
            await harness.remote.cmd_disable.start(timeout=STD_TIMEOUT)
            await self.check_summaryState(harness.remote, salobj.State.DISABLED)
            self.assertNotEqual(self.patch.return_value, harness.csc.device.libavs)

            # in STANDBY, there should be no connected device
            await harness.remote.cmd_standby.start(timeout=STD_TIMEOUT)
            await self.check_summaryState(harness.remote, salobj.State.STANDBY)
            self.assertIsNone(harness.csc.device)

            # Turning the simulator off should give us the test patch again.
            setsm_data = harness.remote.cmd_setSimulationMode.DataType()
            setsm_data.mode = 0
            await harness.remote.cmd_setSimulationMode.start(setsm_data, timeout=STD_TIMEOUT)
            self.assertIsNone(harness.csc.device)
            await harness.remote.cmd_start.start(timeout=STD_TIMEOUT)
            await self.check_summaryState(harness.remote, salobj.State.DISABLED)
            self.assertEqual(self.patch.return_value, harness.csc.device.libavs)

    async def test_telemetry(self):
        """Test that telemetry is emitted in the correct states.

        Notes
        -----
        If the CSC does not close the telemetry loop when the CSC is
        destroyed (e.g. via `close_tasks()`), you will see messages like
        `Task was destroyed but it is pending!` in the test output.
        """
        async with Harness(initial_state=salobj.State.DISABLED) as harness:
            # Check that we are properly in STANDBY at the start
            await self.check_summaryState(harness.remote, salobj.State.DISABLED)
            await self.check_temperature(harness.remote,
                                         self.patcher.temperature,
                                         self.patcher.temperature_setpoint)

            # If we leave DISABLED, the telemetry loop should be closed.
            await harness.remote.cmd_standby.start(timeout=STD_TIMEOUT)
            await self.check_summaryState(harness.remote, salobj.State.STANDBY)
            self.assertTrue(harness.csc.telemetry_loop_task.done())

    async def test_run(self):
        """Test running the CSC commandline script, by checking that it starts
        in STANDBY and can be commanded to exit.
        """
        index = 1
        exe_name = "run_FiberSpectrograph.py"
        exe_path = shutil.which(exe_name)
        if exe_path is None:
            self.fail(f"Could not find bin script {exe_name}; did you setup and scons this package?")

        process = await asyncio.create_subprocess_exec(exe_name, str(index))
        try:
            async with salobj.Domain() as domain:
                remote = salobj.Remote(domain=domain, name="FiberSpectrograph", index=index)
                summaryState_data = await remote.evt_summaryState.next(flush=False, timeout=LONG_TIMEOUT)
                self.assertEqual(summaryState_data.summaryState, salobj.State.STANDBY)

                ack = await remote.cmd_exitControl.start(timeout=STD_TIMEOUT)
                self.assertEqual(ack.ack, salobj.SalRetCode.CMD_COMPLETE)
                summaryState_data = await remote.evt_summaryState.next(flush=False, timeout=LONG_TIMEOUT)
                self.assertEqual(summaryState_data.summaryState, salobj.State.OFFLINE)

                await asyncio.wait_for(process.wait(), 5)
        except Exception:
            if process.returncode is None:
                process.terminate()
            raise


if __name__ == "__main__":
    unittest.main()
