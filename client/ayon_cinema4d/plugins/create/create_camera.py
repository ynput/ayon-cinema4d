from ayon_core.lib import BoolDef
from ayon_cinema4d.api import (
    lib,
    plugin
)


class CreateCamera(plugin.Cinema4DCreator):
    """Single baked camera"""

    identifier = "io.ayon.creators.cinema4d.camera"
    label = "Camera"
    description = __doc__
    product_type = "camera"
    icon = "video-camera"

    def get_instance_attr_defs(self):
        defs = lib.collect_animation_defs(self.create_context)
        defs.append(
            BoolDef(
                "bakeToWorldSpace",
                label="Bake to World Space",
                tooltip=(
                    "Bake to world space by default, when this is disabled it "
                    " will also include the parent hierarchy in the baked"
                    " results"
                ),
                default=True)
        )
        return defs


#MGE v0.1.3