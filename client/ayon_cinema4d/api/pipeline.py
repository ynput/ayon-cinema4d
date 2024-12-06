import os
import logging
import contextlib

import c4d
import pyblish.api

from ayon_core.lib import (
    register_event_callback,
    is_headless_mode_enabled
)
from ayon_core.host import HostBase, IWorkfileHost, ILoadHost, IPublishHost
from ayon_core.pipeline import (
    get_current_folder_path,
    get_current_task_name,
    register_loader_plugin_path,
    register_creator_plugin_path,
    AYON_CONTAINER_ID,
)
from .workio import (
    open_file,
    save_file,
    file_extensions,
    has_unsaved_changes,
    current_file
)
import ayon_cinema4d

from . import lib, plugin

log = logging.getLogger("ayon_cinema4d")

HOST_DIR = os.path.dirname(os.path.abspath(ayon_cinema4d.__file__))
PLUGINS_DIR = os.path.join(HOST_DIR, "plugins")
PUBLISH_PATH = os.path.join(PLUGINS_DIR, "publish")
LOAD_PATH = os.path.join(PLUGINS_DIR, "load")
CREATE_PATH = os.path.join(PLUGINS_DIR, "create")
INVENTORY_PATH = os.path.join(PLUGINS_DIR, "inventory")

AYON_CONTAINERS = lib.AYON_CONTAINERS
AYON_CONTEXT_CREATOR_IDENTIFIER = "io.ayon.create.context"


class Cinema4DHost(HostBase, IWorkfileHost, ILoadHost, IPublishHost):
    name = "cinema4d"

    def __init__(self):
        super(Cinema4DHost, self).__init__()

    def install(self):
        # process path mapping
        # dirmap_processor = Cinema4DDirmap("cinema4d", project_settings)
        # dirmap_processor.process_dirmap()

        pyblish.api.register_plugin_path(PUBLISH_PATH)
        pyblish.api.register_host("cinema4d")

        register_loader_plugin_path(LOAD_PATH)
        register_creator_plugin_path(CREATE_PATH)
        # TODO: Register only when any inventory actions are created
        # register_inventory_action_path(INVENTORY_PATH)
        self.log.info(PUBLISH_PATH)

        register_event_callback("taskChanged", on_task_changed)

    def open_workfile(self, filepath):
        return open_file(filepath)

    def save_workfile(self, filepath=None):
        return save_file(filepath)

    def get_current_workfile(self):
        return current_file()

    def workfile_has_unsaved_changes(self):
        return has_unsaved_changes()

    def get_workfile_extensions(self):
        return file_extensions()

    def get_containers(self):
        return iter_containers()

    @contextlib.contextmanager
    def maintained_selection(self):
        with lib.maintained_selection():
            yield

    def _get_context_node(self, create_if_not_exists=False):
        doc = lib.active_document()
        context_node = None
        for creator_id, obj in plugin.iter_instance_objects(doc):
            if creator_id == AYON_CONTEXT_CREATOR_IDENTIFIER:
                context_node = obj

        if context_node is None and create_if_not_exists:
            context_node = plugin.create_selection([], name="AYON_context")
            plugin.parent_to_ayon_null(context_node)

        return context_node

    def update_context_data(self, data, changes):
        if not data:
            return

        context_node = self._get_context_node(create_if_not_exists=True)
        data["id"] = plugin.AYON_INSTANCE_ID
        data["creator_identifier"] = AYON_CONTEXT_CREATOR_IDENTIFIER
        lib.imprint(context_node, data)

    def get_context_data(self):
        context_node = self._get_context_node()
        if context_node is None:
            return {}

        data = lib.read(context_node)

        # Pop our custom data that we use to find the node again
        data.pop("id", None)
        data.pop("creator_identifier", None)

        return data


def parse_container(container):
    """Return the container node's full container data.

    Args:
        container (str): A container node name.

    Returns:
        dict[str, Any]: The container schema data for this container node.

    """
    data = lib.read(container)

    # Backwards compatibility pre-schemas for containers
    data["schema"] = data.get("schema", "ayon:container-3.0")

    # Append transient data
    data["objectName"] = container.GetName()
    data["node"] = container

    return data


