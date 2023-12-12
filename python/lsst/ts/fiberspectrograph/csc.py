# This file is part of ts_FiberSpectrograph.
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

__all__ = ["FiberSpectrographCsc", "run_fiberspectrograph"]

import asyncio
import io
import pathlib

import astropy.units as u
from lsst.ts import salobj, utils
from lsst.ts.idl.enums.FiberSpectrograph import ExposureState

from . import __version__, constants, data_manager
from .avs_fiber_spectrograph import AvsFiberSpectrograph
from .avs_simulator import AvsSimulator
from .config_schema import CONFIG_SCHEMA


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
    override : `str`, optional
        Configuration override file to apply if ``initial_state`` is
        `State.DISABLED` or `State.ENABLED`.
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

    valid_simulation_modes = (0, 1, 2, 3)
    simulation_help = (
        "Simulation mode, a bitmask of 2 values: "
        "1: simulate the spectrograph; "
        "2: simulate the s3 large file annex"
    )
    version = __version__

    def __init__(
        self,
        index,
        config_dir=None,
        initial_state=salobj.State.STANDBY,
        override="",
        simulation_mode=0,
    ):
        index = constants.SalIndex(index)
        self._simulator = None
        self.device = None

        self.serial_number = constants.SERIAL_NUMBERS[index]
        # Short name of instrument
        self.band_name = constants.BAND_NAMES[index]
        self.generator_name = f"fiberSpec{self.band_name}"
        self.s3bucket_name = None  # Set by `configure`.
        self.s3bucket = None  # Set by `handle_summary_state`.

        self.data_manager = data_manager.DataManager(
            instrument=f"FiberSpectrograph.{self.band_name}",
            origin=type(self).__name__,
            serial=self.serial_number,
        )
        self.telemetry_loop_task = utils.make_done_future()
        self.telemetry_interval = 10  # seconds between telemetry output

        super().__init__(
            name="FiberSpectrograph",
            index=index,
            config_schema=CONFIG_SCHEMA,
            config_dir=config_dir,
            initial_state=initial_state,
            override=override,
            simulation_mode=simulation_mode,
        )

    @staticmethod
    def get_config_pkg():
        return "ts_config_ocs"

    async def configure(self, config):
        # Make bucket name now, to validate config
        self.s3bucket_name = salobj.AsyncS3Bucket.make_bucket_name(
            s3instance=config.s3instance,
        )
        self.config = config
        self.image_service_client = utils.ImageNameServiceClient(
            config.image_service_url, self.salinfo.index, "FiberSpectrograph"
        )

    async def handle_summary_state(self):
        # disabled: connect and send telemetry, but no commands allowed.
        if self.summary_state in (salobj.State.ENABLED, salobj.State.DISABLED):
            if self.s3bucket is None:
                domock = self.simulation_mode & constants.SimulationMode.S3Server != 0
                self.s3bucket = salobj.AsyncS3Bucket(
                    name=self.s3bucket_name, domock=domock, create=domock
                )
            if self.device is None:
                try:
                    self.device = AvsFiberSpectrograph(
                        serial_number=self.serial_number, log=self.log
                    )
                except Exception as e:
                    msg = "Failed to connect to fiber spectrograph."
                    await self.fault(code=1, report=f"{msg}: {repr(e)}")
                    raise salobj.ExpectedError(msg)

            if self.telemetry_loop_task.done():
                self.telemetry_loop_task = asyncio.create_task(self.telemetry_loop())
            status = self.device.get_status()
            await self.evt_deviceInfo.set_write(
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
        if self._simulator is not None:
            self._simulator.stop()

    async def telemetry_loop(self):
        """Output telemetry information at regular intervals.

        The primary telemetry from the fiber spectrograph is the temperature.
        """
        while True:
            status = self.device.get_status()
            await self.tel_temperature.set_write(
                temperature=status.temperature, setpoint=status.temperature_setpoint
            )
            await asyncio.sleep(self.telemetry_interval)

    async def implement_simulation_mode(self, simulation_mode):
        if simulation_mode & constants.SimulationMode.Spectrograph != 0:
            self._simulator = AvsSimulator()
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
        self.assert_enabled()
        msg = self.device.check_expose_ok(data.duration)
        if msg is not None:
            raise salobj.ExpectedError(msg)
        try:
            date_begin = utils.astropy_time_from_tai_unix(utils.current_tai())
            task = asyncio.create_task(self.device.expose(data.duration))
            await self.evt_exposureState.set_write(status=ExposureState.INTEGRATING)
            wavelength, spectrum = await task
            date_end = utils.astropy_time_from_tai_unix(utils.current_tai())
            await self.evt_exposureState.set_write(status=ExposureState.DONE)
            temperature = self.tel_temperature.data.temperature * u.deg_C
            setpoint = self.tel_temperature.data.setpoint * u.deg_C
            n_pixels = self.evt_deviceInfo.data.npixels
            spec_data = data_manager.SpectrographData(
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
            await self.evt_exposureState.set_write(status=ExposureState.TIMEDOUT)
            msg = f"Timeout waiting for exposure: {repr(e)}"
            await self.fault(code=20, report=msg)
            raise salobj.ExpectedError(msg)
        except asyncio.CancelledError:
            await self.evt_exposureState.set_write(status=ExposureState.CANCELLED)
            raise
        except Exception as e:
            await self.evt_exposureState.set_write(status=ExposureState.FAILED)
            msg = f"Failed to take exposure with fiber spectrograph: {repr(e)}"
            await self.fault(code=20, report=msg)
            raise salobj.ExpectedError(msg)

        await self.save_data(spec_data)

    async def save_data(self, spec_data):
        """Save a spectrograph FITS file to the LFA, if possible.

        If the S3 upload fails then try to save the file locally to /tmp.
        The ``largeFileObjectAvailable`` event is written only if S3
        upload succeeds.
        """
        hdulist = self.data_manager.make_hdulist(spec_data)
        image_sequence_array, data = await self.image_service_client.get_next_obs_id(
            num_images=1
        )
        hdulist[0].header["OBSID"] = data[0]
        hdulist[0].header["TELCODE"] = self.config.location
        hdulist[0].header["SEQNUM"] = int(image_sequence_array[0])
        hdulist[0].header["CONTRLLR"] = data[0].split("_")[0]
        fileobj = io.BytesIO()
        hdulist.writeto(fileobj)
        fileobj.seek(0)
        date_begin = spec_data.date_begin
        key = self.s3bucket.make_key(
            salname=self.salinfo.name,
            salindexname=self.band_name,
            generator=self.generator_name,
            date=date_begin,
            suffix=".fits",
        )
        try:
            await self.s3bucket.upload(fileobj=fileobj, key=key)
            url = f"{self.s3bucket.service_resource.meta.client.meta.endpoint_url}/{self.s3bucket.name}/{key}"
            await self.evt_largeFileObjectAvailable.set_write(
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
                await self.evt_largeFileObjectAvailable.set_write(
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


def run_fiberspectrograph():
    """Run the FiberSpectrograph CSC."""
    asyncio.run(FiberSpectrographCsc.amain(index=True))
