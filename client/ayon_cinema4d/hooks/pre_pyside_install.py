import os
import subprocess
import platform
import uuid

from ayon_applications import PreLaunchHook, LaunchTypes


class InstallPySideToCinema4D(PreLaunchHook):
    """Automatically installs Qt binding to Cinema 4D's python packages.

    Check if Cinema 4D has installed PySide6 and will try to install if not.

    For pipeline implementation is required to have Qt binding installed in
    Cinema 4D's python packages.
    """

    app_groups = {"cinema4d"}
    order = 2
    launch_types = {LaunchTypes.local}

    def execute(self):
        # TODO: Enable this when we find a way to make it faster
        return
        # Prelaunch hook is not crucial
        try:
            # TODO: Add setting to enable/disable this
            # settings = self.data["project_settings"][self.host_name]
            # if not settings["hooks"]["InstallPySideToCinema4d"]["enabled"]:
            #     return
            self.inner_execute()
        except Exception:
            self.log.warning(
                "Processing of {} crashed.".format(self.__class__.__name__),
                exc_info=True
            )

    def inner_execute(self):
        self.log.debug("Check for PySide6 installation.")

        # Find c4dpy executable
        executable = self.launch_context.executable.executable_path
        expected_executable = "c4dpy"
        platform_name = platform.system().lower()
        if platform_name == "windows":
            expected_executable += ".exe"
        if os.path.basename(executable) != expected_executable:
            folder = os.path.dirname(executable)
            python_executable = os.path.join(folder, expected_executable)
        else:
            python_executable = executable

        if not os.path.exists(python_executable):
            self.log.warning(
                "Couldn't find python executable for Cinema4D. {}".format(
                    python_executable
                )
            )
            return

        # Check if PySide6 is installed and skip if yes
        if self._is_pyside_installed(python_executable):
            self.log.debug("Cinema4D has already installed PySide6.")
            return

        self.log.debug("Installing PySide6.")
        # Install PySide6 in cinema4d's python
        if self._windows_require_permissions(
                os.path.dirname(python_executable)):
            result = self._install_pyside_windows(python_executable)
        else:
            result = self._install_pyside(python_executable)

        if result:
            self.log.info("Successfully installed PySide6 module to cinema4d.")
        else:
            self.log.warning("Failed to install PySide6 module to cinema4d.")

    def _install_pyside_windows(self, python_executable):
        """Install PySide6 python module to cinema4d's python.

        Installation requires administration rights that's why it is required
        to use "pywin32" module which can execute command's and ask for
        administration rights.
        """
        try:
            import win32con
            import win32process
            import win32event
            import pywintypes
            from win32comext.shell.shell import ShellExecuteEx
            from win32comext.shell import shellcon
        except Exception:
            self.log.warning("Couldn't import \"pywin32\" modules")
            return False

        try:
            # Parameters
            # - use "-m pip" as module pip to install PySide6 and argument
            #   "--ignore-installed" is to force install module to cinema4d's
            #   site-packages and make sure it is binary compatible
            parameters = "-m pip install --ignore-installed PySide6"

            # Execute command and ask for administrator's rights
            process_info = ShellExecuteEx(
                nShow=win32con.SW_SHOWNORMAL,
                fMask=shellcon.SEE_MASK_NOCLOSEPROCESS,
                lpVerb="runas",
                lpFile=python_executable,
                lpParameters=parameters,
                lpDirectory=os.path.dirname(python_executable)
            )
            process_handle = process_info["hProcess"]
            win32event.WaitForSingleObject(process_handle,
                                           win32event.INFINITE)
            returncode = win32process.GetExitCodeProcess(process_handle)
            return returncode == 0
        except pywintypes.error:
            return False

    def _install_pyside(self, python_executable):
        """Install PySide6 python module to cinema4d's python."""
        try:
            # Parameters
            # - use "-m pip" as module pip to install PySide6 and argument
            #   "--ignore-installed" is to force install module to cinema4d's
            #   site-packages and make sure it is binary compatible
            env = dict(os.environ)
            del env['PYTHONPATH']
            args = [
                python_executable,
                "-m",
                "pip",
                "install",
                "--ignore-installed",
                "PySide6",
            ]
            process = subprocess.Popen(
                args, stdout=subprocess.PIPE, universal_newlines=True,
                env=env
            )
            process.communicate()
            return process.returncode == 0
        except PermissionError:
            self.log.warning(
                "Permission denied with command:"
                "\"{}\".".format(" ".join(args))
            )
        except OSError as error:
            self.log.warning(f"OS error has occurred: \"{error}\".")
        except subprocess.SubprocessError:
            pass

    def _is_pyside_installed(self, python_executable):
        """Check if PySide6 module is in cinema4d's pip list."""
        args = [python_executable, "-c", "from qtpy import QtWidgets"]
        process = subprocess.Popen(args,
                                   stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE)
        _, stderr = process.communicate()
        stderr = stderr.decode()
        if stderr:
            return False
        return True

    def _windows_require_permissions(self, dirpath):
        if platform.system().lower() != "windows":
            return False

        try:
            # Attempt to create a temporary file in the folder
            temp_file_path = os.path.join(dirpath, uuid.uuid4().hex)
            with open(temp_file_path, "w"):
                pass
            os.remove(temp_file_path)  # Clean up temporary file
            return False

        except PermissionError:
            return True

        except BaseException as exc:
            print(("Failed to determine if root requires permissions."
                   "Unexpected error: {}").format(exc))
            return False
