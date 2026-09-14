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
        bake_to_worldspace = instance.data.get("bakeToWorldSpace", True)

        nodes = instance[:]
        # Define extract output file path
        dir_path = self.staging_dir(instance)
        filename = "{0}.abc".format(instance.name)
        path = os.path.join(dir_path, filename)

        export_nodes = self.filter_objects(nodes)
        if not bake_to_worldspace:
            # Local transforms are relative to the parents, so those must
            # be exported too - `filter_objects` may have dropped them.
            export_nodes = self.with_parents(export_nodes)
        if not export_nodes:
            raise publish.KnownPublishError(
                f"No valid objects found to export in members: {nodes}"
            )

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
                doc=doc,
                # Log the applied options to the publish logs
                verbose=True
            )

        representation = {
            "name": "abc",
            "ext": "abc",
            "files": filename,
            "stagingDir": dir_path,
        }
        instance.data.setdefault("representations", []).append(representation)

        self.log.info(f"Extracted instance '{instance.name}' to: {path}")

    def filter_objects(self, nodes):
        return nodes

    def with_parents(self, nodes):
        """Return the nodes plus all their ancestors."""
        result = set(nodes)
        for node in nodes:
            parent = node.GetUp()
            while parent:
                result.add(parent)
                parent = parent.GetUp()
        return list(result)


class ExtractCameraAlembic(ExtractAlembic):
    label = "Camera (Alembic)"
    families = ["camera"]

    camera_types = {
        # Camera
        c4d.Ocamera,
        # Redshift Camera
        c4d.Orscamera
    }

    def filter_objects(self, nodes):
        return [obj for obj in nodes if obj.GetType() in self.camera_types]

