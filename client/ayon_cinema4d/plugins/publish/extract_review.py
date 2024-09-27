import os
import c4d

from ayon_core.pipeline import publish
from ayon_cinema4d.api import exporters


class ExtractReview(publish.Extractor):

    label = "Render Review"
    hosts = ["cinema4d"]
    families = ["review"]

    def process(self, instance):

        doc: c4d.BaseDocument = instance.context.data["doc"]

        # Collect the start and end including handles
        start = instance.data["frameStartHandle"]
        end = instance.data["frameEndHandle"]

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
            doc=doc
        )

        representation = {
            'name': 'mp4',
            'ext': 'mp4',
            'files': filename,
            "stagingDir": dir_path,
        }
        instance.data.setdefault("representations", []).append(representation)

        self.log.info(f"Extracted instance '{instance.name}' to: {path}")
