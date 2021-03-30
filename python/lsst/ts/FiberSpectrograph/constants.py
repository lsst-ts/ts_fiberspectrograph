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

__all__ = ["SalIndex", "SimulationMode", "BAND_NAMES", "SERIAL_NUMBERS"]

import enum


class SalIndex(enum.IntEnum):
    """Valid values for the SAL index.

    A duplicate of the SALSubsystems.xml entry in ts_xml
    with the addition of UNKNOWN, which means
    "use the only connected spectrograph".
    """

    UNKNOWN = -1
    BLUE = 1
    RED = 2
    BROAD = 3


class SimulationMode(enum.IntFlag):
    """Bitmask values for the CSC simulation mode."""

    Spectrograph = 1
    S3Server = 2


# A short name describing the range of the spectrograph.
BAND_NAMES = {
    SalIndex.UNKNOWN: "unknown",
    SalIndex.BLUE: "Blue",
    SalIndex.RED: "Red",
    SalIndex.BROAD: "Broad",
}

# Serial numbers of the spectrographs.
SERIAL_NUMBERS = {
    SalIndex.UNKNOWN: None,
    SalIndex.BLUE: "1606192U1",
    SalIndex.RED: "1606190U1",
    SalIndex.BROAD: "1606191U1",
}
