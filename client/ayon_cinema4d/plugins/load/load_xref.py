import c4d

from ayon_cinema4d.api import lib, pipeline, plugin


class XRefLoader(plugin.Cinema4DLoader):
    """Load a file as XRef."""

    label = "Load XRef"

    product_base_types = {"*"}
    product_types = product_base_types
    representations = {"c4d", "abc", "fbx"}
    icon = "code-fork"
    color = "orange"
    order = -8

    def load(self, context, name=None, namespace=None, options=None):
        """Load the asset as XRef.

        Todo:
            - Find out how to set the path to non-relative.
            - Find out how to set the namespace separator.
        """
        filepath = self.filepath_from_context(context)
        doc = lib.active_document()
        name, namespace = self.get_name_and_namespace(
            context, name, namespace, doc)
        basename = f"{namespace}_{name}"

        xref = c4d.BaseList2D(c4d.Oxref)
        xref.SetName(basename)
        doc.InsertObject(xref)
        xref.SetParameter(
            c4d.ID_CA_XREF_FILE,
            filepath,
            c4d.DESCFLAGS_SET_USERINTERACTION
        )
        xref.SetParameter(
            c4d.ID_CA_XREF_NAMESPACE,
            str(namespace),
            c4d.DESCFLAGS_SET_USERINTERACTION
        )
        c4d.EventAdd()
        # c4d.ID_CA_XREF_FILE       # filepath
        # c4d.ID_CA_XREF_NAMESPACE  # namespace
        # c4d.ID_CA_XREF_LOADED     # loaded checkbox
        # c4d.ID_CA_XREF_RELATIVE   # Relative to project

        container = pipeline.containerise(
            name=str(name),
            namespace=str(namespace),
            nodes=[xref],
            context=context,
            loader=str(self.__class__.__name__),
        )

        return container

    def update(self, container, context):
        filepath = self.filepath_from_context(context)
        container_node = container["node"]

        # There should be only 1 xref node
        for xref in lib.get_objects_from_container(container_node):
            if xref.GetTypeName() == "XRef":
                # This requires `c4d.DESCFLAGS_SET_USERINTERACTION`
                # which will unfortunately prompt the user to confirm it.
                # There is no other way, see:
                # https://developers.maxon.net/forum/topic/15728/update-xref-filepath-without-user-interaction  # noqa: E402
                xref.SetParameter(
                    c4d.ID_CA_XREF_FILE,
                    filepath,
                    c4d.DESCFLAGS_SET_USERINTERACTION,
                )

        # Update the representation id
        for i, base_container in container_node.GetUserDataContainer():
            if base_container[c4d.DESC_NAME] == "representation":
                container_node[i] = context["representation"]["id"]
                break

        c4d.EventAdd()

    def remove(self, container):
        """Remove all sub containers"""
        container_node = container["node"]
        for obj in lib.get_objects_from_container(container_node):
            obj.Remove()
        container_node.Remove()
        c4d.EventAdd()
