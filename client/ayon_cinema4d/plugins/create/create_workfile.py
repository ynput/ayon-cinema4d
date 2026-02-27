from ayon_core.pipeline import CreatedInstance, AutoCreator, AYON_INSTANCE_ID
from ayon_cinema4d.api.plugin import cache_instance_data
from ayon_cinema4d.api import lib, plugin


class CreateWorkfile(AutoCreator):
    """Workfile auto-creator.

    The workfile instance stores its data on the `AYON_CONTAINERS` collection
    as custom attributes, because unlike other instances it doesn't have an
    instance node of its own.

    """
    identifier = "io.ayon.creators.cinema4d.workfile"
    label = "Workfile"
    product_base_type = "workfile"
    product_type = product_base_type
    icon = "fa5.file"
    default_variant = "Main"

    node_name = "AYON_workfile"

    def create(self):
        """Create workfile instances."""
        workfile_instance = next(
            (
                instance for instance in self.create_context.instances
                if instance.creator_identifier == self.identifier
            ),
            None,
        )

        project_entity = self.create_context.get_current_project_entity()
        folder_entity = self.create_context.get_current_folder_entity()
        task_entity = self.create_context.get_current_task_entity()

        project_name = project_entity["name"]
        folder_path = folder_entity["path"]
        task_name = task_entity["name"]
        host_name = self.create_context.host_name

        existing_folder_path = None
        if workfile_instance is not None:
            existing_folder_path = workfile_instance.get("folderPath")

        if not workfile_instance:
            product_name = self.get_product_name(
                project_name=project_name,
                folder_entity=folder_entity,
                task_entity=task_entity,
                variant=self.default_variant,
                host_name=host_name,
                product_type=self.product_base_type,
            )
            data = {
                "folderPath": folder_path,
                "task": task_name,
                "variant": self.default_variant,
            }

            # Enforce forward compatibility to avoid the instance to default
            # to the legacy `AVALON_INSTANCE_ID`
            data["id"] = AYON_INSTANCE_ID
            self.log.info("Auto-creating workfile instance...")
            workfile_instance = CreatedInstance(
                self.product_type, product_name, data, self
            )
            self._add_instance_to_context(workfile_instance)

        elif (
            existing_folder_path != folder_path
            or workfile_instance["task"] != task_name
        ):
            # Update instance context if it's different
            product_name = self.get_product_name(
                project_name=project_name,
                folder_entity=folder_entity,
                task_entity=task_entity,
                variant=self.default_variant,
                host_name=host_name,
                product_type=self.product_base_type,
            )

            workfile_instance["folderPath"] = folder_path
            workfile_instance["task"] = task_name
            workfile_instance["productName"] = product_name

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

            # Add instance to create context
            self._add_instance_to_context(created_instance)

            # Collect only one
            break

    def update_instances(self, update_list):
        for created_inst, _changes in update_list:

            # If it has no node yet, then it's a new workfile instance
            node = created_inst.transient_data.get("instance_node")
            if not node:
                node = plugin.create_selection([], name=self.node_name)
                plugin.parent_to_ayon_null(node)
                created_inst.transient_data["instance_node"] = node

            new_data = created_inst.data_to_store()

            # Do not store instance id since it's the node hash
            new_data.pop("instance_id", None)

            lib.imprint(node, new_data, group="AYON")

    def remove_instances(self, instances):
        for instance in instances:
            node = instance.transient_data["instance_node"]
            node.Remove()

            self._remove_instance_from_context(instance)
