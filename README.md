# ts_FiberSpectrograph

Python-based interface for the Avantes fiber spectrograph and a Configurable Commandable SAL Component (CSC) to control it.

Use of this package requires that `libavs.so.0.2.0` be installed in `/usr/local/lib`.

## Non-root access

By default, `libavs` only allows root access to the USB device; this is common for USB devices on Linux.
You add a new udev rule to allow non-root access to the user or group of your choice.
To allow access to the device (identified by a vendor and product id that can be found with `lsusb`), create this file:

    /etc/udev/rules.d/30-avantes-spec-usb.rules

containing this single line, setting GROUP to the group you want to grant access to:

    SUBSYSTEM=="usb", ATTR{idVendor}=="1992", ATTR{idProduct}=="0667", ACTION=="add", GROUP="lsst", MODE="0664"

and then reload the udev rules:

    sudo udevadm control --reload-rules && udevadm trigger

That should make the device usable by anyone in that specified GROUP.

A useful test that the above rule actually triggers when the device is plugged in (i.e. checking for typos) is to run this command (possibly changing the device identifier number at the end to match where your device is attached: use `lsusb` to find that) and look for the above rule in the output:

    udevadm test /devices/pci0000:00/0000:00:14.0/usb1/1-4

You can also try running `udevadm monitor --udev` and plugging and un-plugging the device, but I found this not to be as informative as the above `udevadm test` command was.

To confirm that your above changes worked, use the `testavs` executable distributed with the vendor files (in the `Qt5_demos/`) directory. You can first run it as root to confirm that `libavs.so` is being found by the system that the device is seen at all. Then, after you have configured the above udev rules, you can run it as a user in the "lsst" group to confirm that it works for non-root users.
