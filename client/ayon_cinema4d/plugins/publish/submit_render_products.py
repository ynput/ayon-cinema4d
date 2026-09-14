import json
import os

import pyblish.api

from ayon_core.pipeline.farm.pyblish_functions import create_metadata_path
from ayon_cinema4d.api import lib_renderproducts

MULTIPASS_NAME = "multipass"


class SubmitRenderProducts(pyblish.api.InstancePlugin):
    """Merge the Multi-Layer file into the render product and review it.

    The ayon-deadline publish job creates one product per AOV, so the
    Multi-Layer file would be published as separate `<product>_multipass`
    product. Its sequence is moved into the render product as `multipass`
    representation and the rendered frames are tagged for review, which makes
    AYON create a movie from them.
    """

    label = "Merge Farm Render Products"
    # After `ProcessSubmittedJobOnFarm` wrote the metadata
    order = pyblish.api.IntegratorOrder + 0.22
    hosts = ["cinema4d"]
    families = ["render"]
    targets = ["local"]

    def process(self, instance):
        # Without outputs there is no publish job and no metadata
        if not instance.data.get("farm") or not instance.data.get("outputDir"):
            return

        metadata_path, _ = create_metadata_path(
            instance, instance.context.data["anatomy"]
        )
        if not os.path.exists(metadata_path):
            self.log.warning(
                f"No publish metadata at '{metadata_path}', the render"
                " products are published unchanged."
            )
            return

        with open(metadata_path, "r") as stream:
            metadata = json.load(stream)

        instances = metadata.get("instances") or []
        product = next((i for i in instances if not i.get("aov")), None)
        if product is None:
            self.log.warning("No render product found in the metadata.")
            return

        settings = lib_renderproducts.get_render_settings(
            instance.context.data["project_settings"]
        )
        changed = self.add_review(product) if settings["review"] else False
        changed = self.merge_multipass(instances, product) or changed
        if not changed:
            return

        with open(metadata_path, "w") as stream:
            json.dump(metadata, stream, indent=4, sort_keys=True)

    def add_review(self, product):
        """Tag the rendered frames for review."""
        representations = product.get("representations") or []
        if not representations:
            return False

        tags = representations[0].setdefault("tags", [])
        if "review" in tags:
            return False

        tags.append("review")
        families = product.setdefault("families", [])
        if "review" not in families:
            families.append("review")
        product["review"] = True
        self.log.debug(f"Review enabled for: {product['productName']}")
        return True

    def merge_multipass(self, instances, product):
        """Move the Multi-Layer representations into the render product."""
        merged = False
        for other in list(instances):
            if other is product or other.get("aov") != MULTIPASS_NAME:
                continue

            representations = product.setdefault("representations", [])
            for index, repre in enumerate(other.get("representations") or []):
                name = MULTIPASS_NAME
                if index:
                    name = f"{MULTIPASS_NAME}{index + 1}"
                repre["name"] = name
                repre["outputName"] = name
                # The render product is the reviewed one
                repre["tags"] = [
                    tag for tag in repre.get("tags") or [] if tag != "review"
                ]
                representations.append(repre)

            instances.remove(other)
            merged = True
            self.log.info(
                "Merged '{}' into '{}'.".format(
                    other.get("productName"), product["productName"]
                )
            )
        return merged
