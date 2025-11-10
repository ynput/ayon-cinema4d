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
        name_format: int = render_data[c4d.RDATA_NAMEFORMAT]

        def files_resolver(
            token_path: str,
            layer_name: str = "$userpass",
            layer_type_name: str = "$pass",
            file_format: int = render_data[c4d.RDATA_MULTIPASS_SAVEFORMAT],
        ) -> list[str]:
            """Return filepaths for all frames with given token path and
            layer names."""
            files: list[str] = []
            for frame in range(
                render_instance.frameStartHandle,
                render_instance.frameEndHandle + 1,
            ):
                resolved_path = lib_renderproducts.resolve_filepath(
                    token_path,
                    doc=doc,
                    render_data=render_data,
                    layer_name=layer_name,
                    layer_type_name=layer_type_name,
                    take=take,
                    frame=frame,
                )
                resolved_path = lib_renderproducts.apply_name_format(
                    resolved_path,
                    name_format=name_format,
                    file_format=file_format,
                    frame=frame
                )
                files.append(resolved_path)
            return files

        # Get take render data AOVs
        video_posts_names = ", ".join(vp.GetName() for vp in video_posts)
        self.log.debug(f"  Video posts: {video_posts_names}")

        products: dict[str, list[str]] = {}

        # Regular image
        save_image: bool = render_data[c4d.RDATA_SAVEIMAGE]
        if save_image:
            token_path: str = render_data[c4d.RDATA_PATH]
            products[""] = files_resolver(
                token_path,
                file_format=render_data[c4d.RDATA_FORMAT]
            )

        # Multi-Pass image
        save_multipass_image: bool = render_data[c4d.RDATA_MULTIPASS_SAVEIMAGE]
        if save_multipass_image:
            products.update(
                self._collect_multipass(
                    render_data,
                    video_posts,
                    files_resolver
                )
            )

        # Set output dir from the beauty output because it is required for
        # publish metadata to be written out and the publish job submission
        # to succeed
        if products:
            render_instance.outputDir = os.path.dirname(next(iter(products.values()))[0])
            self.log.debug(
                f"Collected output directory: {render_instance.outputDir}"
            )
        else:
            render_instance.outputDir = None
            self.log.warning("No render outputs collected; outputDir set to None.")

        # Debug log all collected sequences
        for aov_name, aov_files in products.items():
            if aov_name == "":
                aov_name = "<Beauty>"

            collections, remainder = clique.assemble(aov_files)
            file_labels = remainder + list(
                str(collection) for collection in collections
            )
            self.log.debug(f"  {aov_name} files: {', '.join(file_labels)}")

        return [products]

    def _collect_multipass(
        self,
        render_data,
        video_posts,
        files_resolver
    ) -> dict[str, list[str]]:

        multipass_token_path: str = render_data[c4d.RDATA_MULTIPASS_FILENAME]
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

        if multipass_enabled and multilayer_file:
            # Single file
            return {"": files_resolver(multipass_token_path)}

        # File per AOV
        renderer: int = render_data[c4d.RDATA_RENDERENGINE]
        if renderer == redshift.VPrsrenderer:
            # Support Redshift AOVs
            self.log.debug("Renderer is Redshift.")
            return self._collect_redshift_aovs(
                video_posts,
                files_resolver_fn=files_resolver,
                multipass_token_path=multipass_token_path
            )

        return {}

    def _collect_redshift_aovs(
        self,
        video_posts,
        files_resolver_fn,
        multipass_token_path: str
    ) -> dict[str, list[str]]:
        """Collect all Redshift AOVs"""
        products: dict[str, list[str]] = {}

        # Get Redshift Video Post
        redshift_vp = next((
            vp for vp in video_posts if vp.GetTypeName() == "Redshift"
        ), None)
        if not redshift_vp:
            return products

        # If Global AOV mode is set to disabled, collect no AOV data
        AOV_DISABLED = c4d.REDSHIFT_RENDERER_AOV_GLOBAL_MODE_DISABLE
        if redshift_vp[c4d.REDSHIFT_RENDERER_AOV_GLOBAL_MODE] == AOV_DISABLED:
            self.log.debug("Redshift Global AOV mode is disabled.")
            return products

        for aov in lib_renderproducts.iter_redshift_aovs(redshift_vp):
            # TODO: Support AOV light groups
            self.log.debug(f"Found Redshift AOV: {aov}")
            if not aov.enabled:
                continue

            # We only collect AOVs that are saved into separate files
            is_separate_file: bool = aov.always_separate_file or aov.multipass
            if not is_separate_file:
                continue

            # Get filepath without extension and the zero frame suffix that
            # Redshift resolves as the frame number
            if aov.file_effective_path:
                filepath = os.path.splitext(aov.file_effective_path)[0]
                filepath = filepath.rstrip("0")
                files = files_resolver_fn(filepath)
            else:
                # Format the filepath based on the render data's token
                # path
                # For whatever reason the Depth AOV comes out of "$userpass"
                # instead of the effective name "Z".
                layer_name: str = aov.name or aov.effective_name
                if not aov.name and aov.effective_name == "Z":
                    layer_name = "$userpass"

                files = files_resolver_fn(
                    multipass_token_path,
                    layer_name=layer_name,
                    layer_type_name=aov.effective_name,
                )

            aov_name: str = aov.name or aov.effective_name
            products[aov_name] = files
        return products