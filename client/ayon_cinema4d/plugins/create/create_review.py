from ayon_core.lib import BoolDef
from ayon_cinema4d.api import (
    lib,
    plugin
)


class CreateReview(plugin.Cinema4DCreator):
    """Viewport render reviewable"""

    identifier = "io.ayon.creators.cinema4d.review"
    label = "Review"
    description = __doc__
    product_type = "review"
    icon = "video-camera"

    def get_instance_attr_defs(self):
        defs = lib.collect_animation_defs(self.create_context)
        return defs
