from abc import ABC, abstractmethod
import typing

import c4d

from ayon_core.pipeline import (
    Creator,
    CreatedInstance,
    LoaderPlugin,
    AYON_INSTANCE_ID,
    AVALON_INSTANCE_ID
)
from ayon_core.lib import BoolDef

from ayon_cinema4d.api import pipeline

from . import lib

if typing.TYPE_CHECKING:
    from typing import Optional, List, Tuple, Union


def iter_instance_objects(doc):
    instance_ids = {AYON_INSTANCE_ID, AVALON_INSTANCE_ID}

    for obj in lib.iter_objects(doc.GetFirstObject()):
        if lib.get_object_user_data_by_name(obj, "id") not in instance_ids:
            continue

        creator_id = lib.get_object_user_data_by_name(
            obj, "creator_identifier")
        if not creator_id:
            continue

        yield creator_id, obj


def cache_instance_data(shared_data):
    """Cache instances for Creators shared data.

    Create `cinema4d_cached_instances` key when needed in shared data and
    fill it with all collected instances from the scene under its
    respective creator identifiers.

    Args:
        shared_data(Dict[str, Any]): Shared data.

    """
    if shared_data.get('cinema4d_cached_instances') is None:
        cache = {}
        doc = lib.active_document()
        for creator_id, obj in iter_instance_objects(doc):
            cache.setdefault(creator_id, []).append(obj)

        shared_data["cinema4d_cached_instances"] = cache

    return shared_data


def create_selection(
    nodes: "Optional[List[c4d.BaseObject]]" = None,
    name: "Optional[str]" = None
):

    name = name or lib.get_unique_namespace("selection")

    with lib.undo_chunk():

        # Create base object to hold selection
        container = c4d.BaseObject(c4d.Oselection)
        container.SetName(name)

        # Add nodes as members
        if nodes:
            lib.add_objects_to_container(container, nodes)

        # Add to current document
        doc = lib.active_document()
        doc.InsertObject(container)

        c4d.EventAdd()
        return container


def parent_to_ayon_null(obj, doc=None):
    # Find or create the root node
    # TODO: Improve how we find the node to parent to instead of just assuming
    #  it is the first node named "AYON"
    doc = doc or lib.active_document()
    root = doc.SearchObject("AYON")
    if not root:
        root = c4d.BaseList2D(c4d.Onull)
        root.SetName("AYON")
        doc.InsertObject(root)

    obj.InsertUnder(root)
    c4d.EventAdd()


class Cinema4DCreator(Creator):
    default_variants = ["Main"]
    settings_category = "cinema4d"
    skip_discovery = True

    def create(self, product_name, instance_data, pre_create_data):

        # Register the CreatedInstance
        doc = c4d.documents.GetActiveDocument()
        nodes = list()
        if pre_create_data.get("use_selection"):
            nodes = doc.GetActiveObjects(c4d.GETACTIVEOBJECTFLAGS_CHILDREN)

        instance_node = create_selection(nodes, name=product_name)
        parent_to_ayon_null(instance_node)

        # Enforce forward compatibility to avoid the instance to default
        # to the legacy `AVALON_INSTANCE_ID`
        instance_data["id"] = AYON_INSTANCE_ID
        # Use the uniqueness of the node in Cinema4D as the instance id
        instance_data["instance_id"] = str(hash(instance_node))
        product_type = instance_data.get("productType")
        if not product_type:
            product_type = self.product_base_type
        instance = CreatedInstance(
            product_base_type=self.product_base_type,
            product_type=product_type,
            product_name=product_name,
            data=instance_data,
            creator=self,
        )

        # Store the instance data
        data = instance.data_to_store()
        self._imprint(instance_node, data)

        # Insert the transient data
        instance.transient_data["instance_node"] = instance_node

        self._add_instance_to_context(instance)

        return instance

    def collect_instances(self):
        shared_data = cache_instance_data(self.collection_shared_data)
        for obj in shared_data["cinema4d_cached_instances"].get(
                self.identifier, []):

            data = self._read_instance_node(obj)

            # Add instance
            created_instance = CreatedInstance.from_existing(data, self)

            # Collect transient data
            created_instance.transient_data["instance_node"] = obj

            self._add_instance_to_context(created_instance)

    def update_instances(self, update_list):
        for created_inst, _changes in update_list:
            new_data = created_inst.data_to_store()
            node = created_inst.transient_data["instance_node"]
            self._imprint(node, new_data)
        c4d.EventAdd()

    def remove_instances(self, instances):
        for instance in instances:

            # Remove node from the scene
            node = instance.transient_data["instance_node"]
            if node:
                node.Remove()

            # Remove the collected CreatedInstance to remove from UI directly
            self._remove_instance_from_context(instance)
        c4d.EventAdd()

    def _imprint(self, node, data):

        # Do not store instance id since it's the node hash
        data.pop("instance_id", None)

        lib.imprint(node, data, group="AYON")

    def _read_instance_node(self, obj) -> dict:
        data = lib.read(obj)
        data["instance_id"] = str(hash(obj))
        return data

    def get_pre_create_attr_defs(self):
        return [
            BoolDef("use_selection",
                    label="Use selection",
                    default=True)
        ]


