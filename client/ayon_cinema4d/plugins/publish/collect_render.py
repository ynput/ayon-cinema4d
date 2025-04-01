from __future__ import annotations
import attr
import pyblish.api

import clique

from ayon_core.pipeline import publish
from ayon_cinema4d.api import lib_renderproducts

import c4d
import c4d.documents
import redshift


@attr.s
class Cinema4DRenderInstance(publish.RenderInstance):
    # extend generic, composition name is needed
    fps = attr.ib(default=None)
    projectEntity = attr.ib(default=None)
    stagingDir = attr.ib(default=None)
    publish_attributes = attr.ib(default={})
    frameStartHandle = attr.ib(default=None)
    frameEndHandle = attr.ib(default=None)
    renderData: c4d.documents.RenderData = attr.ib(default=None)

    # Required for Submit Publish Job
    renderProducts: lib_renderproducts.ARenderProduct = attr.ib(default=None)
    colorspaceConfig: dict = attr.ib(default=None)
    colorspaceDisplay: str = attr.ib(default=None)
    colorspaceView: str = attr.ib(default=None)


class CollectCinema4DRender(
    publish.AbstractCollectRender, publish.ColormanagedPyblishPluginMixin
):
    order = pyblish.api.CollectorOrder + 0.1
    label = "Collect Render"
    hosts = ["cinema4d"]
    families = ["render"]

    def get_instances(self, context):
        current_file = context.data["currentFile"]
        version = context.data.get("version")
        project_entity = context.data["projectEntity"]

        doc: c4d.documents.BaseDocument = context.data["doc"]
        take_data = doc.GetTakeData()
        instances = []
        for inst in context:
            if not inst.data.get("active", True):
                continue

            product_type = inst.data["productType"]
            if product_type != "render":
                continue

            # Get take from instance
            take: c4d.modules.takesystem.BaseTake = (
                inst.data["transientData"]["take"]
            )

            # take_data.SetCurrentTake(take)
            render_data, base_take = take.GetEffectiveRenderData(take_data)

            # Get take name, resolution, frame range
            fps: float = doc.GetFps()
            resolution_width: int = int(render_data[c4d.RDATA_XRES])
            resolution_height: int = int(render_data[c4d.RDATA_YRES])
            pixel_aspect: float = float(render_data[c4d.RDATA_PIXELASPECT])
            frame_start: int = int(render_data[c4d.RDATA_FRAMEFROM].GetFrame(fps))
            frame_end: int = int(render_data[c4d.RDATA_FRAMETO].GetFrame(fps))
            step: int = int(render_data[c4d.RDATA_FRAMESTEP])

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
                attachTo=[],
                setMembers="",
                publish=True,
                name=product_name,
                resolutionWidth=resolution_width,
                resolutionHeight=resolution_height,
                pixelAspect=pixel_aspect,
                review="review" in instance_families,
                frameStart=frame_start,
                frameEnd=frame_end,
                # TODO: define sensible way to set "handles" for a take
                handleStart=0,
                handleEnd=0,
                frameStartHandle=frame_start,
                frameEndHandle=frame_end,
                frameStep=step,
                fps=fps,
                publish_attributes=inst.data.get("publish_attributes", {}),
                # The source instance this render instance replaces
                source_instance=inst,

                renderProducts=lib_renderproducts.ARenderProduct(
                    frame_start=frame_start,
                    frame_end=frame_end
                ),

                # Required for submit publish job
                renderData=render_data,
                colorspaceConfig={},
                # TODO: Collect correct colorspace config
                colorspaceDisplay="sRGB",
                colorspaceView="ACES 1.0 SDR-video",
            )

            instance.farm = True
            instance.projectEntity = project_entity
            instance.deadline = inst.data.get("deadline")
            instances.append(instance)

        return instances

    def get_expected_files(self, render_instance: Cinema4DRenderInstance):
        """Return expected output files from the render"""

        instance: pyblish.api.Instance = render_instance.source_instance
        render_data: c4d.documents.RenderData = render_instance.renderData
        doc = render_data.GetDocument()
        take: c4d.modules.takesystem.BaseTake = (
            instance.data["transientData"]["take"]
        )

        # From the Take and Render Data we find the correct output path,
        # whether it is multipass and what AOVs are enabled for the renderer.
        # Each output file is considered to be a "Render Product" similar to
        # USD terminology.

        # Debug log what take we're processing, etc.
        self.log.debug(f"Take: {take.GetName()}")
        self.log.debug(f"  Render Settings: {render_data.GetName()}")
        self.log.debug(
            "  Frame range: "
            f"{render_instance.frameStartHandle}-"
            f"{render_instance.frameEndHandle}x"
            f"{render_instance.frameStep}"
        )
        self.log.debug(
            f"  Resolution:  "
            f"{render_instance.resolutionWidth}x"
            f"{render_instance.resolutionHeight}"
        )

        # Main multi-pass output
        token_path: str = render_data[c4d.RDATA_MULTIPASS_FILENAME]

        # If Multi-Layer File is enabled then the renderer will write into
        # a single file for all AOVs, except in some cases a renderer may write
        # into a separate file certain AOVs, like a Cryptomatte.
        # '$pass' becomes `unresolved` if multi-layer file is enabled but the
        # token is present in the output path.
        is_multilayer_file = bool(render_data[c4d.RDATA_MULTIPASS_ENABLE])

        layer_name = "unresolved"       # $userpass if multi-layer file
        layer_type_name = "unresolved"  # $pass if multi-layer file
        # if not is_multilayer_file:
        #     # Include all AOVs or multipasses separately
        #     pass
        # else:
        #     # Include just the main layer and assume everything ends in one
        #     # file, with the exception of e.g. Redshift Cryptomatte
        #     pass


        # Get all frames
        files: list[str] = []
        for frame in range(
            render_instance.frameStartHandle,
            render_instance.frameEndHandle + 1,
        ):
            # TODO: Implement how get the correct output render path based
            #  on the Cinema4D render settings
            path = f"/path/to/file.{frame:0>4d}.exr"
            files.append(path)

        # Get take render data AOVs
        renderer = render_data[c4d.RDATA_RENDERENGINE]
        if renderer == redshift.VPrsrenderer:
            video_post = render_data.GetFirstVideoPost()
            self.log.info("Renderer is redshift.")
            for aov in lib_renderproducts.iter_redshift_aovs(video_post):
                # TODO: Support AOV light groups
                pass
        resolved_path = lib_renderproducts.resolve_filepath(
            token_path,
            doc,
            render_data,
            layer_name=layer_name,
            layer_type_name=layer_type_name)

        self.log.debug(f"    Raw path: {token_path}")
        self.log.debug(f"    Path: {resolved_path}")

        products = {
            # beauty
            "": files
        }

        # Debug log all collected sequences
        for aov_name, aov_files in products.items():
            if aov_name == "":
                aov_name = "<beauty>"

            collections, remainder = clique.assemble(aov_files)
            file_labels = remainder + list(
                str(collection) for collection in collections
            )
            self.log.debug(f"    {aov_name} files: {file_labels}")

        return [products]
