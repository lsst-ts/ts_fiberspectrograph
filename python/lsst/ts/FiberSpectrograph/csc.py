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
import io
import pathlib

import astropy.units as u

from . import constants
from .avsSimulator import AvsSimulator
from .avsFiberSpectrograph import AvsFiberSpectrograph
from . import dataManager
from lsst.ts.idl.enums.FiberSpectrograph import ExposureState
from lsst.ts import salobj


class FiberSpectrographCsc(salobj.ConfigurableCsc):
    """Commandable SAL Component (CSC) to communicate with the Avantes Fiber
    Spectrograph.

    Parameters
    ----------
    index : `int`
        The SAL index; this determines which spectrograph to connect to.
        See the ``FiberSpectrograph`` Enumeration in
        ``ts_xml/sal_interfaces/SALSubsystems.xml`` for index:name mapping.
        index=-1 means use the only connected spectrograph.
    config_dir : `str` (optional)
        Directory of configuration files, or None for the standard
        configuration directory (obtained from `get_default_config_dir`).
        This is provided for unit testing.
    initial_state : `salobj.State` or `int`, optional
        The initial state of the CSC. This is provided for unit testing,
        as real CSCs should start up in `lsst.ts.salobj.StateSTANDBY`,
        the default.
    simulation_mode : `int`, optional
        Simulation mode.

    Notes
    -----
    **Simulation Modes**

    Supported simulation modes are a `SimulationMode` bitmask.

    **Error codes**

    * 1: If there is an error connecting to the spectrograph.
    * 20: If there is an error taking an exposure.
    """

    def __init__(
        self,
        index,
        config_dir=None,
        initial_state=salobj.State.STANDBY,
        simulation_mode=0,
    ):
        index = constants.SalIndex(index)
        schema_path = (
            pathlib.Path(__file__)
            .resolve()
            .parents[4]
            .joinpath("schema", "FiberSpectrograph.yaml")
        )
        self._simulator = AvsSimulator()
        self.device = None

        self.serial_number = constants.SERIAL_NUMBERS[index]
        # Short name of instrument
        self.band_name = constants.BAND_NAMES[index]
        self.generator_name = f"fiberSpec{self.band_name}"
        self.s3bucket_name = None  # Set by `configure`.
        self.s3bucket = None  # Set by `handle_summary_state`.

        self.data_manager = dataManager.DataManager(
            instrument=f"FiberSpectrograph.{self.band_name}", origin=type(self).__name__
        )
        self.telemetry_loop_task = salobj.make_done_future()
        self.telemetry_interval = 10  # seconds between telemetry output

        super().__init__(
            name="FiberSpectrograph",
            index=index,
            schema_path=schema_path,
            config_dir=config_dir,
            initial_state=initial_state,
            simulation_mode=simulation_mode,
        )

    @staticmethod
    def get_config_pkg():
        return "ts_config_ocs"

    async def configure(self, config):
        # Make bucket name now, to validate config
        self.s3bucket_name = salobj.AsyncS3Bucket.make_bucket_name(
            salname=self.salinfo.name,
            salindexname=self.band_name,
            s3instance=config.s3instance,
        )
        self.config = config

    async def handle_summary_state(self):
        # disabled: connect and send telemetry, but no commands allowed.
        if self.summary_state in (salobj.State.ENABLED, salobj.State.DISABLED):
            if self.s3bucket is None:
                domock = self.simulation_mode & constants.SimulationMode.S3Server != 0
                self.s3bucket = salobj.AsyncS3Bucket(
                    name=self.s3bucket_name, domock=domock
                )
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
            if self.s3bucket is not None:
                self.s3bucket.stop_mock()
            self.s3bucket = None

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
        if simulation_mode < 0 or simulation_mode > sum(constants.SimulationMode):
            raise ValueError(f"Unsupported simulation_mode {simulation_mode}")
        if simulation_mode & constants.SimulationMode.Spectrograph != 0:
            self._simulator.start()
        else:
            self._simulator.stop()

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
        self.assert_enabled()
        msg = self.device.check_expose_ok(data.duration)
        if msg is not None:
            raise salobj.ExpectedError(msg)
        try:
            date_begin = salobj.astropy_time_from_tai_unix(salobj.current_tai())
            task = asyncio.create_task(self.device.expose(data.duration))
            self.evt_exposureState.set_put(status=ExposureState.INTEGRATING)
            wavelength, spectrum = await task
            date_end = salobj.astropy_time_from_tai_unix(salobj.current_tai())
            self.evt_exposureState.set_put(status=ExposureState.DONE)
            temperature = self.tel_temperature.data.temperature * u.deg_C
            setpoint = self.tel_temperature.data.setpoint * u.deg_C
            n_pixels = self.evt_deviceInfo.data.npixels
            spec_data = dataManager.SpectrographData(
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

        await self.save_data(spec_data)

    async def save_data(self, spec_data):
        """Save a spectrograph FITS file to the LFA, if possible.

        If the S3 upload fails then try to save the file locally to /tmp.
        The ``largeFileObjectAvailable`` event is written only if S3
        upload succeeds.
        """
        hdulist = self.data_manager.make_hdulist(spec_data)
        fileobj = io.BytesIO()
        hdulist.writeto(fileobj)
        fileobj.seek(0)
        date_begin = spec_data.date_begin
        key = self.s3bucket.make_key(
            salname=self.salinfo.name, generator=self.generator_name, date=date_begin
        )
        try:
            await self.s3bucket.upload(fileobj=fileobj, key=key)
            url = f"s3://{self.s3bucket.name}/{key}"
            self.evt_largeFileObjectAvailable.set_put(
                url=url, generator=self.generator_name
            )
        except Exception:
            self.log.exception(
                f"Could not upload FITS file {key} to S3; trying to save to local disk."
            )
            try:
                filepath = pathlib.Path("/tmp") / self.s3bucket.name / key
                dirpath = filepath.parent
                if not dirpath.exists():
                    self.log.info(f"Create {str(dirpath)}")
                    dirpath.mkdir(parents=True, exist_ok=True)

                hdulist.writeto(filepath)
                self.evt_largeFileObjectAvailable.set_put(
                    url=filepath.as_uri(), generator=self.generator_name
                )
            except Exception:
                self.log.exception(
                    "Could not save the FITS file locally, either. The data is lost."
                )
                raise

    async def do_cancelExposure(self, data):
        """Cancel an ongoing exposure.

        Parameters
        ----------
        data : `DataType`
            Command data
        """
        self.assert_enabled()
        self.device.stop_exposure()
