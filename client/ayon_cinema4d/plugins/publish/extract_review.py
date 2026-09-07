import os
import c4d

from ayon_core.pipeline import publish
from ayon_cinema4d.api import exporters


class Cinema4DExtractReview(publish.Extractor):

    label = "Render Review"
    hosts = ["cinema4d"]
    families = ["review"]

    def process(self, instance):

        doc: c4d.BaseDocument = instance.context.data["doc"]

        # Collect the start and end including handles
        start = instance.data["frameStartHandle"]
        end = instance.data["frameEndHandle"]

        # Resolution and fps from the instance, falling back to the folder
        attrib = instance.data.get("folderEntity", {}).get("attrib", {})
        width = instance.data.get("resolutionWidth",
                                  attrib.get("resolutionWidth", 1920))
        height = instance.data.get("resolutionHeight",
                                   attrib.get("resolutionHeight", 1080))
        fps = instance.data.get("fps", attrib.get("fps"))

        # Viewport content. Splines and nulls can only render with
        # 'Geometry Only' disabled, so enabling either implies it.
        show_splines = instance.data.get("showSplines", False)
        show_nulls = instance.data.get("showNulls", False)
        geometry_only = instance.data.get("geometryOnly", True)
        if show_splines or show_nulls:
            geometry_only = False

        # TODO: Allow using members for isolate view
        # nodes = instance[:]
        # Define extract output file path
        dir_path = self.staging_dir(instance)
        filename = "{0}.mp4".format(instance.name)
        path = os.path.join(dir_path, filename)

        # Export selection to camera
        exporters.render_playblast(
            path,
            frame_start=start,
            frame_end=end,
            fps=fps,
            width=width,
            height=height,
            geometry_only=geometry_only,
            show_splines=show_splines,
            show_nulls=show_nulls,
            doc=doc
        )

        representation = {
            "name": "mp4",
            "ext": "mp4",
            "files": filename,
            "stagingDir": dir_path,
            "frameStart": start,
            "frameEnd": end,
            "fps": fps,
            "tags": ["review"],
        }
        instance.data.setdefault("representations", []).append(representation)

        self.log.info(f"Extracted instance '{instance.name}' to: {path}")
