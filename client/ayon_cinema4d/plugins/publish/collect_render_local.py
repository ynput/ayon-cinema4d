import os

import pyblish.api

from ayon_core.pipeline.farm.pyblish_functions import (
    get_product_name_and_group_from_template,
    _get_legacy_product_name_and_group,
)
from ayon_core.pipeline.publish import ColormanagedPyblishPluginMixin
from ayon_cinema4d.api import lib_renderproducts, plugin

MULTIPASS_NAME = "multipass"


class CollectRenderLocal(pyblish.api.InstancePlugin,
                         ColormanagedPyblishPluginMixin):
    """Collect one instance per AOV for local renders and existing frames.

    Product names and representations match the farm publish of the same
    render: the Multi-Layer file is a `multipass` representation of the
    render product and the frames are tagged for review. The frames are
    rendered by `ExtractRenderLocal`.
    """

    label = "Collect Local Render AOVs"
    # After `CollectCinema4DRender`
    order = pyblish.api.CollectorOrder + 0.15
    hosts = ["cinema4d"]
    families = ["render"]

    def process(self, instance):
        if instance.data.get("farm"):
            self.log.debug("Render on farm, skipping local AOV instances.")
            return

        expected_files = dict(
            next(iter(instance.data.get("expectedFiles", [])), {})
        )
        colorspaces = {
            product.productName: product.colorspace
            for product in instance.data["renderProducts"].layer_data.products
        }
        # Published as representation of the render product, not on its own
        multipass_files = None
        if "" in expected_files:
            multipass_files = expected_files.pop(MULTIPASS_NAME, None)
        review = lib_renderproducts.get_render_settings(
            instance.context.data["project_settings"]
        )["review"]

        for aov_name, files in expected_files.items():
            aov_instance = self.create_aov_instance(
                instance, aov_name, files, colorspaces.get(aov_name)
            )
            if not aov_name:
                if review:
                    self.add_review(aov_instance)
                if multipass_files:
                    aov_instance.data["representations"].append(
                        self.create_representation(
                            instance,
                            multipass_files,
                            colorspaces.get(MULTIPASS_NAME),
                            name=MULTIPASS_NAME,
                        )
                    )
            self.log.debug(f"Collected AOV '{aov_name}': {aov_instance}")

        # The AOV instances publish the frames, they may share the product
        # name of the render instance (regular image without AOV name)
        instance.data["integrate"] = False

    def add_review(self, aov_instance):
        """Tag the rendered frames for review."""
        aov_instance.data["representations"][0]["tags"].append("review")
        aov_instance.data["families"].append("review")
        aov_instance.data["review"] = True

    def create_representation(self, instance, files, colorspace, name=None):
        """Return the representation of a rendered sequence."""
        filenames = [os.path.basename(path) for path in files]
        ext = os.path.splitext(filenames[0])[1].lstrip(".")

        representation = {
            "name": name or ext,
            "ext": ext,
            # A single frame must not be published as a sequence
            "files": filenames if len(filenames) > 1 else filenames[0],
            "stagingDir": os.path.dirname(files[0]),
            "frameStart": instance.data["frameStartHandle"],
            "frameEnd": instance.data["frameEndHandle"],
            "fps": instance.data["fps"],
            "tags": [],
        }
        if name:
            # Keeps the published files apart from the rendered frames
            representation["outputName"] = name
        if colorspace:
            self.set_representation_colorspace(
                representation, instance.context, colorspace=colorspace
            )
        return representation

    def create_aov_instance(self, instance, aov_name, files, colorspace):
        context = instance.context
        product_name, product_group = self.get_product_name_and_group(
            instance, aov_name
        )
        representation = self.create_representation(
            instance, files, colorspace
        )
        staging_dir = representation["stagingDir"]

        aov_instance = context.create_instance(product_name)
        aov_instance.data.update({
            key: instance.data[key]
            for key in (
                "folderPath", "task", "variant", "productType",
                "productBaseType", "frameStart", "frameEnd", "handleStart",
                "handleEnd", "frameStartHandle", "frameEndHandle", "fps",
                "resolutionWidth", "resolutionHeight", "pixelAspect",
                "source", "publish_attributes", "version",
                "hasExplicitFrames", "folderEntity", "taskEntity",
            )
            if key in instance.data
        })
        aov_instance.data.update({
            "name": product_name,
            "label": "{} ({})".format(product_name,
                                      instance.data["folderPath"]),
            "productName": product_name,
            "productGroup": product_group,
            "family": plugin.LOCAL_RENDER_FAMILY,
            "families": [plugin.LOCAL_RENDER_FAMILY],
            "aov": aov_name,
            "farm": False,
            "versionTags": list(instance.data.get("versionTags") or []),
            "stagingDir": staging_dir,
            "representations": [representation],
        })
        return aov_instance

    def get_product_name_and_group(self, instance, aov_name):
        """Return the AOV product name and group like the farm publish."""
        context = instance.context
        dynamic_data = {"aov": aov_name} if aov_name else {}
        project_settings = context.data["project_settings"]
        product_base_type = instance.data["productBaseType"]

        use_legacy = (
            project_settings["core"]["tools"]["creator"]
            .get("use_legacy_product_names_for_renders", False)
        )
        if use_legacy:
            return _get_legacy_product_name_and_group(
                product_base_type,
                instance.data["productName"],
                instance.data["task"],
                dynamic_data,
            )

        create_context = context.data["create_context"]
        folder_path = instance.data["folderPath"]
        return get_product_name_and_group_from_template(
            project_name=context.data["projectName"],
            project_entity=context.data["projectEntity"],
            folder_entity=create_context.get_folder_entity(folder_path),
            task_entity=create_context.get_task_entity(
                folder_path, instance.data["task"]
            ),
            host_name=context.data["hostName"],
            product_base_type=product_base_type,
            product_type=instance.data["productType"],
            variant=instance.data["variant"],
            dynamic_data=dynamic_data,
            project_settings=project_settings,
        )
