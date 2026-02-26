from ayon_cinema4d.api import (
    lib,
    plugin
)


class CreateRedshiftProxy(plugin.Cinema4DCreator):
    """Redshift Proxy"""

    identifier = "io.ayon.creators.cinema4d.redshiftproxy"
    label = "Redshift Proxy"
    product_base_type = "redshiftproxy"
    product_type = product_base_type
    description = __doc__
    icon = "cubes"

    def get_instance_attr_defs(self):
        defs = lib.collect_animation_defs(self.create_context)
        return defs
