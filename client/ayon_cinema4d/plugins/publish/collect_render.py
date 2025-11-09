from __future__ import annotations
import attr
import os
import pyblish.api

import clique

from ayon_core.pipeline import publish
from ayon_cinema4d.api import lib, lib_renderproducts

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
    publish.AbstractCollectRender,
    publish.ColormanagedPyblishPluginMixin
):
    """
    Each active render instance represents a `Take` inside Cinema4D. For this
    take we will get its render settings and will compute the applicable
    frame range and expected output files as well.
    """
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
        instances: list[Cinema4DRenderInstance] = []
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
            render_data, base_take = take.GetEffectiveRenderData(take_data)

            # Get take name, resolution, frame range
            fps: float = doc.GetFps()
            resolution_width: int = int(render_data[c4d.RDATA_XRES])
            resolution_height: int = int(render_data[c4d.RDATA_YRES])
            pixel_aspect: float = float(render_data[c4d.RDATA_PIXELASPECT])
            frame_start: int = int(
                render_data[c4d.RDATA_FRAMEFROM].GetFrame(fps)
            )
            frame_end: int = int(
                render_data[c4d.RDATA_FRAMETO].GetFrame(fps)
            )
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
        # TODO: Support built-in standard, physical and viewport renderers
        # TODO: Relative paths may need to be made absolute because otherwise
        #  those paths will become relative to the PUBLISHED scenefile instead
        #  of the WORKFILE?
        # TODO: Separate into clearer isolated methods
        #  self._collect_regular_image()
        #  self._collect_multipass_image()
        #  self._collect_video_posts(video_posts)

        instance: pyblish.api.Instance = render_instance.source_instance
        render_data: c4d.documents.RenderData = render_instance.renderData
        doc = render_data.GetDocument()

        # From the Take and Render Data we find the correct output path,
        # whether it is multipass and what AOVs are enabled for the renderer.
        # Each output file is considered to be a "Render Product" similar to
        # USD terminology.
        take: c4d.modules.takesystem.BaseTake = (
            instance.data["transientData"]["take"]
        )
        renderer: int = render_data[c4d.RDATA_RENDERENGINE]
        video_posts: list[c4d.documents.BaseVideoPost] = lib.get_siblings(
            render_data.GetFirstVideoPost()
        )

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

        # Save Regular image
        save_image: bool = render_data[c4d.RDATA_SAVEIMAGE]
        if save_image:
            # token_path: str = render_data[c4d.RDATA_PATH]
            self.log.warning(
                "Saving regular image is enabled. "
                "Currently the Collect Render implementation only supports "
                "Multi-Pass Image. Please disable regular image saving."
            )

        # Save Multi-Pass image
        save_multipass_image: bool = render_data[c4d.RDATA_MULTIPASS_SAVEIMAGE]
        multipass_token_path: str = render_data[c4d.RDATA_MULTIPASS_FILENAME]
        multipass_token_path = self._ensure_path_extension(
            multipass_token_path,
            filter_format=render_data[c4d.RDATA_MULTIPASS_SAVEFORMAT]
        )
        if not save_multipass_image:
            self.log.warning(
                "Saving Multi-Pass Image is disabled. It is currently the "
                "only saving that Collect Render currently supports. "
                "Please enable it. "
            )
            return []

        self.log.debug(
            f"Collected Multi-Pass Filepath: {multipass_token_path}"
        )

        # If Multi-Layer File is enabled then the renderer will write into
        # a single file for all AOVs, except in some cases a renderer may write
        # into a separate file certain AOVs, like a Cryptomatte.
        # '$pass' becomes `unresolved` if multi-layer file is enabled but the
        # token is present in the output path.
        multipass_enabled: bool = bool(render_data[c4d.RDATA_MULTIPASS_ENABLE])
        multilayer_file: bool = render_data[c4d.RDATA_MULTIPASS_SAVEONEFILE]

        layer_name = "unresolved"       # $userpass if multi-layer file
        layer_type_name = "unresolved"  # $pass if multi-layer file
        # if not multipass_enabled:
        #     # Include all AOVs or multipasses separately
        #     pass
        # else:
        #     # Include just the main layer and assume everything ends in one
        #     # file, with exception of e.g. Redshift Cryptomatte pass

        # Get all frames
        files: list[str] = []
        for frame in range(
            render_instance.frameStartHandle,
            render_instance.frameEndHandle + 1,
        ):
            resolved_path = lib_renderproducts.resolve_filepath(
                multipass_token_path,
                doc=doc,
                render_data=render_data,
                layer_name=layer_name,
                layer_type_name=layer_type_name,
                take=take,
                frame=frame
            )
            files.append(resolved_path)

        # Get take render data AOVs
        video_posts_names = ", ".join(vp.GetName() for vp in video_posts)
        self.log.debug(f"  Video posts: {video_posts_names}")

        # Support Redshift
        if renderer == redshift.VPrsrenderer:
            self.log.debug("Renderer is Redshift.")
            self._collect_redshift_aovs(render_instance, video_posts)

        # Set output dir because it is required for publish metadata to be
        # written out and the publish job submission to succeed.
        self.log.debug(
            f"Collected output directory: {render_instance.outputDir}"
        )
        render_instance.outputDir = os.path.dirname(files[0])

        # Products by AOV
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

    def _collect_redshift_aovs(self, render_data, video_posts):
        """Collect all Redshift AOVs"""
        # Get Redshift Video Post
        redshift_vp = next((
            vp for vp in video_posts if vp.GetTypeName() == "Redshift"
        ), None)
        if not redshift_vp:
            return

        # If Global AOV mode is set to disabled, collect no AOV data
        AOV_DISABLED = c4d.REDSHIFT_RENDERER_AOV_GLOBAL_MODE_DISABLE
        if redshift_vp[c4d.REDSHIFT_RENDERER_AOV_GLOBAL_MODE] == AOV_DISABLED:
            self.log.debug("Redshift Global AOV mode is disabled.")
            return

        for aov in lib_renderproducts.iter_redshift_aovs(redshift_vp):
            # TODO: Support AOV light groups
            # TODO: Actually return data
            self.log.info(aov)
            pass

    def _ensure_path_extension(self, path: str, filter_format: int) -> str:
        """Add file format extension to the filepath.

        C4D always appends the file format extension to the end of the filepath
        stripping off any existing extension from the filepath field.
        As such we must mimic this behavior.
        """
        path = os.path.splitext(path)[0]
        extension: str = {
            c4d.FILTER_AVI: ".avi",
            c4d.FILTER_B3D: ".b3d",
            c4d.FILTER_B3DNET: ".b3d",
            c4d.FILTER_BMP: ".bmp",
            c4d.FILTER_DDS: ".dds",
            c4d.FILTER_DPX: ".dpx",
            c4d.FILTER_EXR: ".exr",
            c4d.FILTER_HDR: ".hdr",
            c4d.FILTER_IES: ".ies",
            c4d.FILTER_IFF: ".iff",
            c4d.FILTER_JPG: ".jpg",
            c4d.FILTER_PICT: ".pict",
            c4d.FILTER_PNG: ".png",
            c4d.FILTER_PSB: ".psb",
            c4d.FILTER_PSD: ".psd",
            c4d.FILTER_RLA: ".rla",
            c4d.FILTER_RPF: ".rpf",
            c4d.FILTER_TGA: ".tga",
            c4d.FILTER_TIF: ".tif",
            c4d.FILTER_TIF_B3D: ".tif",
        }[filter_format]
        return f"{path}{extension}"
