import os
import c4d

from ayon_core.pipeline import publish
from ayon_cinema4d.api import lib, exporters


class ExtractCameraAlembic(publish.Extractor):
    """Extract a Camera as Alembic.

    The cameras gets baked to world space by default. Only when the instance's
    `bakeToWorldSpace` is set to False it will include its full hierarchy.

    """

    label = "Camera (Alembic)"
    hosts = ["cinema4d"]
    families = ["camera"]

    def process(self, instance):
        doc = c4d.documents.GetActiveDocument()
        # Collect the start and end including handles
        start = instance.data["frameStartHandle"]
        end = instance.data["frameEndHandle"]

        step = instance.data.get("step", 1)
        bake_to_worldspace = instance.data("bakeToWorldSpace", True)

        # get cameras
        nodes = instance[:]
        cameras = [obj for obj in nodes if obj.GetType() == c4d.CameraObject]

        # Define extract output file path
        dir_path = self.staging_dir(instance)
        filename = "{0}.abc".format(instance.name)
        path = os.path.join(dir_path, filename)

        # Perform alembic extraction
        with lib.maintained_selection():
            # Select the cameras
            doc.SetSelection(None, c4d.SELECTION_NEW)  # clear selection
            for camera in cameras:
                doc.SetSelection(camera.obj, c4d.SELECTION_ADD)

            # Export selection to camera
            exporters.extract_alembic(
                path,
                frame_start=start,
                frame_end=end,
                frame_step=step,
                selection=True,
                global_matrix=bake_to_worldspace,
                doc=doc
            )

        representation = {
            'name': 'abc',
            'ext': 'abc',
            'files': filename,
            "stagingDir": dir_path,
        }
        instance.data.setdefault("representations", []).append(representation)

        self.log.info(f"Extracted instance '{instance.name}' to: {path}")