class Cinema4DLoader(LoaderPlugin):
    hosts = ["cinema4d"]
    settings_category = "cinema4d"
    skip_discovery = True

    def get_name_and_namespace(self, context, name, namespace, doc=None):
        if doc is None:
            doc = lib.active_document()

        product_name = context["product"]["name"]
        folder_name: str = context["folder"]["name"]
        namespace = namespace or lib.get_unique_namespace(
            folder_name,
            prefix="_" if folder_name[0].isdigit() else "",
            suffix="",
            doc=doc,
        )
        name = name or product_name

        return name, namespace

    def remove(self, container):
        """Remove all sub containers"""
        container_node = container["node"]
        for obj in lib.get_objects_from_container(container_node):
            obj.Remove()
        container_node.Remove()
        c4d.EventAdd()


class Cinema4DSingleObjLoader(Cinema4DLoader, ABC):
    """Base Loader plug-in that manages a single Cinema4D object with a
    filepath parameter.

    Instead of containerizing on a hidden selection object this imprints the
    node itself as a container."""
    skip_discovery = True

    @property
    @abstractmethod
    def _node_type_id(self) -> int:
        """The node type id to create and manage."""
        pass

    @property
    @abstractmethod
    def _filepath_attribute(self) -> "Union[int, Tuple[int, int]]":
        """Return the id for the filepath attribute on the node type.

        This is usually an `int` constant, but for some nodes like Redshift
        Proxies these are a tuple of two ids.

        """
        pass

    def set_obj_for_context(self, obj, context, is_update=False):
        """Update the object for the new context. This will be called on load
        and update to configure the object for the new context, like setting
        the filepath.

        This can be inherited on child classes to do additional things on load
        or update.

        Arguments:
            obj (c4d.BaseObject): The managed object.
            context (dict[str, Any]): The full representation context.
            is_update (bool): Whether this is part of an `update` call or
                first `load`.

        """
        filepath = self.filepath_from_context(context)
        obj[self._filepath_attribute] = filepath

    def load(self, context, name=None, namespace=None, options=None):

        doc = lib.active_document()

        name, namespace = self.get_name_and_namespace(
            context, name, namespace, doc=doc)

        # Create object
        obj = c4d.BaseObject(self._node_type_id)
        obj.SetName(name)
        doc.InsertObject(obj)

        self.set_obj_for_context(obj, context)

        container = pipeline.imprint_container(
            obj,
            name=str(name),
            namespace=str(namespace),
            context=context,
            loader=str(self.__class__.__name__),
        )

        c4d.EventAdd()

        return container

    def update(self, container, context):

        obj = container["node"]

        # Update filepath
        if obj.CheckType(self._node_type_id):
            self.set_obj_for_context(obj, context)

        # Update representation id
        for i, base_container in obj.GetUserDataContainer():
            if base_container[c4d.DESC_NAME] == "representation":
                obj[i] = context["representation"]["id"]

        c4d.EventAdd()

    def remove(self, container):
        """Remove all sub containers"""
        container_node = container["node"]
        container_node.Remove()
        c4d.EventAdd()