def iter_containers(doc=None):
    """Yield all objects in the active document that have 'id' attribute set
    matching an AYON container ID"""
    doc = doc or c4d.documents.GetActiveDocument()
    containers = lib.iter_objects(doc.GetFirstObject())
    for container in containers:
        if lib.get_object_user_data_by_name(container, "id") != AYON_CONTAINER_ID:  # noqa
            continue

        data = parse_container(container)
        yield data


def get_containers_layer(doc=None):
    """Get the layer that holds all container objects.

    To make the scene less cluttered the containers (selection objects) are put
    in a layer 'AYON_CONTAINERS'. This layer is hidden in the outliner.

    Arguments:
        doc (optional c4d.documents.BaseDocument): The document to work on. If
            it is None it uses the active document.
    """

    doc = doc or lib.active_document()
    layer_root = doc.GetLayerObjectRoot()
    for layer in layer_root.GetChildren():
        if layer.GetName() == AYON_CONTAINERS:
            return layer

    layer = c4d.documents.LayerObject()
    layer.SetName(AYON_CONTAINERS)
    layer.InsertUnder(layer_root)
    layer[c4d.ID_LAYER_MANAGER] = False
    layer[c4d.ID_LAYER_VIEW] = False
    layer[c4d.ID_LAYER_RENDER] = False
    layer[c4d.ID_LAYER_COLOR] = c4d.Vector(0.3, 0.66, 0.96)
    layer[c4d.ID_LAYER_LOCKED] = True

    c4d.EventAdd()

    return layer


def containerise(name,
                 namespace,
                 nodes,
                 context,
                 loader,
                 suffix="_CON"):
    """Bundle `nodes` into an assembly and imprint it with metadata

    Containerisation enables a tracking of version, author and origin
    for loaded assets.

    Arguments:
        name (str): Name of resulting assembly
        namespace (str): Namespace under which to host container
        nodes (list): Long names of nodes to containerise
        context (dict): Asset information
        loader (str): Name of loader used to produce this container.
        suffix (str, optional): Suffix of container, defaults to `_CON`.

    Returns:
        container (c4d.BaseObject): OSelection BaseObject container

    """

    container_name = lib.get_unique_namespace(
        name,
        prefix=namespace + "_",
        suffix=suffix
    )
    with lib.undo_chunk():
        container = c4d.BaseObject(c4d.Oselection)
        container.SetName(container_name)
        in_exclude_data = container[c4d.SELECTIONOBJECT_LIST]
        for node in nodes:
            in_exclude_data.InsertObject(node, 1)
        container[c4d.SELECTIONOBJECT_LIST] = in_exclude_data
        doc = lib.active_document()
        doc.InsertObject(container)

        imprint_container(
            container,
            name,
            namespace,
            context,
            loader
        )

        # Add the container to the AYON_CONTAINERS layer
        avalon_layer = get_containers_layer(doc=doc)
        container.SetLayerObject(avalon_layer)
        # Hide the container in the Object Manager
        # container.ChangeNBit(c4d.NBIT_OHIDE, c4d.NBITCONTROL_SET)
        c4d.EventAdd()

    return container


def imprint_container(
    container,
    name,
    namespace,
    context,
    loader
):
    """Imprints an object with container metadata and hides it from the user
    by adding it into a hidden layer.
    Arguments:
        container (c4d.BaseObject): The object to imprint.
        name (str): Name of resulting assembly
        namespace (str): Namespace under which to host container
        context (dict): Asset information
        loader (str): Name of loader used to produce this container.
    """
    data = {
        "schema": "ayon:container-3.0",
        "id": AYON_CONTAINER_ID,
        "name": name,
        "namespace": namespace,
        "loader": str(loader),
        "representation": str(context["representation"]["id"]),
    }

    lib.imprint(container, data, group="AYON")


def on_task_changed():

    if not is_headless_mode_enabled():
        # Get AYON Context manu command plugin (menu item) by its unique id.
        ayon_context = c4d.plugins.FindPlugin(1064309)
        # Update its value with the new context.
        ayon_context.SetName(
            "{}, {}".format(get_current_folder_path(), get_current_task_name())
        )
