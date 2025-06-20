from __future__ import annotations
import inspect
import attr

from ayon_core.pipeline import publish, CreatorError, CreatedInstance
from ayon_cinema4d.api import lib, plugin

import c4d
import c4d.documents
import redshift

import importlib
importlib.reload(lib)
importlib.reload(plugin)


class RenderlayerCreator(plugin.Cinema4DCreator):
    """Creator which creates an instance per renderlayer in the workfile.

    Create and manages renderlayer product per renderLayer in workfile.
    This generates a singleton node in the scene which, if it exists, tells the
    Creator to collect Maya rendersetup renderlayers as individual instances.
    As such, triggering create doesn't actually create the instance node per
    layer but only the node which tells the Creator it may now collect
    an instance per renderlayer.

    It collects Cinema4D Takes and individual renderlayers, each turning
    into a render product instance.

    """
    settings_category = "maya"

    identifier = "io.ayon.creators.cinema4d.render"
    label = "Render"
    description = "Create a render product per Cinema4D Take."
    detailed_description = inspect.cleandoc(__doc__)
    product_type = "render"
    icon = "eye"

    def create(self, product_name, instance_data, pre_create_data):
        pass
        # TODO
        # On creating a first renderlayer instance, we tag the scene so that
        # from that moment onwards, we collect all takes as renderlayers.
        # So we put some data somewhere that says, "takes are now collected".
        # self._mark_workfile_as_render_enabled()

        # Add a take so that at least something happens on Create for the user
        # (unless this is the first one and the variant is Main?)

        # Then directly refresh with all existing entries
        # self.collect_instances()

    def collect_instances(self):
        # TODO
        # if not self._is_marked_workfile_as_render_enabled():
        #     return

        required_keys = ("creator_identifier", "productName")

        # Each Cinema4D Take is considered a renderlayer
        # Each take can have its own "Render Settings" overrides
        # As such each take may have its own "Render Data" and "Video Post"
        # as a result it can have different frame ranges, renderer, etc.
        # and also different output filepath settings.
        # TODO: Support different render settings in a Take.
        # See: https://developers.maxon.net/docs/Cinema4DCPPSDK/page_overview_takesystem.html  # noqa
        doc: c4d.documents.BaseDocument = c4d.documents.GetActiveDocument()
        take_data = doc.GetTakeData()
        for take in lib.iter_objects(take_data.GetMainTake()):

            data = self._read_instance_node(take)
            if all(key in data for key in required_keys):
                data = self.read_take_overrides(take, data)
                instance = CreatedInstance.from_existing(data, creator=self)
            else:
                variant: str = take.GetName()

                # Sanitize take variant name (e.g. remove spaces)
                # because variants and products names are not allowed to have
                # spaces in them.
                variant = variant.replace(" ", "_").replace("-", "_")

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
        variant = take.GetName()
        # TODO: Sanitize take variant name (e.g. remove spaces)

        host_name = self.create_context.host_name

        # Always keep product name in sync with the take name
        product_name = self.get_product_name(
            project_name,
            folder_entity,
            task_entity,
            variant,
            host_name,
        )
        instance_data["productName"] = product_name
        instance_data["variant"] = variant

        return instance_data

    def imprint_instance_node_data_overrides(self,
                                             data: dict,
                                             instance):
        """Persist instance overrides in a custom way.

        Using this you can persist data to the scene that needs to be persisted
        in an alternate way than regular instance attributes, e.g. a native
        Cinema4D attribute or alike such as toggling the take active
        state.

        Make sure to `pop` the data you have already persisted if that data
        is also read from native Maya node attribute in the scene in
        `read_instance_node_overrides`. This avoids it still getting written
        into the `UserData` of the instance node as well.

        Arguments:
            data (str): The data available to be 'persisted'.
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
        # TODO: Disallow 'deleting the "Main" take because it can't be removed
        super().remove_instances(instances)

    def get_pre_create_attr_defs(self):
        return []
