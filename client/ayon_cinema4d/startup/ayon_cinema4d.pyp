import os
import sys

# For whatever reason Cinema4D does not add `PYTHONPATH` to `sys.path`
# It also seems that e.g. `C4DPYTHONPATH310` does not do that either?
for path in os.getenv("PYTHONPATH", "").split(os.pathsep):
    if path and path not in sys.path:
        sys.path.append(path)

# C4D doesn't ship with python3.dll which PySide is built against on Windows.
# Note: The python3.dll must match with the correct Python 3.x.y version
# Hence we need to force it to be an available .dll for Qt.
# C4D Hosts root
import ayon_cinema4d  # noqa: E402
AYON_C4D_ROOT = os.path.dirname(ayon_cinema4d.__file__)


def add_dll_directory(_path):
    # Python3.8+ uses os.add_dll_directory to load dlls
    # Previous version just add to the PATH env var
    try:
        os.add_dll_directory(_path)
    except AttributeError:
        norm_path = os.path.normpath(_path)
        os.environ["PATH"] = norm_path + os.pathsep + os.environ["PATH"]


if "win" in sys.platform:
    dll_dir = os.path.join(
        AYON_C4D_ROOT, "resource", "windows", "bin",
        "py{0.major}.{0.minor}".format(sys.version_info)
    )
    print("Adding DLL directory: {}".format(dll_dir))
    add_dll_directory(dll_dir)


import c4d  # noqa: E402

from ayon_core.resources import get_resource  # noqa: E402
from ayon_core.pipeline import install_host  # noqa: E402
from ayon_cinema4d.api import Cinema4DHost  # noqa: E402
from ayon_cinema4d.api.lib import get_main_window  # noqa: E402
from ayon_cinema4d.api.commands import (
    reset_frame_range,
    reset_resolution,
    reset_colorspace
)  # noqa: E402
from ayon_core.tools.utils import host_tools  # noqa: E402


AYON_LOAD_ID = 1064311
AYON_CREATE_ID = 1064312
AYON_PUBLISH_ID = 1064313
AYON_MANAGE_ID = 1064315
AYON_LIBRARY_ID = 1064314
AYON_WORKFILES_ID = 1064310
AYON_BUILD_WORKFILE_ID = 1064316
AYON_RESET_FRAME_RANGE_ID = 1064317
AYON_RESET_RESOLUTION_ID = 1064318
AYON_RESET_COLORSPACE_ID = 1064320
AYON_EXPERIMENTAL_TOOLS_ID = 1064319


def get_icon_by_name(name):
    """Get icon full path"""
    return get_resource("icons", "{}.png".format(name))


def get_icon_bitmap_by_name(name):
    bitmap = c4d.bitmaps.BaseBitmap()
    bitmap.InitWith(get_icon_by_name(name))
    return bitmap


class Creator(c4d.plugins.CommandData):
    id = AYON_CREATE_ID
    label = "Create..."
    icon = c4d.bitmaps.InitResourceBitmap(1018791)  # split polycube icon

    def Execute(self, doc):
        host_tools.show_publisher(
            tab="create",
            parent=get_main_window()
        )
        return True


class Loader(c4d.plugins.CommandData):
    id = AYON_LOAD_ID
    label = "Load..."
    icon = get_icon_bitmap_by_name("loader")

    def Execute(self, doc):
        host_tools.show_loader(
            parent=get_main_window(),
            use_context=True
        )
        return True


class Publish(c4d.plugins.CommandData):
    id = AYON_PUBLISH_ID
    label = "Publish..."

    def Execute(self, doc):
        host_tools.show_publisher(
            tab="publish",
            parent=get_main_window()
        )
        return True


class Manage(c4d.plugins.CommandData):
    id = AYON_MANAGE_ID
    label = "Manage..."
    icon = get_icon_bitmap_by_name("inventory")

    def Execute(self, doc):
        host_tools.show_scene_inventory(
            parent=get_main_window()
        )
        return True


class Library(c4d.plugins.CommandData):
    id = AYON_LIBRARY_ID
    label = "Library..."
    icon = get_icon_bitmap_by_name("folder-favorite")

    def Execute(self, doc):
        host_tools.show_library_loader(
            parent=get_main_window()
        )
        return True


class Workfiles(c4d.plugins.CommandData):
    id = AYON_WORKFILES_ID
    label = "Workfiles..."
    icon = get_icon_bitmap_by_name("workfiles")

    def Execute(self, doc):
        host_tools.show_workfiles(
            parent=get_main_window()
        )
        return True


