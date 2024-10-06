import attr
import pyblish.api

from ayon_core.pipeline import publish
from ayon_core.pipeline.publish import RenderInstance


@attr.s
class Cinema4DRenderInstance(RenderInstance):
    # extend generic, composition name is needed
    fps = attr.ib(default=None)
    projectEntity = attr.ib(default=None)
    stagingDir = attr.ib(default=None)
    app_version = attr.ib(default=None)
    tool = attr.ib(default=None)
    workfileComp = attr.ib(default=None)
    publish_attributes = attr.ib(default={})
    frameStartHandle = attr.ib(default=None)
    frameEndHandle = attr.ib(default=None)


class CollectCinema4DRender(
    publish.AbstractCollectRender,
    publish.ColormanagedPyblishPluginMixin
):

    order = pyblish.api.CollectorOrder + 0.09
    label = "Collect Render"
    hosts = ["cinema4d"]
    families = ["render"]

    def get_instances(self, context):

        app_version = None
        resolution_width: int = 1920
        resolution_height: int = 1080
        pixel_aspect: float = 1.0
        fps: float = 25.0  # get scene fps
        current_file = context.data["currentFile"]
        version = context.data.get("version")
        project_entity = context.data["projectEntity"]

        instances = []
        for inst in context:
            if not inst.data.get("active", True):
                continue

            product_type = inst.data["productType"]
            if product_type != "render":
                continue

            instance_families = inst.data.get("families", [])
            product_name = inst.data["productName"]
            instance = Cinema4DRenderInstance(
                productType=product_type,
                family=product_type,
                families=instance_families,
                version=version,
                time="",
                source=current_file,
                label=inst.data["label"],
                productName=product_name,
                folderPath=inst.data["folderPath"],
                task=inst.data["task"],
                attachTo=False,
                setMembers='',
                publish=True,
                name=product_name,
                resolutionWidth=resolution_width,
                resolutionHeight=resolution_height,
                pixelAspect=pixel_aspect,
                review="review" in instance_families,
                frameStart=inst.data["frameStart"],
                frameEnd=inst.data["frameEnd"],
                handleStart=inst.data["handleStart"],
                handleEnd=inst.data["handleEnd"],
                frameStartHandle=inst.data["frameStartHandle"],
                frameEndHandle=inst.data["frameEndHandle"],
                frameStep=1,
                fps=fps,
                app_version=app_version,
                publish_attributes=inst.data.get("publish_attributes", {}),

                # The source instance this render instance replaces
                source_instance=inst
            )

            instance.farm = True
            instance.projectEntity = project_entity
            instance.deadline = inst.data.get("deadline")
            instances.append(instance)

        return instances

    def get_expected_files(self, render_instance: Cinema4DRenderInstance):
        """Return expected output files from the render"""

        # Get all frames
        files = []
        for frame in range(render_instance.frameStartHandle,
                           render_instance.frameEndHandle+1):
            # TODO: Implement how get the correct output render path based
            #  on the Cinema4D render settings
            path = f"/path/to/file.{frame:0>4d}.exr"
            files.append(path)

        # TODO: Implement multiple AOVs instead of only single render product

        return {
            # beauty
            "": files
        }
