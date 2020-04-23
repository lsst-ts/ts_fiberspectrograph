.. py:currentmodule:: lsst.ts.FiberSpectrograph

.. _lsst.ts.FiberSpectrograph:

#########################
lsst.ts.FiberSpectrograph
#########################

Commandable SAL Component (CSC) to control the fiber spectrographs that are used to determine the wavelengths of the LSST calibration lamps and lasers.

.. _lsst.ts.FiberSpectrograph-using:

Using lsst.ts.FiberSpectrograph
===============================

.. toctree::
   :maxdepth: 2

The Avantes `Sensline <https://www.avantes.com/products/spectrometers/sensline/item/333-avaspec-uls-tec>`_ spectrographs are USB connected devices, controlled via a vendor-supplied linux library written in C.
This library, ``libavs.so``, must be installed in ``/usr/local/lib``.
See `~lsst.ts.FiberSpectrograph.AvsFiberSpectrograph` for information about library version compatibility.

.. _device-communication:

Device Communication
--------------------

The CSC communicates with a connected device via an `Resource acquisition is initialization (RAII) <https://en.wikipedia.org/wiki/Resource_acquisition_is_initialization>`_ controller class, `~lsst.ts.FiberSpectrograph.AvsFiberSpectrograph`, which manages the device state, exposures, and error return codes.
As an RAII class, a successful instantiation of the class means that the device is ready for use, and communication errors typically require destroying the instance and creating a new one to re-connect.
The CSC manages this via its states: transitioning to the DISABLED state creates a device connection, while transitioning to any non-ENABLED state closes the connection.

Multiple devices can be connected to a single computer (however, see caveats_), with the desired device determined by the index number of the CSC (see SALSubsystems.xml for the index->device mapping).
The index ``-1`` is special, as a CSC with that index will connect to the only attached USB spectrograph (if multiple devices are attached, ``index=-1`` will raise an error).
This can be useful for bench testing where different devices are plugged in and removed while a single CSC is running.

.. _exposures:

Exposures
---------

Exposure durations can be between 2 microseconds and 600 seconds.
Exposure readout should complete within about 10 milliseconds of the end of the exposure duration.

The output of an exposure is a 1x2048 pixel spectrum, with units of instrumental counts.
This spectrum is bundled with appropriate metadata and a per-pixel wavelength solution in a FITS file.
It is possible to saturate the detector: we do not currently provide a mask of saturated pixels.

Exposures are not dark corrected: we should have plenty of signal, so should have minimal dark current to worry about.
The AvaSpec devices have a "dynamic dark correction" option available, which we have disabled.

The device provides an estimated per-pixel wavelength solution, which we include with the output from each exposure.
These wavelengths should be used as an initial guess when fitting a calibration lamp (e.g. HeNeAr), and are likely not accurate enough for the LSST science goals.

Status commands have to wait for on-going exposures to finish.
This appears to be a limitation of the library or device itself: the ``AVS_GetParameter`` and ``AVS_GetAnalogIn`` commands (used to query the temperature setpoint and device temperature) will block until the exposure has been read out.

.. _status:

Cooling and status
------------------

The `~lsst.ts.FiberSpectrograph.FiberSpectrographCsc` telemetry loop outputs the device temperature and setpoint every 10 seconds.
We have not currently implemented a facility for modifying the setpoint temperature: the device default is 5°C.

.. _error-codes:

Error codes
-----------

When a command to the device fails, the called C function will return an error code.
The controller class will raise an exception that includes some information about that error code.
For a detailed description of what each error code means, consult section ``3.6.1`` of the AvaSpec Linux Library Manual, on page 44.

.. _simulator:

Simulator
---------

The CSC implements a simulator mode using the same `unittest.mock` framework that the tests use to fake a connected spectrograph, via the `~lsst.ts.FiberSpectrograph.AvsSimulator` class.
`~lsst.ts.FiberSpectrograph.AvsSimulator` mocks the loading of the ``libavs.so`` C library entirely, so the simulator must be activated before a device is connected, i.e. when the CSC is in STANDBY mode.
The simulator is configured for a "no error conditions" use case, where all functions return success codes and reasonable values.

.. _caveats:

Caveats and notes
-----------------

Some particular quirks of working with the system:

* There is no specific "USB heartbeat" command as there might be with an ethernet connected device; commands will immediately fail if the device is no longer connected or if there is a failure in communication.

* Running multiple CSCs from the same python instance may cause odd behavior, as the device controller class closes all communications via the ``AVS_Done`` function when disconnecting.
  It is **strongly recommended** to use a separate python instance for each device.

* Using multiple devices attached to the same computer should work, so long as each device is connected to via a specific serial number, as is done with the three indexes in the CSC.
  If no serial number is specified, the controller class will connect to a single attached device, but will fail at instantiation if multiple devices are attached.

.. _data_format:

Data Format
-----------

Data files written by this CSC are in FITS format with the data stored as a 1-D spectrum in the primary HDU.
The wavelength information is stored using the FITS ``-TAB`` standard and is stored in a binary table with name ``WCS-TAB``.
At this time Astropy does not natively support this WCS but the data and wavelength information can be read using the following code:

.. code-block:: python

   with astropy.io.fits.open(filename, checksum=True) as hdulist:
       spectrum = hdulist[0].data

       # Read WCS information from header
       primary_header = hdulist[0].header
       wcs_tab_name = primary_header["PS1_0"]
       wcs_tab_extver = primary_header["PV1_1"]
       wave_col_name = primary_header["PS1_1"]
       wave_table = astropy.table.QTable.read(hdulist[wcs_tab_name, wcs_tab_extver])
       # Only one row so select that one explicitly
       wavelengths = wave_table[wave_col_name][0]
       # Force 1,N array to shape N
       wavelengths = wavelengths.flatten()

.. _lsst.ts.FiberSpectrograph-contributing:

Contributing
============

``lsst.ts.FiberSpectrograph`` is developed at https://github.com/lsst-ts/ts_FiberSpectrograph.
You can find Jira issues for this module under the `FiberSpectrograph <https://jira.lsstcorp.org/issues/?jql=labels%20%3D%20FiberSpectrograph>`_ label.

.. If there are topics related to developing this module (rather than using it), link to this from a toctree placed here.

.. .. toctree::
..    :maxdepth: 1

.. _lsst.ts.FiberSpectrograph-pyapi:

Python API reference
====================

.. automodapi:: lsst.ts.FiberSpectrograph
   :no-main-docstr:
   :no-inheritance-diagram:

Revision History
================

.. toctree::
    revision_history
    :maxdepth: 1
