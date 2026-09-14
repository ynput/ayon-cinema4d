import json
import os

import pyblish.api

from ayon_core.pipeline.farm.pyblish_functions import create_metadata_path
from ayon_cinema4d.api import lib_renderproducts

MULTIPASS_NAME = "multipass"


class SubmitRenderProducts(pyblish.api.InstancePlugin):
    """Merge the extra render outputs into the product and review it.

    The ayon-deadline publish job creates one product per AOV, so the
    Multi-Layer file and the passes Redshift writes separately (Cryptomatte)
    would become `<product>_multipass` / `<product>_cryptomatte` products.
    `CollectCinema4DRender` lists them in `mergedAovs`, their sequences are
    moved into the render product as representations instead. The rendered
    frames are tagged for review, which makes AYON create a movie from them.
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
        merged = instance.data.get("mergedAovs") or [MULTIPASS_NAME]
        changed = self.merge_aovs(instances, product, merged) or changed
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

    def merge_aovs(self, instances, product, merged_aovs):
        """Move the AOVs that belong to the render into its product.

        The Multi-Layer file and the passes Redshift writes separately
        (Cryptomatte) are the same render, so they become representations
        instead of `<product>_multipass` / `<product>_cryptomatte` products.
        """
        merged = False
        for other in list(instances):
            aov = other.get("aov")
            if other is product or not aov or aov not in merged_aovs:
                continue

            representations = product.setdefault("representations", [])
            for index, repre in enumerate(other.get("representations") or []):
                name = aov if not index else f"{aov}{index + 1}"
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
