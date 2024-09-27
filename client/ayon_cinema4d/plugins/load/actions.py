"""A module containing generic loader actions that will display in the Loader.

"""
import math

import c4d

from ayon_core.pipeline import load
from ayon_cinema4d.api import lib


def _set_frame_range(frame_start: int, frame_end: int, fps: float):
    i_fps = int(math.ceil(fps))
    bt_frame_start = c4d.BaseTime(int(frame_start), i_fps)
    bt_frame_end = c4d.BaseTime(int(frame_end), i_fps)
    doc = lib.active_document()

    # set document fps
    doc.SetFps(i_fps)

    # set document frame range
    doc.SetMinTime(bt_frame_start)
    doc.SetMaxTime(bt_frame_end)
    doc.SetLoopMinTime(bt_frame_start)
    doc.SetLoopMaxTime(bt_frame_end)


class SetFrameRangeLoader(load.LoaderPlugin):
    """Set frame range excluding pre- and post-handles"""

    product_types = {
        "animation",
        "camera",
        "pointcache",
        "vdbcache",
        "usd",
        "render",
        "plate",
        "mayaScene",
        "review"
    }
    representations = {"*"}

    label = "Set frame range"
    order = 11
    icon = "clock-o"
    color = "white"

    def load(self, context, name=None, namespace=None, options=None):

        version_attributes = context["version"]["attrib"]

        frame_start = version_attributes.get("frameStart")
        frame_end = version_attributes.get("frameEnd")
        if frame_start is None or frame_end is None:
            print(
                "Skipping setting frame range because start or "
                "end frame data is missing.."
            )
            return

        fps = version_attributes["fps"]
        _set_frame_range(frame_start, frame_end, fps)


class SetFrameRangeWithHandlesLoader(load.LoaderPlugin):
    """Set frame range including pre- and post-handles"""

    product_types = {
        "animation",
        "camera",
        "pointcache",
        "vdbcache",
        "usd",
        "render",
        "plate",
        "mayaScene",
        "review"
    }
    representations = {"*"}

    label = "Set frame range (with handles)"
    order = 12
    icon = "clock-o"
    color = "white"

    def load(self, context, name=None, namespace=None, options=None):

        version_attributes = context["version"]["attrib"]

        frame_start = version_attributes.get("frameStart")
        frame_end = version_attributes.get("frameEnd")
        if frame_start is None or frame_end is None:
            print(
                "Skipping setting frame range because start or "
                "end frame data is missing.."
            )
            return

        # Include handles
        frame_start -= version_attributes.get("handleStart", 0)
        frame_end += version_attributes.get("handleEnd", 0)

        fps = version_attributes["fps"]
        _set_frame_range(frame_start, frame_end, fps)
