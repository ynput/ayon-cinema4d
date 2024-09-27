import c4d

from ayon_cinema4d.api import lib, pipeline, plugin


class CameraLoader(plugin.Cinema4DLoader):
    """Load the camera."""

    color = "orange"
    product_types = {"camera"}
    representations = {"abc"}
    icon = "file-video-o"
    label = "Load Camera"
    order = -11

    def _merge_camera(self, filepath, doc=None):
        """Merge a camera from a file.

        Arguments:
            filepath (str): The full path to the file that contains the camera.
            doc (optional c4d.documents.BaseDocument): The document to put the
                camera in. By default this will be the active document.

        Returns:
            c4d.BaseList2D: The merge camera object
        """

        doc = doc or lib.active_document()
        camera_doc = c4d.documents.LoadDocument(
            filepath,
            c4d.SCENEFILTER_OBJECTS
            # | c4d.SCENEFILTER_MERGESCENE
            | c4d.SCENEFILTER_NOUNDO
            | c4d.SCENEFILTER_IGNOREXREFS
            | c4d.SCENEFILTER_DONTCORRECTOUTPUTFORMAT,
        )

        # TODO: We should include the parent hierarchy of the loaded camera
        #  to ensure the full correct transformations? As such, maybe we should
        #  merge the full camera - and only make editable the camera objects
        for obj in lib.iter_objects(camera_doc.GetFirstObject()):
            # Get internal camera data from the Alembic Generator
            data = {"res": None}
            obj.Message(c4d.MSG_GETREALCAMERADATA, data)
            if data["res"] is not None:
                camera_alembic = obj
                break
        else:
            raise RuntimeError(f"No camera found in {filepath}")

        # The camera should be the only object in the file
        result = c4d.utils.SendModelingCommand(
            command=c4d.MCOMMAND_MAKEEDITABLE,
            list=[camera_alembic],
            doc=doc,
        )
        assert result, "Making the camera editable failed."
        camera = result[0]
        assert camera.GetTypeName() == "Camera", "No camera found in: {}".format(
            filepath
        )

        self.log.info("Loaded camera '%s' from %s", camera.GetName(), filepath)

        return camera

    def _protect_camera(self, camera):
        """Add a protection tag to the camera.

        Arguments:
            camera (c4d.CameraObject): The camera to protect.
        """

        protection_tag = c4d.BaseTag(c4d.Tprotection)
        camera.InsertTag(protection_tag)
        self.log.debug("Added a protection tag to camera '%s'", camera.GetName())

    def load(self, context, name=None, namespace=None, options=None):
        """Load the camera."""

        doc = lib.active_document()
        name, namespace = self.get_name_and_namespace(
            context, name, namespace, doc)
        basename = f"{namespace}_{name}"

        filepath = self.filepath_from_context(context)
        camera = self._merge_camera(filepath, doc)

        doc.InsertObject(camera)
        camera.SetName(str(basename))

        # Set the camera as the active camera
        for basedraw in (doc.GetActiveBaseDraw(), doc.GetRenderBaseDraw()):
            basedraw.SetSceneCamera(camera)

        self._protect_camera(camera)

        container = pipeline.containerise(
            name=str(name),
            namespace=str(namespace),
            nodes=[camera],
            context=context,
            loader=str(self.__class__.__name__),
        )

        c4d.EventAdd()

        return container

    def update(self, container, context):
        doc = lib.active_document()
        container_node = container["node"]
        filepath = self.filepath_from_context(context)

        camera_name = None
        camera_tags = None
        # There should be only 1 camera node here, remove it
        for obj in lib.get_objects_from_container(container_node):
            if obj.GetTypeName() == "Camera":
                camera_name = obj.GetName()
                camera_tags = obj.GetTags()
            obj.Remove()

        # Add new camera
        camera = self._merge_camera(filepath, doc=doc)
        doc.InsertObject(camera)

        if camera_name:
            camera.SetName(str(camera_name))
        if camera_tags:
            for tag in camera_tags:
                camera.InsertTag(tag)

        # Set the camera as the active camera
        for basedraw in (doc.GetActiveBaseDraw(), doc.GetRenderBaseDraw()):
            basedraw.SetSceneCamera(camera)

        self._protect_camera(camera)

        lib.add_objects_to_container(container_node, [camera])

        # Update representation id
        for i, base_container in container_node.GetUserDataContainer():
            if base_container[c4d.DESC_NAME] == "representation":
                container_node[i] = context["representation"]["id"]

        c4d.EventAdd()