class ResetFrameRange(c4d.plugins.CommandData):
    id = AYON_RESET_FRAME_RANGE_ID
    label = "Reset Frame Range"
    icon = c4d.bitmaps.InitResourceBitmap(1038339)  # filmstrip

    def Execute(self, doc):
        reset_frame_range()
        return True


class ResetSceneResolution(c4d.plugins.CommandData):
    id = AYON_RESET_RESOLUTION_ID
    label = "Reset Scene Resolution"
    icon = c4d.bitmaps.InitResourceBitmap(1040962)  # expandy icon

    def Execute(self, doc):
        reset_resolution()
        return True


class ResetColorspace(c4d.plugins.CommandData):
    id = AYON_RESET_COLORSPACE_ID
    label = "Reset Colorspace"
    icon = c4d.bitmaps.InitResourceBitmap(440000312)  # color

    def Execute(self, doc):
        reset_colorspace()
        return True


# class BuildWorkFileCommand(c4d.plugins.CommandData):
#     id = AYON_BUILD_WORKFILE_ID
#     label = "Build Workfile"
#     icon = c4d.bitmaps.InitResourceBitmap(1024542)  # wrench
#
#     def Execute(self, doc):
#         BuildWorkfile().process()
#         return True


class ExperimentalTools(c4d.plugins.CommandData):
    id = AYON_EXPERIMENTAL_TOOLS_ID
    label = "Experimental Tools"
    icon = c4d.bitmaps.InitResourceBitmap(18186)  # ghost

    def Execute(self, doc):
        host_tools.show_experimental_tools_dialog(
            get_main_window()
        )
        return True


def install_menu():
    """Register the OpenPype menu with Cinema4D"""
    main_menu = c4d.gui.GetMenuResource("M_EDITOR")
    plugins_menu = c4d.gui.SearchPluginMenuResource()

    def add_command(_menu, plugin):
        _menu.InsData(c4d.MENURESOURCE_COMMAND, f"PLUGIN_CMD_{plugin.id}")

    menu = c4d.BaseContainer()
    menu.InsData(c4d.MENURESOURCE_SUBTITLE, "AYON")

    # Define menu commands
    add_command(menu, Creator)
    add_command(menu, Loader)
    add_command(menu, Publish)
    add_command(menu, Manage)
    add_command(menu, Library)
    menu.InsData(c4d.MENURESOURCE_SEPERATOR, True)
    add_command(menu, Workfiles)
    menu.InsData(c4d.MENURESOURCE_SEPERATOR, True)
    add_command(menu, ResetFrameRange)
    add_command(menu, ResetSceneResolution)
    add_command(menu, ResetColorspace)
    menu.InsData(c4d.MENURESOURCE_SEPERATOR, True)
    # add_command(menu, BuildWorkFileCommand)
    add_command(menu, ExperimentalTools)

    if plugins_menu:
        main_menu.InsDataAfter(c4d.MENURESOURCE_STRING, menu, plugins_menu)
    else:
        main_menu.InsData(c4d.MENURESOURCE_STRING, menu)

    # Refresh menu bar
    c4d.gui.UpdateMenus()


def PluginMessage(id, data):
    """Entry point to add menu items to Cinema4D"""
    if id == c4d.C4DPL_BUILDMENU:
        install_menu()


if __name__ == '__main__':
    install_host(Cinema4DHost())

    # Ensure a running QApplication instance without calling `.exec()` on it
    # because this way the Qt UIs run as intended inside Cinema4D.
    from qtpy import QtWidgets  # noqa: E402
    app = QtWidgets.QApplication.instance()
    if not app:
        app = QtWidgets.QApplication([])

    # Do not close app if we close last open Qt window
    app.setQuitOnLastWindowClosed(False)

    # Register commands for the AYON menu
    for command_plugin in [
        Creator,
        Loader,
        Publish,
        Manage,
        Library,
        Workfiles,
        ResetFrameRange,
        ResetSceneResolution,
        ResetColorspace,
        # BuildWorkFileCommand,
        ExperimentalTools,
    ]:
        c4d.plugins.RegisterCommandPlugin(
            id=command_plugin.id,
            str=command_plugin.label,
            info=c4d.PLUGINFLAG_HIDEPLUGINMENU,
            icon=getattr(command_plugin, "icon", None),
            help=getattr(command_plugin, "help", None),
            dat=command_plugin()
        )
