import os
import c4d

from ayon_core.pipeline import publish
from ayon_cinema4d.api import lib, exporters


class ExtractRedshiftProxy(publish.Extractor):
    """Extract a Redshift Proxy"""

    label = "Redshift Proxy"
    hosts = ["cinema4d"]
    families = ["redshiftproxy"]

    def process(self, instance):

        doc: c4d.BaseDocument = instance.context.data["doc"]

        # Collect the start and end including handles
        start = instance.data["frameStartHandle"]
        end = instance.data["frameEndHandle"]
        step = instance.data.get("step", 1)

        export_nodes = instance[:]
        # Define extract output file path
        dir_path = self.staging_dir(instance)

        # Add the `_` suffix because Redshift Proxy export will add the
        # frame numbers to the file names before the extension.
        filename = "{0}_.rs".format(instance.name)
        path = os.path.join(dir_path, filename)

        # TODO: Set the document timeline to 'fit' the extra frame start and
        #  frame end because redshift export fails if the frame range is
        #  outside of the current document's timeline range.

        # Perform alembic extraction
        with lib.maintained_selection():
            lib.set_selection(doc, export_nodes)

            # Export selection to camera
            exporters.extract_redshiftproxy(
                path,
                frame_start=start,
                frame_end=end,
                frame_step=step,
                selection=True,
                doc=doc,
                # Log the applied options to the publish logs
                verbose=True
            )

        # The Redshift exporter will add the frame numbers to the filepath
        # before the extension. So we collect the resulting files.
        frame_filepaths: "list[str]" = []
        for frame in range(int(start), int(end) + 1):
            head, tail = os.path.splitext(path)
            frame_filepath = f"{head}{frame:04d}{tail}"
            if not os.path.exists(frame_filepath):
                raise publish.PublishError(
                    "Expected exported Redshift Proxy frame not found: "
                    f"{frame_filepath}")

            frame_filepaths.append(frame_filepath)

        # Define the collected filename with the frame numbers
        frame_filenames = [os.path.basename(path) for path in frame_filepaths]
        if len(frame_filepaths) == 1:
            files = frame_filenames[0]
        else:
            files = frame_filenames

        representation = {
            "name": "rs",
            "ext": "rs",
            "files": files,
            "stagingDir": dir_path,
        }
        instance.data.setdefault("representations", []).append(representation)

        self.log.info(f"Extracted instance '{instance.name}' to: {path}")
