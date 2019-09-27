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

import os.path
import tempfile
import unittest

from astropy.table import Table
import astropy.time
import astropy.units as u
import numpy as np

from lsst.ts.FiberSpectrograph import SpectrographData, DataManager


class TestDataManager(unittest.TestCase):
    """Tests of the data management API for the fiber spectrograph CSC.
    """
    def setUp(self):
        self.instrument = "TestBlue"
        self.origin = "Not a real CSC"
        self.n_pixels = 1234
        self.wavelength = np.linspace(300, 1000, self.n_pixels, dtype=np.float64) * u.nm
        self.spectrum = np.random.random(self.n_pixels)
        self.duration = 2.5
        self.time_str = '1999-01-01T00:00:00.000'
        self.date_begin = astropy.time.Time(self.time_str, scale='tai')
        self.date_end = self.date_begin + astropy.time.TimeDelta(self.duration, format='sec')
        self.temperature = -273 * u.deg_C
        self.temperature_setpoint = -274 * u.deg_C
        self.type = "totally real data"
        self.source = "blacklight"
        self.data = SpectrographData(wavelength=self.wavelength,
                                     spectrum=self.spectrum,
                                     duration=self.duration,
                                     date_begin=self.date_begin,
                                     date_end=self.date_end,
                                     type=self.type,
                                     source=self.source,
                                     temperature=self.temperature,
                                     temperature_setpoint=self.temperature_setpoint,
                                     n_pixels=self.n_pixels)

        self.expected_header = {'FORMAT_V': 1,
                                'INSTRUME': self.instrument,
                                'ORIGIN': self.origin,
                                'DETSIZE': self.n_pixels,
                                'DATE-BEG': '1999-01-01T00:00:00.000',
                                'DATE-END': '1999-01-01T00:00:02.500',
                                'EXPTIME': self.duration,
                                'TIMESYS': 'TAI',
                                'IMGTYPE': self.type,
                                'SOURCE': self.source,
                                'TEMP_SET': self.temperature_setpoint.to_value(u.deg_C),
                                'CCDTEMP': self.temperature.to_value(u.deg_C,)}

    def check_header(self, header):
        """Check that all expected keys are in the header."""
        for key, value in self.expected_header.items():
            self.assertEqual(header[key], value, msg=f"Mismatched key: {key}")

    def test_make_fits_header(self):
        manager = DataManager(instrument=self.instrument, origin=self.origin)

        header = manager.make_fits_header(self.data)
        self.check_header(header)

    def test_make_primary_hdu(self):
        manager = DataManager(instrument=self.instrument, origin=self.origin)

        hdu = manager.make_primary_hdu(self.data)
        np.testing.assert_array_equal(hdu.data, self.spectrum)
        self.check_header(hdu.header)
        # The flux data should be a Primary HDU.
        self.assertIsInstance(hdu, astropy.io.fits.PrimaryHDU)

    def test_make_wavelength_hdu(self):
        manager = DataManager(instrument=self.instrument, origin=self.origin)
        hdu = manager.make_wavelength_hdu(self.data)
        np.testing.assert_array_equal(Table.read(hdu)['wavelength'], self.wavelength)
        # The wavelength data should not be a Primary HDU.
        self.assertNotIsInstance(hdu, astropy.io.fits.PrimaryHDU)

    def test_call(self):
        """Test that calling a DataManager outputs a FITS file with the correct
        values in it.

        TODO: once we have a working LFA API in salobj, replace the
        "file output" part of this test with a `spulec/moto`-based test that
        we've sent things to the correct s3 store.
        """
        with tempfile.TemporaryDirectory() as path:
            manager = DataManager(instrument=self.instrument, origin=self.origin, outpath=path)
            output = manager(self.data)
            expected_path = os.path.join(path, "TestBlue_1999-01-01T00:00:00.000.fits")
            self.assertEqual(output, expected_path)
            hdulist = astropy.io.fits.open(output, checksum=True)
            self.check_header(hdulist[0].header)
            np.testing.assert_array_equal(hdulist[0].data, self.spectrum)
            np.testing.assert_array_equal(Table.read(hdulist[1])['wavelength'], self.wavelength)
            # Ensure the checksums are written, but let astropy verify them.
            self.assertIn('CHECKSUM', hdulist[0].header)
            self.assertIn('DATASUM', hdulist[0].header)
            self.assertIn('CHECKSUM', hdulist[1].header)
            self.assertIn('DATASUM', hdulist[1].header)


if __name__ == "__main__":
    unittest.main()
