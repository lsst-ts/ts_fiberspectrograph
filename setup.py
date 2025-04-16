from importlib import metadata

import setuptools
import setuptools_scm

scm_version = metadata.version("setuptools_scm")

if scm_version.startswith("8"):
    setuptools.setup(
        version=setuptools_scm.get_version(
            version_file="python/lsst/ts/fiberspectrograph/version.py",
            relative_to="pyproject.toml",
        )
    )
else:
    setuptools.setup(
        version=setuptools_scm.get_version(
            write_to="python/lsst/ts/fiberspectrograph/version.py"
        )
    )
