import os
import c4d

from ayon_core.pipeline import publish
from ayon_cinema4d.api import lib, exporters


class ExtractAlembic(publish.Extractor):
    """Extract a Camera as Alembic.

    The cameras gets baked to world space by default. Only when the instance's
    `bakeToWorldSpace` is set to False it will include its full hierarchy.
    """

    label = "Alembic"
    hosts = ["cinema4d"]
    families = ["pointcache"]

    def process(self, instance):

        doc: c4d.BaseDocument = instance.context.data["doc"]

        # Collect the start and end including handles
        start = instance.data["frameStartHandle"]
        end = instance.data["frameEndHandle"]
        step = instance.data.get("step", 1)
        bake_to_worldspace = instance.data("bakeToWorldSpace", True)

        nodes = instance[:]
        # Define extract output file path
        dir_path = self.staging_dir(instance)
        filename = "{0}.abc".format(instance.name)
        path = os.path.join(dir_path, filename)

        export_nodes = self.filter_objects(nodes)

        # Perform alembic extraction
        with lib.maintained_selection():
            lib.set_selection(doc, export_nodes)

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

    def filter_objects(self, nodes):
        return nodes


class ExtractCameraAlembic(ExtractAlembic):
    label = "Camera (Alembic)"
    families = ["camera"]

    def filter_objects(self, nodes):
        return [obj for obj in nodes if obj.GetType() == c4d.CameraObject]

