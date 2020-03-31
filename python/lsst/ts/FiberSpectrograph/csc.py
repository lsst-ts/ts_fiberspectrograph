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

__all__ = ["FiberSpectrographCsc", "serial_numbers"]

import asyncio

import astropy.time
import astropy.units as u

from .avsSimulator import AvsSimulator
from .avsFiberSpectrograph import AvsFiberSpectrograph
from . import dataManager
from lsst.ts.idl.enums.FiberSpectrograph import ExposureState
from lsst.ts import salobj

# The instrument names to be accessed by index number.
instruments = {-1: "unknown", 1: "MTBlue", 2: "MTRed", 3: "ATBroad"}

# The serial numbers of the above instruments.
# index=-1 means "use the only connected spectrograph."
serial_numbers = {-1: None, 1: "1606192U1", 2: "1606190U1", 3: "1606191U1"}


class FiberSpectrographCsc(salobj.BaseCsc):
    """Commandable SAL Component (CSC) to communicate with the Avantes Fiber
    Spectrograph.

    Parameters
    ----------
    initial_state : `salobj.State` or `int`, optional
        The initial state of the CSC. This is provided for unit testing,
        as real CSCs should start up in `lsst.ts.salobj.StateSTANDBY`,
        the default.
    initial_simulation_mode : `int`, optional
        Initial simulation mode.
    outpath : `str`, optional
        Write output files to this path.
        TODO: this is temporary until we have a working LFA.
    index : `int`
        The SAL index; this determines which spectrograph to connect to.
        See the ``FiberSpectrograph`` Enumeration in
        ``ts_xml/sal_interfaces/SALSubsystems.xml`` for index:name mapping.
        index=-1 means use the only connected spectrograph.

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

    def __init__(
        self,
        initial_state=salobj.State.STANDBY,
        initial_simulation_mode=0,
        outpath=None,
        *,
        index,
    ):
        self._simulator = AvsSimulator()
        self.device = None

        self.serial_number = serial_numbers[index]
        self.name = instruments[index]

        self.data_manager = dataManager.DataManager(
            instrument=self.name, origin=type(self).__name__, outpath=outpath
        )
        self.telemetry_loop_task = salobj.make_done_future()
        self.telemetry_interval = 10  # seconds between telemetry output

        super().__init__(
            "FiberSpectrograph",
            index=index,
            initial_state=initial_state,
            initial_simulation_mode=initial_simulation_mode,
        )

    async def handle_summary_state(self):
        # disabled: connect and send telemetry, but no commands allowed.
        if self.summary_state in (salobj.State.ENABLED, salobj.State.DISABLED):
            if self.device is None:
                try:
                    self.device = AvsFiberSpectrograph(
                        serial_number=self.serial_number, log=self.log
                    )
                except Exception as e:
                    msg = "Failed to connect to fiber spectrograph."
                    self.fault(code=1, report=f"{msg}: {repr(e)}")
                    raise salobj.ExpectedError(msg)

            if self.telemetry_loop_task.done():
                self.telemetry_loop_task = asyncio.create_task(self.telemetry_loop())
            status = self.device.get_status()
            self.evt_deviceInfo.set_put(
                npixels=status.n_pixels,
                fpgaVersion=status.fpga_version,
                firmwareVersion=status.firmware_version,
                libraryVersion=status.library_version,
            )
        else:
            self.telemetry_loop_task.cancel()
            if self.device is not None:
                self.device.disconnect()
            self.device = None

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
            self.tel_temperature.set_put(
                temperature=status.temperature, setpoint=status.temperature_setpoint
            )
            await asyncio.sleep(self.telemetry_interval)

    async def implement_simulation_mode(self, simulation_mode):
        if simulation_mode == 0:
            self._simulator.stop()
        if simulation_mode == 1:
            self._simulator.start()

    async def do_expose(self, data):
        """Take an exposure with the connected spectrograph.

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
            date_begin = astropy.time.Time.now()
            task = asyncio.create_task(self.device.expose(data.duration))
            self.evt_exposureState.set_put(status=ExposureState.INTEGRATING)
            wavelength, spectrum = await task
            date_end = astropy.time.Time.now()
            self.evt_exposureState.set_put(status=ExposureState.DONE)
            temperature = self.tel_temperature.data.temperature * u.deg_C
            setpoint = self.tel_temperature.data.setpoint * u.deg_C
            n_pixels = self.evt_deviceInfo.data.npixels
            specData = dataManager.SpectrographData(
                wavelength=wavelength,
                spectrum=spectrum,
                duration=data.duration,
                date_begin=date_begin,
                date_end=date_end,
                type=data.type,
                source=data.source,
                temperature=temperature,
                temperature_setpoint=setpoint,
                n_pixels=n_pixels,
            )
            output = self.data_manager(specData)
            self.evt_largeFileObjectAvailable.set_put(url=output)
        except asyncio.TimeoutError as e:
            self.evt_exposureState.set_put(status=ExposureState.TIMEDOUT)
            msg = f"Timeout waiting for exposure: {repr(e)}"
            self.fault(code=20, report=msg)
            raise salobj.ExpectedError(msg)
        except asyncio.CancelledError:
            self.evt_exposureState.set_put(status=ExposureState.CANCELLED)
            raise
        except Exception as e:
            self.evt_exposureState.set_put(status=ExposureState.FAILED)
            msg = f"Failed to take exposure with fiber spectrograph: {repr(e)}"
            self.fault(code=20, report=msg)
            raise salobj.ExpectedError(msg)

    async def do_cancelExposure(self, data):
        """Cancel an ongoing exposure.

        Parameters
        ----------
        data : `DataType`
            Command data
        """
        self.device.stop_exposure()
