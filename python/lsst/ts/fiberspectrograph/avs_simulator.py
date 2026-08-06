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

"""An in-process simulator for the Avantes AvaSpec library."""

__all__ = ["AvsSimulator"]

from collections import Counter

import numpy as np

from . import constants
from .avs_fiber_spectrograph import AvsDeviceStatus, AvsIdentity


class AvsSimulator:
    """Simulate the subset of ``libavs`` used by the CSC.

    The simulator retains only device state, return-code overrides, scalar
    call counts, and the most recent measurement configuration. It never
    retains call arguments, so telemetry can run indefinitely.

    Parameters
    ----------
    serial_number : `str`, optional
        Serial number of the simulated device. Defaults to the red
        spectrograph serial number.

    Notes
    -----
    Set ``return_codes[method_name]`` to replace a method's documented
    default return value, or ``exceptions[method_name]`` to raise an
    exception from that method. Each call is counted in ``call_counts``.
    """

    def __init__(self, serial_number=None):
        if serial_number is None:
            serial_number = constants.SERIAL_NUMBERS[constants.SalIndex.RED]
        self.serial_number = serial_number
        self.handle = 314159
        self.id0 = AvsIdentity(
            bytes(str(self.serial_number), "ascii"),
            b"Fake Spectrograph",
            AvsDeviceStatus.USB_AVAILABLE.value,
        )
        self.devices = [self.id0]

        self.n_pixels = 2048
        self.temperature_setpoint = 5
        self.tec_coefficients = np.array((1, 2, 0, 0.0, 0), dtype=np.float32)
        self.tec_voltage = 2
        self.temperature = sum(coeff * self.tec_voltage**i for i, coeff in enumerate(self.tec_coefficients))
        self.fpga_version = "fpga12345678901"
        self.firmware_version = "firmware123456"
        self.library_version = "library123456"
        self.wavelength = np.arange(self.n_pixels)
        self.spectrum = np.arange(self.n_pixels) * 2
        self.polls_until_ready = 3
        self.polls_since_measure = 0
        self.measure_config_sent = None

        self.return_codes = {}
        self.exceptions = {}
        self.call_counts = Counter()

    def _result(self, name, default=0):
        """Record a call and return its configured or default result.

        Parameters
        ----------
        name : `str`
            Name of the simulated AvaSpec method.
        default : `int` or `bool`, optional
            Result returned when no override is configured.

        Returns
        -------
        result : `int` or `bool`
            The value in ``return_codes[name]``, if present; otherwise
            ``default``.

        Raises
        ------
        Exception
            Raised when ``exceptions[name]`` contains an exception.
        """
        self.call_counts[name] += 1
        exception = self.exceptions.get(name)
        if exception is not None:
            raise exception
        return self.return_codes.get(name, default)

    def AVS_Init(self, port):
        """Initialize the simulated AvaSpec USB library.

        Parameters
        ----------
        port : `int`
            AvaSpec USB port selector. It is accepted but not used by the
            simulator.

        Returns
        -------
        return_code : `int`
            Number of simulated devices, unless overridden.

        Raises
        ------
        Exception
            Raised when an exception override is configured.
        """
        return self._result("AVS_Init", len(self.devices))

    def AVS_Done(self):
        """Release the simulated AvaSpec library.

        Returns
        -------
        return_code : `int`
            Zero, unless overridden.

        Raises
        ------
        Exception
            Raised when an exception override is configured.
        """
        return self._result("AVS_Done")

    def AVS_UpdateUSBDevices(self):
        """Refresh the simulated USB-device list.

        Returns
        -------
        return_code : `int`
            Number of simulated devices, unless overridden.

        Raises
        ------
        Exception
            Raised when an exception override is configured.
        """
        return self._result("AVS_UpdateUSBDevices", len(self.devices))

    def AVS_GetList(self, list_size, required_size, device_list):
        """Populate a caller-provided buffer with simulated devices.

        Parameters
        ----------
        list_size : `int`
            Size of ``device_list`` in bytes. Accepted but not validated.
        required_size : `ctypes.POINTER(ctypes.c_uint)`
            Pointer for the required buffer size. Accepted but not modified.
        device_list : sequence of `AvsIdentity`
            Output buffer populated with ``devices`` on a nonnegative result.

        Returns
        -------
        result : `int`
            Zero, unless overridden.

        Raises
        ------
        Exception
            Raised when an exception override is configured.
        """
        result = self._result("AVS_GetList")
        if result >= 0:
            for index, device in enumerate(self.devices):
                device_list[index] = device
        return result

    def AVS_Activate(self, device):
        """Activate a simulated device.

        Parameters
        ----------
        device : `AvsIdentity`
            Device identity to activate. Accepted but not validated.

        Returns
        -------
        handle : `int`
            The simulated device handle (``314159``), unless overridden.

        Raises
        ------
        Exception
            Raised when an exception override is configured.
        """
        return self._result("AVS_Activate", self.handle)

    def AVS_Deactivate(self, handle):
        """Deactivate a simulated device.

        Parameters
        ----------
        handle : `int`
            Device handle to deactivate. Accepted but not validated.

        Returns
        -------
        result : `bool`
            `True`, unless overridden.

        Raises
        ------
        Exception
            Raised when an exception override is configured.
        """
        return self._result("AVS_Deactivate", True)

    def AVS_GetNumPixels(self, handle, n_pixels):
        """Write the simulated detector pixel count to an output pointer.

        Parameters
        ----------
        handle : `int`
            Device handle. Accepted but not validated.
        n_pixels : `ctypes.POINTER(ctypes.c_ushort)`
            Output pointer set to ``self.n_pixels`` on a nonnegative result.

        Returns
        -------
        result : `int`
            Zero, unless overridden.

        Raises
        ------
        Exception
            Raised when an exception override is configured.
        """
        result = self._result("AVS_GetNumPixels")
        if result >= 0:
            n_pixels.contents.value = self.n_pixels
        return result

    def AVS_GetVersionInfo(self, handle, fpga_version, firmware_version, library_version):
        """Write simulated FPGA, firmware, and library version strings.

        Parameters
        ----------
        handle : `int`
            Device handle. Accepted but not validated.
        fpga_version : writable byte buffer
            Output buffer set to the simulated FPGA version on a nonnegative
            result.
        firmware_version : writable byte buffer
            Output buffer set to the simulated firmware version on a
            nonnegative result.
        library_version : writable byte buffer
            Output buffer set to the simulated library version on a
            nonnegative result.

        Returns
        -------
        result : `int`
            Zero, unless overridden.

        Raises
        ------
        Exception
            Raised when an exception override is configured.
        """
        result = self._result("AVS_GetVersionInfo")
        if result >= 0:
            fpga_version[:15] = self.fpga_version.encode("ascii")
            firmware_version[:14] = self.firmware_version.encode("ascii")
            library_version[:13] = self.library_version.encode("ascii")
        return result

    def AVS_GetParameter(self, handle, size, required_size, config):
        """Write simulated device configuration values.

        Parameters
        ----------
        handle : `int`
            Device handle. Accepted but not validated.
        size : `int`
            Size of ``config`` in bytes. Accepted but not validated.
        required_size : `ctypes.POINTER(ctypes.c_uint)`
            Pointer for the required configuration size. Accepted but not
            modified.
        config : `AvsDeviceConfig`
            Configuration structure populated on a nonnegative result.

        Returns
        -------
        result : `int`
            Zero, unless overridden.

        Raises
        ------
        Exception
            Raised when an exception override is configured.
        """
        result = self._result("AVS_GetParameter")
        if result >= 0:
            config.Detector_m_NrPixels = self.n_pixels
            config.TecControl_m_Setpoint = self.temperature_setpoint
            config.Temperature_3_m_aFit[:] = self.tec_coefficients
        return result

    def AVS_GetAnalogIn(self, handle, analog_in_id, voltage):
        """Read a simulated analog-input voltage.

        Parameters
        ----------
        handle : `int`
            Device handle. Accepted but not validated.
        analog_in_id : `int`
            Analog input identifier. Only input ``0`` populates ``voltage``.
        voltage : `ctypes.POINTER(ctypes.c_float)`
            Output pointer set to ``self.tec_voltage`` for input ``0`` on a
            nonnegative result.

        Returns
        -------
        result : `int`
            Zero, unless overridden.

        Raises
        ------
        Exception
            Raised when an exception override is configured.
        """
        result = self._result("AVS_GetAnalogIn")
        if result >= 0 and analog_in_id == 0:
            voltage.contents.value = self.tec_voltage
        return result

    def AVS_PrepareMeasure(self, handle, config):
        """Store a measurement configuration for the next exposure.

        Parameters
        ----------
        handle : `int`
            Device handle. Accepted but not validated.
        config : `AvsMeasureConfig`
            Measurement configuration saved as ``measure_config_sent`` on a
            nonnegative result.

        Returns
        -------
        result : `int`
            Zero, unless overridden.

        Raises
        ------
        Exception
            Raised when an exception override is configured.
        """
        result = self._result("AVS_PrepareMeasure")
        if result >= 0:
            self.measure_config_sent = config
        return result

    def AVS_Measure(self, handle, window_handle, measurements):
        """Start a simulated measurement.

        Parameters
        ----------
        handle : `int`
            Device handle. Accepted but not validated.
        window_handle : `int`
            Callback window handle. Accepted but not used.
        measurements : `int`
            Number of measurements to acquire. Accepted but not used.

        Returns
        -------
        result : `int`
            Zero, unless overridden. A nonnegative result resets the poll
            counter.

        Raises
        ------
        Exception
            Raised when an exception override is configured.
        """
        result = self._result("AVS_Measure")
        if result >= 0:
            self.polls_since_measure = 0
        return result

    def AVS_GetLambda(self, handle, wavelength):
        """Write the simulated wavelength array to an output buffer.

        Parameters
        ----------
        handle : `int`
            Device handle. Accepted but not validated.
        wavelength : writable sequence of `float`
            Output buffer populated with ``self.wavelength`` on a
            nonnegative result.

        Returns
        -------
        result : `int`
            Zero, unless overridden.

        Raises
        ------
        Exception
            Raised when an exception override is configured.
        """
        result = self._result("AVS_GetLambda")
        if result >= 0:
            wavelength[:] = self.wavelength
        return result

    def AVS_PollScan(self, handle):
        """Report whether the simulated measurement data are ready.

        Parameters
        ----------
        handle : `int`
            Device handle. Accepted but not validated.

        Returns
        -------
        result : `int`
            An override when nonzero; otherwise `0` while polling and `1`
            after ``polls_until_ready`` polls since the last successful
            measurement.

        Raises
        ------
        Exception
            Raised when an exception override is configured.
        """
        result = self._result("AVS_PollScan")
        if result != 0:
            return result
        if self.polls_since_measure < self.polls_until_ready:
            self.polls_since_measure += 1
            return 0
        return 1

    def AVS_GetScopeData(self, handle, time_label, spectrum):
        """Write simulated spectrum data to an output buffer.

        Parameters
        ----------
        handle : `int`
            Device handle. Accepted but not validated.
        time_label : `ctypes.POINTER(ctypes.c_uint)`
            Acquisition-time output pointer. Accepted but not modified.
        spectrum : writable sequence of `float`
            Output buffer populated with ``self.spectrum`` on a nonnegative
            result.

        Returns
        -------
        result : `int`
            Zero, unless overridden.

        Raises
        ------
        Exception
            Raised when an exception override is configured.
        """
        result = self._result("AVS_GetScopeData")
        if result >= 0:
            spectrum[:] = self.spectrum
        return result

    def AVS_StopMeasure(self, handle):
        """Stop a simulated measurement.

        Parameters
        ----------
        handle : `int`
            Device handle. Accepted but not validated.

        Returns
        -------
        result : `int`
            Zero, unless overridden.

        Raises
        ------
        Exception
            Raised when an exception override is configured.
        """
        return self._result("AVS_StopMeasure")
