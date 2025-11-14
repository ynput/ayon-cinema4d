from __future__ import annotations
import attr
import os
import pyblish.api
from typing import Optional

import clique

from ayon_core.pipeline import publish
from ayon_cinema4d.api import lib, lib_renderproducts

import c4d
import c4d.documents
import redshift


@attr.s
class Cinema4DRenderInstance(publish.RenderInstance):
    fps: float = attr.ib(default=None)
    projectEntity: dict = attr.ib(factory=dict)
    stagingDir: str = attr.ib(default=None)
    publish_attributes: dict = attr.ib(factory=dict)
    frameStartHandle: int = attr.ib(default=None)
    frameEndHandle: int = attr.ib(default=None)
    renderData: c4d.documents.RenderData = attr.ib(default=None)
    sceneRenderColorspace: Optional[str] = attr.ib(default=None)

    # Required for Submit Publish Job
    renderProducts: lib_renderproducts.ARenderProduct = attr.ib(default=None)
    colorspaceConfig: Optional[str] = attr.ib(default=None)
    colorspaceDisplay: Optional[str] = attr.ib(default=None)
    colorspaceView: Optional[str] = attr.ib(default=None)


class CollectCinema4DRender(
    publish.AbstractCollectRender,
    publish.ColormanagedPyblishPluginMixin
):
    """
    Each active render instance represents a `Take` inside Cinema4D. For this
    take we will get its render settings and will compute the applicable
    frame range and expected output files as well.

    Each take in Cinema4D can have its own "Render Settings" overrides.
    As such each take may have its own "Render Data" and "Video Post"
    as a result it can have different frame ranges, renderer, etc.
    and also different output filepath settings.
    See: https://developers.maxon.net/docs/Cinema4DCPPSDK/page_overview_takesystem.html  # noqa
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

        scene_ocio_config = lib_renderproducts.get_scene_ocio_config(doc)
        self.log.debug(f"Scene OCIO Config: '{scene_ocio_config['config']}'")
        self.log.debug(f"Scene OCIO Display: '{scene_ocio_config['display']}'")
        self.log.debug(f"Scene OCIO View: '{scene_ocio_config['view']}'")
        self.log.debug(
            f"Scene OCIO Colorspace: '{scene_ocio_config['colorspace']}'"
        )

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
                colorspaceConfig=scene_ocio_config["config"],
                colorspaceDisplay=scene_ocio_config["display"],
                colorspaceView=scene_ocio_config["view"],
                sceneRenderColorspace=scene_ocio_config["colorspace"],
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

        # Debug log video posts
        video_posts: list[c4d.documents.BaseVideoPost] = lib.get_siblings(
            render_data.GetFirstVideoPost()
        )
        video_posts_names = ", ".join(vp.GetName() for vp in video_posts)
        self.log.debug(f"  Video posts: {video_posts_names}")

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
            token_path = self._abspath(doc, token_path)
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
                    files_resolver
                )
            )

        # Set output dir from the beauty output because it is required for
        # publish metadata to be written out and the publish job submission
        # to succeed
        if products:
            first_product_file: str = next(iter(products.values()))[0]
            render_instance.outputDir = os.path.dirname(first_product_file)
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

        # Assume that for all render products we have the same colorspace
        # so for now we will apply the scene render colorspace to all products
        # This is used by the Submit Publish Job plug-in to set the colorspace
        # for each instance
        for aov_name, files in products.items():
            render_instance.renderProducts.layer_data.products.append(
                lib_renderproducts.RenderProduct(
                    productName=aov_name,
                    colorspace=render_instance.sceneRenderColorspace,
                )
            )

        return [products]

    def _collect_multipass(
        self,
        render_data,
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
            # TODO: Check if Cryptomatte is still forced to be written out
            #   in this scenario as a separate file.
            # Single file
            return {"": files_resolver(multipass_token_path)}

        # Support Redshift AOVs
        renderer: int = render_data[c4d.RDATA_RENDERENGINE]
        if renderer == redshift.VPrsrenderer:
            self.log.debug("Renderer is Redshift.")
            redshift_vp = lib_renderproducts.find_video_post(
                render_data,
                lib_renderproducts.REDSHIFT_RENDER_ENGINE_ID
            )
            if redshift_vp:
                return self._collect_redshift_aovs(
                    redshift_vp,
                    files_resolver_fn=files_resolver,
                    multipass_token_path=multipass_token_path
                )

        return {}

    def _collect_redshift_aovs(
        self,
        redshift_vp: c4d.documents.BaseVideoPost,
        files_resolver_fn,
        multipass_token_path: str
    ) -> dict[str, list[str]]:
        """Collect all Redshift AOVs output filepaths by AOV name."""
        products: dict[str, list[str]] = {}

        # If Global AOV mode is set to disabled, collect no AOV data
        aov_disabled: int = c4d.REDSHIFT_RENDERER_AOV_GLOBAL_MODE_DISABLE
        if redshift_vp[c4d.REDSHIFT_RENDERER_AOV_GLOBAL_MODE] == aov_disabled:
            self.log.debug("Redshift Global AOV mode is disabled.")
            return products

        self.log.debug("Collecting Redshift AOVs...")
        layer_index: int = 0
        for aov in lib_renderproducts.iter_redshift_aovs(redshift_vp):
            self.log.debug(f"  {aov}")
            if not aov.enabled:
                continue

            # AOV has no enabled outputs
            if not aov.multipass_enabled and not aov.direct_enabled:
                continue

            layer_index += 1
            aov_name: str = aov.name or aov.effective_name

            # Get filepath without extension and the frame suffix that
            # Redshift already includes in the effective path
            if aov.direct_enabled:
                # TODO: File effective path does not work with e.g. Light
                #  Groups because it will always return the direct AOV path
                #  from C4D instead of our 'copied' aovs
                filepath = os.path.splitext(aov.file_effective_path)[0]
                filepath = filepath.rstrip("0123456789")
                files = files_resolver_fn(filepath)
            else:
                # Make a copy because we may alter it for AOV suffix
                multipass_token_path_aov = multipass_token_path

                # For whatever reason the Depth AOV comes out as "$userpass"
                # instead of the effective name "Z".
                layer_name: str = aov.name or aov.effective_name
                if not aov.name and aov.effective_name == "Z":
                    layer_name = "$userpass"

                # Add layer name suffix
                add_automated_layer_name: bool = (
                    "$pass" not in multipass_token_path_aov
                    and "$userpass" not in multipass_token_path_aov
                )
                if add_automated_layer_name:
                    filename_suffix = f"_{aov_name.lower()}_{layer_index}"
                    multipass_token_path_aov += filename_suffix

                # Format the filepath based on the render data's token
                # path
                files = files_resolver_fn(
                    multipass_token_path_aov,
                    layer_name=layer_name,
                    layer_type_name=aov.effective_name,
                )

            products[aov_name] = files
        return products

    def _abspath(self, doc, path: str) -> str:
        """Return absolute path from possibly relative path."""
        if os.path.isabs(path):
            return path

        project_folder: str = doc.GetDocumentPath()
        abs_path: str = os.path.normpath(os.path.join(project_folder, path))
        self.log.debug(
            f"Resolved relative path '{path}' to absolute path '{abs_path}'"
        )
        return abs_path
