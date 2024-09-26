import c4d

from ayon_cinema4d.api import lib, pipeline, plugin


class AlembicLoader(plugin.Cinema4DLoader):
    """Load the camera."""

    color = "orange"
    product_types = {"*"}
    icon = "file-video-o"
    label = "Load Alembic"
    order = -10
    representations = {"abc"}

    def _load_file(self, filepath):
        """Merge a camera from a file.

        Arguments:
            filepath (str): The full path to the file that contains the camera.

        Returns:
            c4d.documents.BaseDocument: The loaded document.
        """
        return c4d.documents.LoadDocument(
            filepath,
            c4d.SCENEFILTER_OBJECTS
            # | c4d.SCENEFILTER_MERGESCENE
            | c4d.SCENEFILTER_NOUNDO
            | c4d.SCENEFILTER_IGNOREXREFS
            | c4d.SCENEFILTER_DONTCORRECTOUTPUTFORMAT,
        )

    def load(self, context, name=None, namespace=None, options=None):
        """Merge the Alembic into the scene."""

        # Merge the alembic, then containerise the generated nodes so we have
        # access to them on update.
        filepath = self.filepath_from_context(context)

        doc = lib.active_document()

        name, namespace = self.get_name_and_namespace(
            context, name, namespace, doc=doc)

        loaded_doc = self._load_file(filepath)
        nodes = []
        for obj in loaded_doc.GetObjects():
            doc.InsertObject(obj, checknames=True)
            nodes.append(obj)

        # TODO: Also containerize all children objects to ensure we keep them
        #   linked explicitly

        container = pipeline.containerise(
            name=str(name),
            namespace=str(namespace),
            nodes=nodes,
            context=context,
            loader=str(self.__class__.__name__),
        )

        c4d.EventAdd()

        return container

    def update(self, container, context):

        container_node = container["node"]
        filepath = self.filepath_from_context(context)

        # todo: Add new objects
        # From the loaded (external) document iterate all its objects, any
        # new ones insert them into our current document at the right "place"
        # in the hierarchy.
        # Any already existing ones, do nothing (unless there are specific
        # updates we want to transfer that it doesn't automatically)
        # loaded_doc = self._load_file(filepath)
        # lib.add_objects_to_container(container_node, [camera])

        # todo: Remove or 'tag' removed objects
        # Any removed ones, keep them dangling in their "broken" state. It
        # looks like Cinema4D is fine with that.
        # for obj in remove:
        #     obj.Remove()

        # todo: Update existing objects
        members = list(lib.get_objects_from_container(container_node))
        objects = set(members)
        for obj in members:
            children = lib.get_all_children(obj)
            objects.update(children)

        for obj in objects:
            # Only update those with alembic path set
            if obj[c4d.ALEMBIC_PATH]:
                obj[c4d.ALEMBIC_PATH] = filepath
                continue

            # Or if we find a Alembic Morph tag update that instead
            # This will exist on the object if it was made editable.
            alembic_morph = obj.GetTag(c4d.Talembicmorphtag)
            if alembic_morph:
                alembic_morph[c4d.ALEMBIC_MT_PATH] = filepath

        # Update representation id
        for i, base_container in container_node.GetUserDataContainer():
            if base_container[c4d.DESC_NAME] == "representation":
                container_node[i] = context["representation"]["id"]

        c4d.EventAdd()

    def remove(self, container):
        """Remove all sub containers"""
        container_node = container["node"]
        for obj in lib.get_objects_from_container(container_node):
            if obj:
                obj.Remove()
        container_node.Remove()

        c4d.EventAdd()
