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

__all__ = ["CONFIG_SCHEMA"]

import yaml

CONFIG_SCHEMA = yaml.safe_load(
    """
$schema: http://json-schema.org/draft-07/schema#
$id: https://github.com/lsst-ts/ts_FiberSpectrograph/blob/master/python/lsst/ts/FiberSpectrograph/schema_config.py  # noqa
# title must end with one or more spaces followed by the schema version, which must begin with "v"
title: FiberSpectrograph v1
description: Schema for FiberSpectrograph configuration files
type: object
properties:
  s3instance:
    description: >-
      Large File Annex S3 instance, for example "summit", "ncsa", or "tucson".
    type: string
    default: "summit"
    pattern: "^[a-z0-9][.a-z0-9]*[a-z0-9]$"
required:
  - s3instance
additionalProperties: false
"""
)
