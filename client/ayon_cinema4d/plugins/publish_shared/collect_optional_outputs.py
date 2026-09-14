"""Drop optional render outputs that the renderer didn't write.

Runs in the Cinema 4D session for local renders and in the Deadline publish
job for farm renders, so it must not import `c4d` or `ayon_cinema4d.api`.
See `Cinema4DAddon.get_publish_plugin_paths`.
"""
import os

import pyblish.api

# `plugin.LOCAL_RENDER_FAMILY` is not importable without Cinema 4D
RENDER_FAMILIES = ["render", "render.local.c4d"]


class CollectOptionalRenderOutputs(pyblish.api.InstancePlugin):
    """Remove representations marked optional whose files are missing.

    Passes a renderer writes into their own file (Redshift Cryptomatte) are
    collected from the settings before rendering, but whether they end up on
    disk depends on the renderer. A pass that wasn't written must not fail
    the publish of the render itself, so its representation is dropped with
    a warning and `ValidateExpectedFiles` never sees it.
    """

    label = "Collect Optional Render Outputs"
    # After `CollectRenderedFiles` / `CollectRenderLocal`, before the
    # `ValidateExpectedFiles` of ayon-deadline
    order = pyblish.api.CollectorOrder + 0.25
    families = RENDER_FAMILIES
    settings_category = "cinema4d"
    targets = ["local", "farm"]

    def process(self, instance):
        representations = instance.data.get("representations") or []
        for repre in list(representations):
            if not repre.get("optionalOutput"):
                continue

            missing = self.get_missing(repre)
            if not missing:
                self.log.debug(
                    "Optional output '{}' is complete.".format(repre["name"])
                )
                continue

            representations.remove(repre)
            self.log.warning(
                "The renderer did not write the optional output '{}', it is"
                " not published. {} file(s) are missing, the first one is"
                " '{}'.".format(repre["name"], len(missing), missing[0])
            )

    @staticmethod
    def get_missing(repre):
        """Return the files of a representation that are not on disk."""
        files = repre.get("files") or []
        if isinstance(files, str):
            files = [files]
        staging_dir = repre.get("stagingDir") or ""
        return [
            name for name in files
            if not os.path.exists(os.path.join(staging_dir, name))
        ]
