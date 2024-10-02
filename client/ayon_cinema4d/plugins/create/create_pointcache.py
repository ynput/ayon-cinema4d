from ayon_cinema4d.api import (
    lib,
    plugin
)


class CreatePointcache(plugin.Cinema4DCreator):
    """Geometry pointcache using Alembic"""

    identifier = "io.ayon.creators.cinema4d.pointcache"
    label = "Pointcache"
    description = __doc__
    product_type = "pointcache"
    icon = "cubes"

    def get_instance_attr_defs(self):
        defs = lib.collect_animation_defs(self.create_context)
        return defs
