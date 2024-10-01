# Cinema4D Addon

Cinema4D addon integration for AYON.

## Setup

### Install Qt library for Cinema4D

A Qt library must be installed for Cinema4D to ensure the AYON tools can run, either make sure
a `PySide6` or `PySide2` library is available on `PYTHONPATH` matching the Python version of the Cinema4D release.

Alternatively, you can use the Tray launcher to trigger the `Terminal` tool to open a command-line initialized for the Cinema4D application. From there you should be able to run:
```cmd
c4dpy.exe -m pip install --ignore-installed PySide6
```
## Known Issues

### High DPI scaling

The Redshift render view may appear oddly scaled on high DPI monitors due to some Qt scaling environment variables that AYON sets by default. To resolve this, launch Cinema4D with the environment variable: `QT_AUTO_SCREEN_SCALE_FACTOR=0`

This can be easily setup in the Application environment settings:
```json
{
 "QT_AUTO_SCREEN_SCALE_FACTOR": "0"
}
```