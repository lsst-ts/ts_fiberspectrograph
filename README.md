# ts_fiberspectrograph

Python-based interface for the Avantes fiber spectrograph and a Configurable Commandable SAL Component (CSC) to control it.

Use of this package requires that `libavs.so.0.2.0` be installed in `/usr/local/lib`.

## Non-root access

By default, `libavs` only allows root access to the USB device; this is common for USB devices on Linux.
You add a new udev rule to allow non-root access to the user or group of your choice.
To allow access to the device (identified by a vendor and product id that can be found with `lsusb`), create this file:

    /etc/udev/rules.d/30-avantes-spec-usb.rules

containing this single line, setting GROUP to the group you want to grant access to, adding the owner should not be necessary except it appears to be required in order to set the uid correctly.

    SUBSYSTEM=="usb", ATTR{idVendor}=="1992", ATTR{idProduct}=="0667", ACTION=="add", GROUP="saluser", OWNER="saluser", MODE="0664"

and then reload the udev rules:

    sudo udevadm control --reload-rules && udevadm trigger

That should make the device usable by anyone in that specified GROUP, however, the device may need to be unplugged and replugged.

A useful test that the above rule actually triggers when the device is plugged in (i.e. checking for typos) is to run this command (possibly changing the device identifier number at the end to match where your device is attached: use `lsusb` to find that) and look for the above rule in the output:

    udevadm test /devices/pci0000:00/0000:00:14.0/usb1/1-4

You can also try running `udevadm monitor --udev` and plugging and un-plugging the device, but I found this not to be as informative as the above `udevadm test` command was.

One can check that the permissions are correct by looking at the permissions of the device.
Note that the first value after usb represents the bus, whereas the second indicates the device, which may need to be changed from the example below:

    ls -ltr /dev/bus/usb/001/004

The proper output should be:

    crw-rw-r--. 1 saluser saluser 189, 3 Nov 15 03:01 /dev/bus/usb/001/004

Note that if the new rule has not been applied, running the udevadm utest command using sudo may as it appears to modify the owner and group help.



# Automatic Formatting

This code uses ``pre-commit`` to maintain ``black`` formatting and ``flake8`` compliance.
To enable this, run the following commands once (the first removes the previous pre-commit hook)::

    git config --unset-all core.hooksPath
    pre-commit install
