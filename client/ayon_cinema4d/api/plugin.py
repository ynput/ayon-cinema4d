import c4d
import typing

from ayon_core.pipeline import (
    Creator,
    CreatedInstance,
    LoaderPlugin,
    AYON_INSTANCE_ID,
    AVALON_INSTANCE_ID
)
from ayon_core.lib import BoolDef

from . import lib

if typing.TYPE_CHECKING:
    from typing import Optional, List


def cache_instance_data(shared_data):
    """Cache instances for Creators shared data.

    Create `blender_cached_instances` key when needed in shared data and
    fill it with all collected instances from the scene under its
    respective creator identifiers.

    If legacy instances are detected in the scene, create
    `blender_cached_legacy_instances` key and fill it with
    all legacy products from this family as a value.  # key or value?

    Args:
        shared_data(Dict[str, Any]): Shared data.

    """
    if shared_data.get('cinema4d_cached_instances') is None:
        cache = {}
        doc = lib.active_document()
        instance_ids = {AYON_INSTANCE_ID, AVALON_INSTANCE_ID}

        for obj in lib.iter_objects(doc.GetFirstObject()):
            if lib.get_object_user_data_by_name(obj, "id") not in instance_ids:
                continue

            creator_id = lib.get_object_user_data_by_name(
                obj, "creator_identifier")
            if not creator_id:
                continue

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


class Cinema4DCreator(Creator):
    default_variants = ['Main']
    settings_category = "cinema4d"

    def create(self, product_name, instance_data, pre_create_data):

        # Register the CreatedInstance
        doc = c4d.documents.GetActiveDocument()
        nodes = list()
        if pre_create_data.get("useSelection"):
            nodes = doc.GetActiveObjects(c4d.GETACTIVEOBJECTFLAGS_CHILDREN)

        instance_node = create_selection(nodes, name=product_name)

        # Enforce forward compatibility to avoid the instance to default
        # to the legacy `AVALON_INSTANCE_ID`
        instance_data["id"] = AYON_INSTANCE_ID
        # Use the uniqueness of the node in Cinema4D as the instance id
        instance_data["instance_id"] = str(hash(instance_node))
        instance = CreatedInstance(
            product_type=self.product_type,
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

            data = lib.read(obj)
            data["instance_id"] = str(hash(obj))

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

    def remove_instances(self, instances):
        for instance in instances:

            # Remove node from the scene
            node = instance.transient_data["instance_node"]
            if node:
                node.Remove()

            # Remove the collected CreatedInstance to remove from UI directly
            self._remove_instance_from_context(instance)

    def _imprint(self, node, data):

        # Do not store instance id since it's the node hash
        data.pop("instance_id", None)

        lib.imprint(node, data, group="AYON")

    def get_pre_create_attr_defs(self):
        return [
            BoolDef("use_selection",
                    label="Use selection",
                    default=True)
        ]


class Cinema4DLoader(LoaderPlugin):
    hosts = ["cinema4d"]
    settings_category = "cinema4d"

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
