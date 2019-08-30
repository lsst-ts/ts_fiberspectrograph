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

__all__ = ["FiberSpectrograph"]

import logging

from .fibspec import AVS


class FiberSpectrograph:
    """Interface for the Avantes fiber spectrograph AvaSpec library.

    This class follows Resource acquisition is initialization (RAII): when
    instantiated, it opens a connection; if it cannot open a connection, it
    raises an exception. To reconnect, delete the object and create a new one.

    Parameters
    ----------
    serial_number: `str`, optional
        The serial number of the USB device to connect to. If `None`, then
        connect to the only available USB device, or raise RuntimeError
        if multiple devices are connected.

    Raises
    ------
    LookupError
        Raised if there is no device with the specified serial number.
    RuntimeError
        * Raised if multiple devices are connected and no serial number
        was specified.
        * Raised if there is an error connecting to the requested device.
    """
    handle = None
    """The handle of the connected spectrograph.
    """
    device = None
    """`AvsIdentityType` of the connected spectrograph.
    """

    def __init__(self, serial_number=None):
        self.log = logging.getLogger('FiberSpectrograph')
        self.log.setLevel(logging.DEBUG)

        self.avaspec = AVS()
        # NOTE: init(0) initializes the USB library, not device 0.
        self.avaspec.init(0)

        self._connect(serial_number)

    def _connect(self, serial_number=None):
        """Establish a connection with a single USB spectrograph.

        Parameters
        ----------
        serial_number: `str`, optional
            The serial number of the USB device to connect to. If `None`, then
            connect to the only available USB device, or raise RuntimeError
            if multiple devices are connected.

        Raises
        ------
        LookupError
            Raised if there is no device with the specified serial number.
        RuntimeError
            * Raised if multiple devices are connected and no serial number
            was specified.
            * Raised if there is an error connecting to the requested device.
        """
        n_devices = self.avaspec.updateUSBDevices()
        self.log.debug("Found %d attached USB Avantes device(s).", n_devices)

        code, device_list = self.avaspec.getList()
        if serial_number is None:
            if len(device_list) > 1:
                raise RuntimeError(f"Multiple devices found, but no serial number specified."
                                   f" Attached devices: {device_list}")
            device = device_list[0]
        else:
            for device in device_list:
                if serial_number == device.SerialNumber.decode('ascii'):
                    break
            else:
                msg = f"Device serial number {serial_number} not found in device list: {device_list}"
                raise LookupError(msg)
        self.handle = self.avaspec.activate(device)
        if self.handle == self.avaspec.INVALID_AVS_HANDLE_VALUE:
            raise RuntimeError(f"Cannot activate device: {device}")
        self.log.info("Activated connection (handle=%s) with USB device %s.", self.handle, device)
        self.device = device

    def disconnect(self):
        """Close the connection with the connected USB spectrograph.
        If the attempt to disconnect fails, log an error messages.
        """
        if self.handle is not None:
            result = self.avaspec.lib.AVS_Deactivate(self.handle)
            if not result:
                self.log.error("Could not deactivate device %s with handle %s.", self.device, self.handle)

    async def get_status(self):
        """Get the status of the currently connected spectrograph.

        Returns
        -------
        status : `StatusClass?`
            The current status of the spectrograph, including temperature,
            exposure status, etc.
        """
        pass

    async def expose(self, duration):
        """Take an exposure with the currently connected spectrograph.

        Returns
        -------
        spectrum : `numpy.ndarray`
            The 1-d spectrum measured by the instrument.
        """
        pass

    async def stop_exposure(self):
        """Cancel a currently running exposure and reset the spectrograph.
        """
        pass

    def __del__(self):
        self.disconnect()
