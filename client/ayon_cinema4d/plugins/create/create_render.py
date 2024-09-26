from ayon_core.lib import BoolDef
from ayon_cinema4d.api import (
    lib,
    plugin
)


class CreateRender(plugin.Cinema4DCreator):
    """Render"""

    identifier = "io.ayon.creators.cinema4d.render"
    label = "Render"
    description = __doc__
    product_type = "render"
    icon = "eye"

    def get_instance_attr_defs(self):
        defs = lib.collect_animation_defs(self.create_context)
        return defs
