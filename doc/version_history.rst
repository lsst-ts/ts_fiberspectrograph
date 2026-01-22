.. py:currentmodule:: lsst.ts.fiberspectrograph

.. _lsst.ts.fiberspectrograph.version_history:

###############
Version History
###############

.. towncrier release notes start

v0.11.1
-------
* Fix fits header information based on list object received from image name service.

v0.11.0
-------
* Make module names pep8 compliant.

v0.10.1
-------

* Use ts_pre_commit_config.
* Jenkinsfile: use the shared library.
* Remove scons support.

Requires:

* ts_salobj 7
* ts_idl 1
* FiberSpectrograph IDL files built with ts_xml 11

v0.10.0
-------

* Update `CONFIG_SCHEMA` to version v4: add a location field. 

Requires:

* ts_salobj 7
* ts_idl 1
* FiberSpectrograph IDL files built with ts_xml 11


v0.9.0
------

* Fix fits file header to match Vera C. Rubin format
* Add OBSID to fits header using utils.ImageNameServiceClient.
* Modernize conda build.
* pre-commit: update black to 23.1.0, isort to 5.12.0, mypy to 1.0.0, and pre-commit-hooks to v4.4.0.
* ``Jenkinsfile``: do not run as root.

Requires:

* ts_salobj 7
* ts_idl 1
* FiberSpectrograph IDL files built with ts_xml 11

v0.8.0
------

* Rename the package from ts_FiberSpectrograph to ts_fiberspectrograph.
* Jenkins CI file: change HOME to WHOME everywhere except the cleanup section.

Requires:

* ts_salobj 7
* ts_idl 1
* FiberSpectrograph IDL files built with ts_xml 11

v0.7.0
------

* Rename the command-line script to run_fiberspectrograph (lowercase and no ".py" suffix).
* Add a continuous integration Jenkinsfile.
* Build with pyproject.toml.

Requires:

* ts_salobj 7
* ts_idl 1
* FiberSpectrograph IDL files built with ts_xml 11

v0.6.1
------

* Fixed the formatting of a src file so that black 22.3.0 is happy with it.

Requires:

* ts_salobj 7
* ts_idl 1
* FiberSpectrograph IDL files built with ts_xml 11

v0.6.0
------

* Update for ts_salobj v7, which is required.
  This also requires ts_xml 11.

Requires:

* ts_salobj 7
* ts_idl 1
* FiberSpectrograph IDL files built with ts_xml 11


v0.5.0
------

* Update test_csc.py for ts_salobj 8.6, which is now required.
* Use ts_utils.
* Use pytest-black to test black formatting, instead of ts_salobj function.
* Modernize the unit tests to use bare asserts.

Requires:

* ts_salobj 6.8
* ts_idl 1
* ts_xml 4.3
* FiberSpectrograph IDL files, e.g. made using ``make_idl_files.py FiberSpectrograph``

v0.4.1
------

* Use `unittest.IsolatedAsyncioTestCase` instead of the abandoned asynctest package.
* Use pre-commit to enforce black formatting; see the README.md for instructions.
* Format the code with black 20.8b1.

Requires:

* ts_salobj 6.3
* ts_idl 1
* ts_xml 4.3
* FiberSpectrograph IDL files, e.g. made using ``make_idl_files.py FiberSpectrograph``

v0.4.0
------

* Store the CSC configuration schema in code.
  This requires ts_salobj 6.3.

Requires:

* ts_salobj 6.3
* ts_idl 1
* ts_xml 4.3
* FiberSpectrograph IDL files, e.g. made using ``make_idl_files.py FiberSpectrograph``

v0.3.2
------

* `FiberSpectrographCsc`: modernize handling of simulation mode.
* `FiberSpectrographCsc`: set ``version`` class variable.
  Test that this sets the cscVersion field of the softwareVersions event.
* Modernize doc/conf.py for documenteer 0.6.

Requires:

* ts_salobj 5.14
* ts_idl 1
* ts_xml 4.3
* FiberSpectrograph IDL files, e.g. made using ``make_idl_files.py FiberSpectrograph``

v0.3.1
------

* Updated Jenkinsfile.conda to use Jenkins Shared Library
* Pinned the ts-idl and ts-salobj version in conda recipe
* Add missing required dependency in EUPs table file

v0.3.0
------

* Updated for ts_salobj v5.14.0.
  Build the ``salobj.AsyncS3Bucket`` with ``create=True`` when mocking the S3 server.
  Specify ``suffix="*.fits"`` when constructing an S3 key.

Requires:

* ts_salobj 5.14
* ts_idl 1
* ts_xml 4.3
* FiberSpectrograph IDL files, e.g. made using ``make_idl_files.py FiberSpectrograph``

v0.2.1
------

* Add ``tests/test_black.py`` to verify that files are formatted with black.
  This requires ts_salobj 5.11 or later.
* Fix f strings with no {}.
* Update ``.travis.yml`` to remove ``sudo: false`` to github travis checks pass once again.

v0.2.0
------

Write images to an S3 Large File Annex using ts_salobj 5.9, which changes the convention for bucket names and keys.

Requires:

* ts_salobj 5.9
* ts_idl 1
* ts_xml 4.3
* FiberSpectrograph IDL files, e.g. made using ``make_idl_files.py FiberSpectrograph``

v0.1.0
------

First tagged prerelease.
This version adds writing images to an S3 Large File Annex using ts_salobj 5.8.

Requires:

* ts_salobj 5.8
* ts_idl 1
* ts_xml 4.3
* FiberSpectrograph IDL files, e.g. made using ``make_idl_files.py FiberSpectrograph``
