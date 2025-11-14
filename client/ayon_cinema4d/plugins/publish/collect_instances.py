import pyblish.api
from ayon_cinema4d.api import lib


class CollectInstances(pyblish.api.InstancePlugin):
    label = "Collect Instances"
    order = pyblish.api.CollectorOrder - 0.4
    hosts = ["cinema4d"]

    def process(self, instance):

        if instance.data.get("productType") == "render":
            return

        self.log.debug(f"Collecting members for {instance}")

        # Add the creator attributes to instance.data
        self.creator_attributes_to_instance_data(instance)

        # Collect members from the instance node
        instance_node = instance.data["transientData"]["instance_node"]
        members = list(lib.get_objects_from_container(instance_node))

        members_hierarchy = set(members)
        if instance.data.get("includeParentHierarchy", True):
            parents = self.get_all_parents(members)
            members_hierarchy.update(parents)

        # Store members hierarchy
        instance[:] = list(members_hierarchy)

        # Store the exact members of the object set
        instance.data["setMembers"] = members

        # Define nice label
        name = instance_node.GetName()  # use short name
        label = "{0} ({1})".format(name, instance.data["folderPath"])

        # Set frame start handle and frame end handle if frame ranges are
        # available
        if "frameStart" in instance.data and "frameEnd" in instance.data:
            # Enforce existence if handles
            instance.data.setdefault("handleStart", 0)
            instance.data.setdefault("handleEnd", 0)

            # Compute frame start handle and end start handle
            frame_start_handle = (
                instance.data["frameStart"] - instance.data["handleStart"]
            )
            frame_end_handle = (
                instance.data["frameEnd"] - instance.data["handleEnd"]
            )
            instance.data["frameStartHandle"] = frame_start_handle
            instance.data["frameEndHandle"] = frame_end_handle

            # Include frame range in label
            label += "  [{0}-{1}]".format(int(frame_start_handle),
                                          int(frame_end_handle))

        instance.data["label"] = label

    def get_all_parents(self, nodes):
        """Get all parents by using string operations (optimization)

        Args:
            nodes (list): the nodes which are found in the objectSet

        Returns:
            list
        """

        parents = []
        for node in nodes:
            parent = node.GetUp()
            while parent:
                parents.append(parent)
                parent = parent.GetUp()

        return parents

    def creator_attributes_to_instance_data(self, instance):
        creator_attributes = instance.data.get("creator_attributes", {})
        if not creator_attributes:
            return

        for key, value in creator_attributes.items():
            if key in instance.data:
                continue

            instance.data[key] = value
