import os
import inspect

import pyblish.api
import c4d

from ayon_core.pipeline.publish import (
    OptionalPyblishPluginMixin,
    PublishValidationError,
    RepairAction,
)

RENDER_DATA_KEYS: dict[int, str] = {
    c4d.RDATA_PATH: "Regular Image path",
    c4d.RDATA_MULTIPASS_FILENAME: "Multi-Pass Image path",
}


class ValidateRenderRelativePaths(
    pyblish.api.InstancePlugin, OptionalPyblishPluginMixin
):
    """Validates render scene does not use relative paths.

    Because the scene will be rendered from the published folder if it renders
    to a relative path then the output will end up in the publish folder
    instead of the expected location.

    """
    label = "Validate Render Relative Paths"
    order = pyblish.api.ValidatorOrder
    families = ["render"]
    optional = False
    actions = [RepairAction]

    settings_category = "cinema4d"

    def process(self, instance: pyblish.api.Instance):
        if not self.is_active(instance.data):
            return

        doc: c4d.documents.BaseDocument = instance.context.data["doc"]
        take_data = doc.GetTakeData()
        take: c4d.modules.takesystem.BaseTake = (
            instance.data["transientData"]["take"]
        )
        render_data, base_take = take.GetEffectiveRenderData(take_data)
        invalid: bool = False

        # Regular image
        save_image: bool = render_data[c4d.RDATA_SAVEIMAGE]
        if save_image:
            token_path: str = render_data[c4d.RDATA_PATH]
            if not os.path.isabs(token_path):
                self.log.error(
                    "Regular image Render output path is relative:\n"
                    f"{token_path}"
                )
                invalid = True

        # Multi-Pass image
        save_multipass_image: bool = render_data[c4d.RDATA_MULTIPASS_SAVEIMAGE]
        if save_multipass_image:
            token_path: str  = render_data[c4d.RDATA_MULTIPASS_FILENAME]
            if not os.path.isabs(token_path):
                self.log.error(
                    "Multi-Pass Image render output path is relative:\n"
                    f"{token_path}",
                )
                invalid = True

        if invalid:
            raise PublishValidationError(
                "Please use an absolute path for render output.",
                description=self.get_description()
            )


    @classmethod
    def repair(cls, instance: pyblish.api.Instance):

        current_file = instance.context.data["currentFile"]
        if not current_file:
            raise RuntimeError(
                "Cannot repair relative paths because the current "
                "file path is unknown. Please save the Cinema 4D "
                "project and try again."
            )
        current_folder = os.path.dirname(current_file)

        doc: c4d.documents.BaseDocument = instance.context.data["doc"]
        take_data = doc.GetTakeData()
        take: c4d.modules.takesystem.BaseTake = (
            instance.data["transientData"]["take"]
        )
        render_data, base_take = take.GetEffectiveRenderData(take_data)

        for key, label in RENDER_DATA_KEYS.items():
            token_path: str = render_data[key]

            # Strip leading dot from ./ or .\ start if present
            if token_path.startswith(("./", ".\\")):
                token_path = token_path[2:]

            if not os.path.isabs(token_path):
                render_data[key] = os.path.join(current_folder, token_path)

        c4d.EventAdd()

    @classmethod
    def get_description(cls) -> str:
        return inspect.cleandoc(
            """### Render paths are relative
            
            The render output paths must be absolute paths.

            Relative paths can lead to renders being saved in unexpected 
            locations due to the render possibly occurring from a published 
            workfile.
            
            Use the 'Repair' action to convert relative paths to 
            absolute paths based on the current Cinema4D project folder.
        """)
