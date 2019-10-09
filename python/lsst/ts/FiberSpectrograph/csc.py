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

__all__ = ["FiberSpectrographCsc"]

import asyncio

from .avsSimulator import AvsSimulator
from .avsFiberSpectrograph import AvsFiberSpectrograph
from lsst.ts.idl.enums.FiberSpectrograph import ExposureState
from lsst.ts import salobj


class FiberSpectrographCsc(salobj.BaseCsc):
    """Commandable SAL Component (CSC) to communicate with the Avantes Fiber
    Spectrograph.

    Parameters
    ----------
    initial_state : `salobj.State` or `int` (optional)
        The initial state of the CSC. This is provided for unit testing,
        as real CSCs should start up in `lsst.ts.salobj.StateSTANDBY`,
        the default.
    initial_simulation_mode : `int` (optional)
        Initial simulation mode.

    Notes
    -----
    **Simulation Modes**

    Supported simulation modes:

    * 0: regular operation
    * 1: simulation mode: start a mock spectrograph library and talk to it
         instead of the real device.

    **Error codes**

    * 1: If there is an error connecting to the spectrograph.
    * 20: If there is an error taking an exposure.
    """
    def __init__(self, initial_state=salobj.State.STANDBY,
                 initial_simulation_mode=0, index=0):
        self._simulator = AvsSimulator()
        self.device = None

        self.telemetry_loop_task = salobj.make_done_future()
        self.telemetry_interval = 10  # seconds between telemetry output

        # TODO DM-21437: we will have to do something with the index here,
        # once we figure out what the various spectrograph indexes are.
        # For example, we'll probably use the index to determine the
        # spectrograph serial number to connect to.
        super().__init__("FiberSpectrograph", index=index,
                         initial_state=initial_state, initial_simulation_mode=initial_simulation_mode)

    def report_summary_state(self):
        try:
            # disabled: connect and send telemetry, but no commands allowed.
            if self.summary_state in (salobj.State.ENABLED, salobj.State.DISABLED):
                if self.device is None:
                    try:
                        self.device = AvsFiberSpectrograph(log=self.log)
                    except Exception as e:
                        msg = "Failed to connect to fiber spectrograph."
                        self.fault(code=1, report=f"{msg}: {repr(e)}")
                        raise salobj.ExpectedError(msg)

                if self.telemetry_loop_task.done():
                    self.telemetry_loop_task = asyncio.create_task(self.telemetry_loop())
                status = self.device.get_status()
                self.evt_deviceInfo.set_put(npixels=status.n_pixels,
                                            fpgaVersion=status.fpga_version,
                                            firmwareVersion=status.firmware_version,
                                            libraryVersion=status.library_version)
            else:
                self.telemetry_loop_task.cancel()
                if self.device is not None:
                    self.device.disconnect()
                self.device = None
        finally:
            # Always report the final state, whatever happens above.
            super().report_summary_state()

    async def close_tasks(self):
        """Kill the telemetry loop if we are closed outside of OFFLINE.

        This keeps tests from emitting warnings about a pending task.
        """
        await super().close_tasks()
        self.telemetry_loop_task.cancel()

    async def telemetry_loop(self):
        """Output telemetry information at regular intervals.

        The primary telemetry from the fiber spectrograph is the temperature.
        """
        while True:
            status = self.device.get_status()
            self.tel_temperature.set_put(temperature=status.temperature,
                                         setpoint=status.temperature_setpoint)
            await asyncio.sleep(self.telemetry_interval)

    async def implement_simulation_mode(self, simulation_mode):
        if simulation_mode == 0:
            self._simulator.stop()
        if simulation_mode == 1:
            self._simulator.start()

    async def do_expose(self, data):
        """Take an exposure with the connected spectrograph.

        **WARNING**
        The output data is currently dropped on the floor, until we have a
        clear path for dealing with the files.

        Parameters
        ----------
        data : `DataType`
            Command data

        Raises
        ------
        asyncio.CancelledError
            Raised if the exposure is cancelled before it completes.
        lsst.ts.salobj.ExpectedError
            Raised if an error occurs while taking the exposure.
        """
        msg = self.device.check_expose_ok(data.duration)
        if msg is not None:
            raise salobj.ExpectedError(msg)
        try:
            task = asyncio.create_task(self.device.expose(data.duration))
            self.evt_exposureState.set_put(status=ExposureState.INTEGRATING)
            wavelength, spectrum = await task
            self.evt_exposureState.set_put(status=ExposureState.DONE)
        except asyncio.CancelledError:
            self.evt_exposureState.set_put(status=ExposureState.CANCELLED)
            raise
        except Exception as e:
            self.evt_exposureState.set_put(status=ExposureState.FAILED)
            msg = "Failed to take exposure with fiber spectrograph."
            self.fault(code=20, report=f"{msg}: {repr(e)}")
            raise salobj.ExpectedError(msg)

    async def do_cancelExposure(self, data):
        """Cancel an ongoing exposure.

        Parameters
        ----------
        data : `DataType`
            Command data
        """
        self.device.stop_exposure()
