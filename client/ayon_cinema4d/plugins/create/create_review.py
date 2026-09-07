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
    product_base_type = "review"
    product_type = product_base_type
    icon = "video-camera"

    def get_instance_attr_defs(self):
        # `fps` is required by ayon-core ExtractReview
        defs = lib.collect_animation_defs(self.create_context, fps=True)
        defs.extend([
            BoolDef(
                "geometryOnly",
                label="Geometry Only",
                tooltip=(
                    "Render geometry only. Splines, nulls, grid and other"
                    " viewport helpers are excluded from the review."
                ),
                default=True),
            BoolDef(
                "showSplines",
                label="Show Splines",
                tooltip=(
                    "Include splines in the review. Disables 'Geometry"
                    " Only'; grid, handles and other helpers stay"
                    " excluded."
                ),
                default=False),
            BoolDef(
                "showNulls",
                label="Show Nulls",
                tooltip=(
                    "Include nulls in the review. Disables 'Geometry"
                    " Only'; grid, handles and other helpers stay"
                    " excluded."
                ),
                default=False),
        ])
        return defs
