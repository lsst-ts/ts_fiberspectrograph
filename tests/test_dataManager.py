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

import unittest

import astropy.time
import astropy.units as u
import numpy as np
from astropy.table import QTable
from lsst.ts.fiberspectrograph import DataManager, SpectrographData


class TestDataManager(unittest.TestCase):
    """Tests of the data management API for the fiber spectrograph CSC."""

    def setUp(self):
        self.instrument = "TestBlue"
        self.origin = "Not a real CSC"
        self.serial = "123"
        self.n_pixels = 1234
        self.wavelength = np.linspace(300, 1000, self.n_pixels, dtype=np.float64) * u.nm
        self.spectrum = np.random.random(self.n_pixels)
        self.duration = 2.5
        self.time_str = "1999-01-01T00:00:00.000"
        self.date_begin = astropy.time.Time(self.time_str, scale="tai")
        self.date_end = self.date_begin + astropy.time.TimeDelta(
            self.duration, format="sec"
        )
        self.temperature = -273 * u.deg_C
        self.temperature_setpoint = -274 * u.deg_C
        self.type = "totally real data"
        self.source = "blacklight"
        self.data = SpectrographData(
            wavelength=self.wavelength,
            spectrum=self.spectrum,
            duration=self.duration,
            date_begin=self.date_begin,
            date_end=self.date_end,
            type=self.type,
            source=self.source,
            temperature=self.temperature,
            temperature_setpoint=self.temperature_setpoint,
            n_pixels=self.n_pixels,
        )

        self.expected_header = {
            "FORMAT_V": 1,
            "INSTRUME": self.instrument,
            "SERIAL": self.serial,
            "CSCNAME": self.origin,
            "DETSIZE": self.n_pixels,
            "DATE-BEG": "1999-01-01T00:00:00.000",
            "DATE-END": "1999-01-01T00:00:02.500",
            "ORIGIN": "Vera C. Rubin Observatory",
            "DAYOBS": int("19990101"),
            "EXPTIME": self.duration,
            "TIMESYS": "TAI",
            "IMGTYPE": "spectrum",
            "SOURCE": self.source,
            "TEMP_SET": self.temperature_setpoint.to_value(u.deg_C),
            "CCDTEMP": self.temperature.to_value(
                u.deg_C,
            ),
            # WCS headers
            "CTYPE1": "WAVE-TAB",
            "PS1_0": "WCS-TAB",
            "PS1_1": "wavelength",
            "CUNIT1": "nm",
        }

    def check_header(self, header):
        """Check that all expected keys are in the header."""
        for key, value in self.expected_header.items():
            assert header[key] == value, f"Mismatched key: {key}"

    def check_wavelength_data(self, wavelengths, expected_unit=None):
        """Check that the wavelength data read from the file is correct."""
        # This will be 2D from the table so force to 1D for comparison
        assert wavelengths.shape == (self.wavelength.size, 1)
        wavelengths = wavelengths.flatten()
        np.testing.assert_array_equal(wavelengths, self.wavelength)

        # Ensure that we have a quantity compatible with meters
        assert wavelengths.to(u.m).unit.name == "m"

        if expected_unit is not None:
            assert wavelengths.unit.name == expected_unit

    def test_make_fits_header(self):
        manager = DataManager(
            instrument=self.instrument, origin=self.origin, serial=self.serial
        )

        header = manager.make_fits_header(self.data)
        self.check_header(header)

    def test_make_primary_hdu(self):
        manager = DataManager(
            instrument=self.instrument, origin=self.origin, serial=self.serial
        )

        hdu = manager.make_primary_hdu(self.data)
        np.testing.assert_array_equal(hdu.data, self.spectrum)
        self.check_header(hdu.header)
        # The flux data should be a Primary HDU.
        assert isinstance(hdu, astropy.io.fits.PrimaryHDU)

    def test_make_wavelength_hdu(self):
        manager = DataManager(
            instrument=self.instrument, origin=self.origin, serial=self.serial
        )
        hdu = manager.make_wavelength_hdu(self.data)
        # Need first wavelength from first row
        wavelengths = QTable.read(hdu)["wavelength"][0]
        self.check_wavelength_data(wavelengths)
        # The wavelength data should not be a Primary HDU.
        assert not isinstance(hdu, astropy.io.fits.PrimaryHDU)

    def test_make_hdulist(self):
        manager = DataManager(
            instrument=self.instrument, origin=self.origin, serial=self.serial
        )
        hdulist = manager.make_hdulist(self.data)
        self.check_header(hdulist[0].header)
        np.testing.assert_array_equal(hdulist[0].data, self.spectrum)

        # Check that the headers are consistent with WCS -TAB
        primary_header = hdulist[0].header
        assert primary_header["CTYPE1"] == "WAVE-TAB"
        wcs_tab_name = primary_header["PS1_0"]
        wcs_tab_extver = primary_header["PV1_1"]
        wave_col_name = primary_header["PS1_1"]
        wave_table = QTable.read(hdulist[wcs_tab_name, wcs_tab_extver])
        assert len(wave_table) == 1
        # Only one row so select that one explicitly
        wavelengths = wave_table[wave_col_name][0]
        self.check_wavelength_data(wavelengths, expected_unit=primary_header["CUNIT1"])


if __name__ == "__main__":
    unittest.main()
