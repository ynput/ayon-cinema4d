from ayon_cinema4d.api import plugin


class CreateRender(plugin.Cinema4DCreator):
    """Render"""

    identifier = "io.ayon.creators.cinema4d.render"
    label = "Render"
    description = __doc__
    product_type = "render"
    icon = "eye"

    def get_pre_create_attr_defs(self):
        # Avoid inherited "Use Selection" attribute
        return []
