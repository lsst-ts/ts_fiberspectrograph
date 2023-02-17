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

__all__ = ["SpectrographData", "DataManager"]

import dataclasses

import astropy.io.fits
import astropy.table
import astropy.time
import astropy.units as u
import numpy as np

# The version of the FITS file format produced by this class.
FORMAT_VERSION = 1


@dataclasses.dataclass
class SpectrographData:
    """Class to hold data and metadata from a fiber spectrograph."""

    wavelength: astropy.units.Quantity
    """The wavelength array produced by the instrument."""
    spectrum: np.ndarray
    """The flux array in instrumental units."""
    duration: float
    """The duration of the exposure in seconds."""
    date_begin: astropy.time
    """The start time of the exposure."""
    date_end: astropy.time
    """The end time of the exposure."""
    type: str
    """The measurement type (see the XML `expose.type` field)."""
    source: str
    """The light source that was measured (see the XML `expose.source` field).
    """
    temperature: astropy.units.Quantity
    """The internal spectrograph temperature."""
    temperature_setpoint: astropy.units.Quantity
    """The internal spectrograph temperature set point."""
    n_pixels: int
    """The number of pixels in the detector."""


class DataManager:
    """A data packager from the Fiber Spectrograph CSC.

    Attributes
    ----------
    instrument : `str`
        The name of the instrument taking the data.
    origin : `str`
        The name of the program that produced this data.
    """

    wcs_table_name = "WCS-TAB"
    """Name of the table containing the wavelength WCS (EXTNAME)."""
    wcs_table_ver = 1
    """WCS table version (EXTVER)."""
    wcs_column_name = "wavelength"
    """Name of the table column containing the wavelength information."""

    def __init__(self, instrument, origin):
        self.instrument = instrument
        self.origin = origin

    def make_hdulist(self, data):
        """Generate a FITS hdulist built from SpectrographData.

        Parameters
        ----------
        data : `SpectrographData`
            The data from which to build the FITS hdulist.

        Returns
        -------
        hdulist : `astropy.io.fits.HDUList`
            The FITS hdulist.
        """
        hdu1 = self.make_primary_hdu(data)
        hdu2 = self.make_wavelength_hdu(data)
        return astropy.io.fits.HDUList([hdu1, hdu2])

    def make_fits_header(self, data):
        """Return a FITS header built from SpectrographData."""
        hdr = astropy.io.fits.Header()
        # TODO: it would be good to include the dataclass docstrings
        # as comments on each of these, but pydoc can't see them.
        hdr["FORMAT_V"] = FORMAT_VERSION
        hdr["INSTRUME"] = self.instrument
        hdr["ORIGIN"] = self.origin
        hdr["DETSIZE"] = data.n_pixels
        hdr["DATE-BEG"] = astropy.time.Time(data.date_begin).tai.fits
        hdr["DATE-END"] = astropy.time.Time(data.date_end).tai.fits
        hdr["EXPTIME"] = data.duration
        hdr["TIMESYS"] = "TAI"
        hdr["IMGTYPE"] = data.type
        hdr["SOURCE"] = data.source
        hdr["TEMP_SET"] = data.temperature_setpoint.to_value(u.deg_C)
        hdr["CCDTEMP"] = data.temperature.to_value(u.deg_C)

        # WCS headers - Use -TAB WCS definition
        wcs_cards = [
            "WCSAXES =                    1 / Number of WCS axes",
            "CRPIX1  =                  0.0 / Reference pixel on axis 1",
            "CRVAL1  =                  0.0 / Value at ref. pixel on axis 1",
            "CNAME1  = 'Wavelength'         / Axis name for labeling purposes",
            "CTYPE1  = 'WAVE-TAB'           / Wavelength axis by lookup table",
            "CDELT1  =                  1.0 / Pixel size on axis 1",
            f"CUNIT1  = '{data.wavelength.unit.name:8s}'           / Units for axis 1",
            f"PV1_1   = {self.wcs_table_ver:20d} / EXTVER  of bintable extension for -TAB arrays",
            f"PS1_0   = '{self.wcs_table_name:8s}'           / EXTNAME of bintable extension for -TAB arrays",
            f"PS1_1   = '{self.wcs_column_name:8s}'         / Wavelength coordinate array",
        ]
        for c in wcs_cards:
            hdr.append(astropy.io.fits.Card.fromstring(c))

        return hdr

    def make_primary_hdu(self, data):
        """Return the primary HDU built from SpectrographData."""

        hdu = astropy.io.fits.PrimaryHDU(
            data=data.spectrum, header=self.make_fits_header(data)
        )
        return hdu

    def make_wavelength_hdu(self, data):
        """Return the wavelength HDU built from SpectrographData."""

        # The wavelength array must be 2D (N, 1) in numpy but (1, N) in FITS
        wavelength = data.wavelength.reshape([data.wavelength.size, 1])

        # Create a Table. It will be a single element table
        table = astropy.table.Table()

        # Create the wavelength column
        # Create the column explicitly since it is easier to ensure the
        # shape this way.
        wavecol = astropy.table.Column([wavelength], unit=wavelength.unit.name)

        # The column name must match the PS1_1 entry from the primary HDU
        table[self.wcs_column_name] = wavecol

        # The name MUST match the value of PS1_0 and the version MUST
        # match the value of PV1_1
        hdu = astropy.io.fits.BinTableHDU(table, name=self.wcs_table_name, ver=1)
        return hdu
