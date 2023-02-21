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

import jsonschema
import pytest
from lsst.ts import fiberspectrograph, salobj


class ValidationTestCase(unittest.TestCase):
    """Test validation of the config schema."""

    def setUp(self):
        self.schema = fiberspectrograph.CONFIG_SCHEMA
        self.validator = salobj.StandardValidator(schema=self.schema)

    def test_basics(self):
        config = dict(
            s3instance="a.valid.value",
            image_service_url="http://comcam-mcm.tu.lsst.org",
        )
        self.validator.validate(config)

    def test_invalid_configs(self):
        for bad_s3instance in (
            "1BadName",  # No uppercase
            "2bad_name",  # No underscores
            "3bad-name",  # No hyphens
            "4bad#name",  # No # @ , etc.
            "5bad@name",  # No # @ , etc.
            ".6badname",  # must start with letter or digit
            "7badname.",  # must end with a letter or digit
        ):
            bad_data = dict(
                s3instance=bad_s3instance,
                image_service_url="http://comcam-mcm.ls.lsst.org",
            )
            with self.subTest(bad_data=bad_data):
                with pytest.raises(jsonschema.exceptions.ValidationError):
                    self.validator.validate(bad_data)


if __name__ == "__main__":
    unittest.main()
