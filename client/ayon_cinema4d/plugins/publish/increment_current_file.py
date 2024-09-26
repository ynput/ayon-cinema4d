import pyblish.api

from ayon_core.lib import version_up
from ayon_core.pipeline import registered_host
from ayon_core.pipeline.publish import (
    KnownPublishError,
    OptionalPyblishPluginMixin
)


class IncrementCurrentFile(pyblish.api.ContextPlugin,
                           OptionalPyblishPluginMixin):
    """Increment the current file.

    Saves the current scene with an increased version number.
    """
    label = "Increment current file"
    order = pyblish.api.IntegratorOrder + 9.0
    families = ["*"]
    hosts = ["cinema4d"]
    optional = True

    def process(self, context):
        if not self.is_active(context.data):
            return

        # Filename must not have changed since collecting
        host = registered_host()
        current_file = host.current_file()
        if context.data["currentFile"] != current_file:
            raise KnownPublishError(
                "Collected filename mismatches from current scene name."
            )

        new_filepath = version_up(current_file)
        host.save_workfile(new_filepath)
