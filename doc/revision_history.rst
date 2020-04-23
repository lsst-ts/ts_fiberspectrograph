.. py:currentmodule:: lsst.ts.FiberSpectrograph

.. _lsst.ts.FiberSpectrograph.revision_history:

#####################################
ts_FiberSpectrograph Revision History
#####################################

v0.2.0
======

Write images to an S3 Large File Annex using ts_salobj 5.9, which changes the convention for bucket names and keys.

Requires:

* ts_salobj 5.9
* ts_idl 1
* ts_xml 4.3
* Rotator IDL files, e.g. made using ``make_idl_files.py Rotator``

v0.1.0
======

First tagged prerelease.
This version adds writing images to an S3 Large File Annex using ts_salobj 5.8.

Requires:

* ts_salobj 5.8
* ts_idl 1
* ts_xml 4.3
* FiberSpectrograph IDL files, e.g. made using ``make_idl_files.py FiberSpectrograph``
