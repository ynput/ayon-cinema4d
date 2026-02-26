from __future__ import annotations
import inspect

from ayon_core.pipeline import CreatedInstance, AYON_INSTANCE_ID
from ayon_cinema4d.api import lib, plugin

import c4d
import c4d.documents


class RenderlayerCreator(plugin.Cinema4DCreator):
    """Creator which creates an instance per renderlayer in the workfile.

    Create and manages render product instancess per Cinema4D Take in workfile.
    This generates a singleton node in the scene which, if it exists, tells the
    Creator to collect Cinema4D Takes as individual instances.
    As such, triggering create doesn't actually create the instance node per
    layer but only the node which tells the Creator it may now collect
    an instance per Take.

    It collects Cinema4D Takes each turning into a render product instance.
    """
    settings_category = "cinema4d"

    identifier = "io.ayon.creators.cinema4d.render"
    label = "Render"
    description = "Create a render product per Cinema4D Take."
    detailed_description = inspect.cleandoc(__doc__)
    product_base_type = "render"
    product_type = product_base_type
    icon = "eye"

    _required_keys = ("creator_identifier", "productName")

    def _is_marked_workfile_as_render_enabled(self, take_data) -> bool:
        """Return whether the detecting of Takes as render instances is
        enabled in the current workfile.

        This will be true if at least one Take in the scene has render instance
        data imprinted onto it.
        """
        for take in lib.iter_objects(take_data.GetMainTake()):
            data = self._read_instance_node(take)
            if all(key in data for key in self._required_keys):
                return True
        return False

    def create(self, product_name, instance_data, pre_create_data):

        # On creating a first renderlayer instance, we tag the scene so that
        # from that moment onwards, we collect all takes as renderlayers.
        # So we put some data somewhere that says, "takes are now collected".
        # self._mark_workfile_as_render_enabled()

        doc: c4d.documents.BaseDocument = c4d.documents.GetActiveDocument()
        take_data = doc.GetTakeData()
        if take_data is None:
            return

        instance_node = None
        variant_name: str = instance_data.get("variant", "Main")
        print(variant_name)
        if not self._is_marked_workfile_as_render_enabled(take_data):
            # If there's already a take with the variant name, we skip creating
            # a new take but instead just mark the existing take
            for take in lib.iter_objects(take_data.GetMainTake()):
                if take.GetName() == variant_name:
                    # If there's already a take with the variant name,
                    # we do nothing
                    instance_node = take

        # Create a new take
        if instance_node is None:
            # Add a take so that at least something happens on Create for the
            # user
            root = take_data.GetMainTake()
            instance_node = take_data.AddTake(variant_name, root, None)
            c4d.EventAdd()

        # Enforce forward compatibility to avoid the instance to default
        # to the legacy `AVALON_INSTANCE_ID`
        instance_data["id"] = AYON_INSTANCE_ID
        # Use the uniqueness of the node in Cinema4D as the instance id
        instance_data["instance_id"] = str(hash(instance_node))
        instance = CreatedInstance(
            product_type=self.product_type,
            product_name=product_name,
            data=instance_data,
            transient_data={
                "instance_node": instance_node,
                "take": instance_node
            },
            creator=self,
        )

        # Store the instance data
        data = instance.data_to_store()
        self.imprint_instance_node(instance_node, data)

        self._add_instance_to_context(instance)

        # Then directly refresh with all existing entries
        self.collect_instances()

    def collect_instances(self):
        doc: c4d.documents.BaseDocument = c4d.documents.GetActiveDocument()
        take_data = doc.GetTakeData()
        if not self._is_marked_workfile_as_render_enabled(take_data):
            return

        # Each Cinema4D Take is considered a renderlayer
        for take in lib.iter_objects(take_data.GetMainTake()):

            data = self._read_instance_node(take)
            if all(key in data for key in self._required_keys):
                data = self.read_take_overrides(take, data)
                instance = CreatedInstance.from_existing(data, creator=self)
            else:
                take_name: str = take.GetName()
                variant = self._sanitize_take_variant_name(take_name)

                # No existing scene instance node for this layer. Note that
                # this instance will not have the `instance_node` data yet
                # until it's been saved/persisted at least once.
                folder_entity = self.create_context.get_current_folder_entity()
                task_entity = self.create_context.get_current_task_entity()
                instance_data = {
                    "folderPath": folder_entity["path"],
                    "task": task_entity["name"],
                    "variant": variant,
                }

                # Allow subclass to override data behavior
                instance_data = self.read_take_overrides(
                    take, instance_data
                )

                instance = CreatedInstance(
                    product_type=self.product_type,
                    # Defined in `read_take_overrides`
                    product_name=instance_data["productName"],
                    data=instance_data,
                    creator=self
                )

            instance.transient_data["instance_node"] = take
            instance.transient_data["take"] = take
            self._add_instance_to_context(instance)

    def read_take_overrides(
            self,
            take: c4d.modules.takesystem.BaseTake,
            instance_data: dict) -> dict:
        """Overridable read logic to read certain data from the take itself.

        Arguments:
            take (c4d.modules.takesystem.BaseTake): The render take.
            instance_data (dict): The instance's data dictionary.

        Returns:
            dict: The instance's data dictionary with overrides.

        """
        # Override some regular "read" logic like active state
        # retrieved from take active state
        instance_data["active"] = take.IsChecked()

        project_name = self.create_context.get_current_project_name()
        folder_entity = self.create_context.get_current_folder_entity()
        task_entity = self.create_context.get_current_task_entity()
        variant = self._sanitize_take_variant_name(take.GetName())

        host_name = self.create_context.host_name

        product_type = instance_data.get("productType")
        if not product_type:
            product_type = self.product_base_type
        # Always keep product name in sync with the take name
        product_name = self.get_product_name(
            project_name,
            folder_entity,
            task_entity,
            variant,
            host_name,
            product_type=product_type,
        )
        instance_data["productName"] = product_name
        instance_data["variant"] = variant

        return instance_data

    def _sanitize_take_variant_name(self, variant: str) -> str:
        # Sanitize take variant name (e.g. remove spaces)
        # because variants and products names are not allowed to have
        # spaces in them.
        variant = variant.replace(" ", "_").replace("-", "_")
        return variant

    def imprint_instance_node_data_overrides(self,
                                             data: dict,
                                             instance):
        """Persist instance overrides in a custom way.

        Using this you can persist data to the scene that needs to be persisted
        in an alternate way than regular instance attributes, e.g. a native
        Cinema4D attribute or alike such as toggling the take active
        state.

        Make sure to `pop` the data you have already persisted if that data
        is also read from native Cinema4D node attribute in the scene in
        `read_instance_node_overrides`. This avoids it still getting written
        into the `UserData` of the instance node as well.

        Arguments:
            data (dict): The data available to be 'persisted'.
            instance (CreatedInstance): The instance operating on.

        Returns:
            dict: The instance's data that should be persisted into the scene
                in the regular manner.

        """
        take: c4d.modules.takesystem.BaseTake = instance.transient_data["take"]
        take.SetChecked(data.pop("active"))
        take.SetName(data.pop("variant"))
        return data

    def update_instances(self, update_list):
        # We only generate the persisting layer data into the scene once
        # we save with the UI on e.g. validate or publish
        for instance, _changes in update_list:
            instance_node = instance.transient_data["take"]

            data = instance.data_to_store()
            # Allow subclass to override imprinted data behavior
            # The returned data may be altered (e.g. some data popped) that
            # custom imprint logic stored elsewhere
            data = self.imprint_instance_node_data_overrides(data,
                                                             instance)
            self.imprint_instance_node(instance_node, data=data)
        c4d.EventAdd()

    def imprint_instance_node(self, node, data):
        self._imprint(node, data)

    def remove_instances(self, instances):
        # Disallow 'deleting the "Main" take because it can't be removed
        for instance in instances:
            take: c4d.modules.takesystem.BaseTake = (
                instance.transient_data.get("take")
            )
            if not take:
                continue

            if take.IsMain():
                # Remove any imprinted instance data, but avoid deleting it
                # because deleting the main take will crash Cinema4D
                existing_user_data = take.GetUserDataContainer()
                instance_data_keys = set(instance.data_to_store().keys())
                for description_id, base_container in existing_user_data:
                    key = base_container[c4d.DESC_NAME]
                    if key in instance_data_keys:
                        take.RemoveUserData(description_id)
            else:
                take.Remove()

            # Remove the collected CreatedInstance to remove from UI directly
            self._remove_instance_from_context(instance)
        c4d.EventAdd()

    def get_pre_create_attr_defs(self):
        return []
