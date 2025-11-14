from __future__ import annotations
import pyblish.api

from ayon_core.pipeline import (
    OptionalPyblishPluginMixin,
    PublishValidationError,
)
from ayon_core.pipeline.publish import RepairAction
from ayon_cinema4d.api.commands import reset_resolution

import c4d


class ValidateResolution(
    pyblish.api.InstancePlugin, OptionalPyblishPluginMixin
):
    """Validate the render resolution setting aligned with DB"""

    order = pyblish.api.ValidatorOrder
    families = ["render"]
    label = "Validate Resolution"
    actions = [RepairAction]
    optional = True

    settings_category = "cinema4d"

    def process(self, instance):
        if not self.is_active(instance.data):
            return
        invalid = self.get_invalid_resolution(instance)
        if invalid:
            raise PublishValidationError(
                "Render resolution is invalid. See log for details.",
                description=(
                    "Wrong render resolution setting. "
                    "Please use repair button to fix it.\n\n"
                ),
            )

    @classmethod
    def get_invalid_resolution(cls, instance):
        # Current resolution for take
        doc = instance.context.data["doc"]
        take_data = doc.GetTakeData()
        take: c4d.modules.takesystem.BaseTake = (
            instance.data["transientData"]["take"]
        )
        rd, _base_take = take.GetEffectiveRenderData(take_data)
        current_width: int = rd[c4d.RDATA_XRES]
        current_height: int = rd[c4d.RDATA_YRES]
        current_pixel_aspect: float = rd[c4d.RDATA_PIXELASPECT]

        # Expected resolution
        width, height, pixel_aspect = cls.get_context_resolution(instance)

        invalid = False
        if current_width != width or current_height != height:
            cls.log.error(
                "Render resolution {}x{} does not match "
                "context resolution {}x{}".format(
                    current_width, current_height, width, height
                )
            )
            invalid = True
        if current_pixel_aspect != pixel_aspect:
            cls.log.error(
                "Render pixel aspect {} does not match "
                "context pixel aspect {}".format(
                    current_pixel_aspect, pixel_aspect
                )
            )
            invalid = True
        return invalid

    @classmethod
    def get_context_resolution(
        cls, instance: pyblish.api.Instance
    ) -> tuple[int, int, float]:
        task_attributes = instance.data["taskEntity"]["attrib"]
        width = task_attributes["resolutionWidth"]
        height = task_attributes["resolutionHeight"]
        pixel_aspect = task_attributes["pixelAspect"]
        return int(width), int(height), float(pixel_aspect)

    @classmethod
    def repair(cls, instance: pyblish.api.Instance):
        if not cls.get_invalid_resolution(instance):
            cls.log.debug("Nothing to repair on instance: {}".format(instance))
            return

        # Note that this always repairs the resolution to the current
        # context and does not reset it to the context of the target instance
        # TODO: Support setting resolution from other context
        reset_resolution()
