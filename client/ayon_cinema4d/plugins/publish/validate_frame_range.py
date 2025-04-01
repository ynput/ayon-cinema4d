import pyblish.api

from ayon_core.pipeline.publish import (
    OptionalPyblishPluginMixin,
    PublishValidationError,
    RepairAction,
    ValidateContentsOrder,
)


class ValidateFrameRange(
    pyblish.api.InstancePlugin, OptionalPyblishPluginMixin
):
    """Validates the frame ranges.

    This is an optional validator checking if the frame range on instance
    matches the frame range specified for the asset.

    It also validates render frame ranges of render layers.

    Repair action will change everything to match the asset frame range.

    This can be turned off by the artist to allow custom ranges.
    """

    label = "Validate Frame Range"
    order = ValidateContentsOrder
    families = ["camera", "pointcache", "redshiftproxy", "render", "review"]
    optional = True
    actions = [RepairAction]

    settings_category = "cinema4d"

    def process(self, instance: pyblish.api.Instance):
        if not self.is_active(instance.data):
            return

        # Get range from instance's context
        entity = instance.data.get("taskEntity", instance.data["folderEntity"])
        attrib: dict = entity["attrib"]
        frame_start: int = attrib["frameStart"]
        frame_end: int = attrib["frameEnd"]
        handle_start: int = attrib["handleStart"]
        handle_end: int = attrib["handleEnd"]

        # Get instance frame range
        inst_frame_start = int(instance.data.get("frameStart"))
        inst_frame_end = int(instance.data.get("frameEnd"))
        inst_handle_start = int(instance.data.get("handleStart"))
        inst_handle_end = int(instance.data.get("handleEnd"))

        # compare with data on instance
        invalid = False
        checks = {
            "Frame start": (frame_start, inst_frame_start),
            "Frame end": (frame_end, inst_frame_end),
            "Handle start": (handle_start, inst_handle_start),
            "Handle end": (handle_end, inst_handle_end),
        }
        for label, values in checks.items():
            context_value, instance_value = values
            if context_value != instance_value:
                self.log.warning(
                    "{} on instance ({}) does not match with the folder "
                    "({}).".format(label, context_value, instance_value)
                )
                invalid = True

        if invalid:
            raise PublishValidationError(
                "Instance frame range is incorrect.",
                title="Frame Range incorrect",
            )

    @classmethod
    def repair(cls, instance: pyblish.api.Instance):
        from ayon_cinema4d.api.commands import reset_frame_range

        reset_frame_range()
