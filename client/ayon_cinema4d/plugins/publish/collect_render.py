from __future__ import annotations
import attr
import os
import re
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
    # farm, local or local_no_render
    renderTarget: str = attr.ib(default="farm")

    # Required for Submit Publish Job
    renderProducts: lib_renderproducts.ARenderProduct = attr.ib(default=None)
    colorspaceConfig: Optional[str] = attr.ib(default=None)
    colorspaceDisplay: Optional[str] = attr.ib(default=None)
    colorspaceView: Optional[str] = attr.ib(default=None)


class CollectCinema4DRender(
    publish.AbstractCollectRender,
    publish.ColormanagedPyblishPluginMixin
):
    """Collect the render of the current take or a marked take.

    Each render instance renders one take with the take's effective render
    settings (a take may override the render settings of its parent). The
    rendered frame range, frame step and resolution come from those render
    settings, see `ValidateRenderSettings` for the check against the product.
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
            # Source of marked takes, see `CollectMarkedTakes`
            if inst.data.get("publish") is False:
                continue

            product_type = inst.data["productType"]
            product_base_type = inst.data.get("productBaseType")
            if not product_base_type:
                product_base_type = product_type
            if product_base_type != "render":
                continue

            # Marked take or the current take
            take, render_data = lib.get_take_render_data(
                doc, inst.data.get("take")
            )
            inst.data.setdefault("transientData", {})["take"] = take
            attrs = inst.data.get("creator_attributes", {})

            # Frames rendered by the render settings, the product range for
            # custom frames (reported by `ValidateRenderSettings`)
            product_start = int(attrs.get("frameStart", 1001))
            product_end = int(attrs.get("frameEnd", product_start))
            render_range = lib.get_render_frame_range(doc, render_data) or (
                product_start - int(attrs.get("handleStart", 0)),
                product_end + int(attrs.get("handleEnd", 0)),
            )
            render_start, render_end = render_range
            # Product range clamped to the render range, the rest are handles
            frame_start = min(max(render_start, product_start), render_end)
            frame_end = max(min(render_end, product_end), frame_start)

            instance_families = inst.data.get("families", [])
            product_name = inst.data["productName"]
            render_target = attrs.get("render_target", "farm")

            self.collect_render_quality(inst, attrs)
            step = max(int(render_data[c4d.RDATA_FRAMESTEP]), 1)
            if step > 1:
                # Integrate would renumber the frames without gaps otherwise
                inst.data["hasExplicitFrames"] = True

            instance = Cinema4DRenderInstance(
                productType=product_type,
                productBaseType=product_base_type,
                family=product_base_type,
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
                resolutionWidth=int(render_data[c4d.RDATA_XRES]),
                resolutionHeight=int(render_data[c4d.RDATA_YRES]),
                pixelAspect=float(render_data[c4d.RDATA_PIXELASPECT]),
                review="review" in instance_families,
                frameStart=frame_start,
                frameEnd=frame_end,
                handleStart=frame_start - render_start,
                handleEnd=render_end - frame_end,
                frameStartHandle=render_start,
                frameEndHandle=render_end,
                frameStep=step,
                fps=float(attrs.get("fps") or doc.GetFps()),
                publish_attributes=inst.data.get("publish_attributes", {}),
                # The source instance this render instance replaces
                source_instance=inst,

                renderProducts=lib_renderproducts.ARenderProduct(
                    frame_start=render_start,
                    frame_end=render_end
                ),

                # Required for submit publish job
                renderData=render_data,
                colorspaceConfig=scene_ocio_config["config"],
                colorspaceDisplay=scene_ocio_config["display"],
                colorspaceView=scene_ocio_config["view"],
                sceneRenderColorspace=scene_ocio_config["colorspace"],
            )

            instance.farm = render_target == "farm"
            instance.renderTarget = render_target
            instance.projectEntity = project_entity
            instance.deadline = inst.data.get("deadline")
            instances.append(instance)

            self.log.debug(
                f"Take '{take.GetName()}' renders '{render_data.GetName()}'"
                f" {render_start}-{render_end} ({render_target})"
            )

        self._render_instances = instances
        return instances

    def post_collecting_action(self):
        # The base class takes the context frame range and handles when the
        # product range equals the context range with handles. Keep ours.
        for render_instance in self._render_instances:
            render_instance.source_instance.data.update({
                key: getattr(render_instance, key)
                for key in (
                    "frameStart", "frameEnd", "handleStart", "handleEnd",
                    "frameStartHandle", "frameEndHandle",
                )
            })

    def collect_render_quality(self, instance, attrs):
        """Store the render quality and add it as version tag."""
        quality = attrs.get("render_quality")
        if not quality:
            return
        instance.data["renderQuality"] = quality

        tags = list(instance.data.get("versionTags") or [])
        if quality not in tags:
            tags.append(quality)
        instance.data["versionTags"] = tags

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
        first_video_post = render_data.GetFirstVideoPost()
        video_posts: list[c4d.documents.BaseVideoPost] = (
            lib.get_siblings(first_video_post) if first_video_post else []
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
                render_instance.frameStep,
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

        # Multi-Pass image. Passes written into their own file (Cryptomatte)
        # belong to this render, they become representations of its product.
        merged_aovs: list[str] = []
        save_multipass_image: bool = render_data[c4d.RDATA_MULTIPASS_SAVEIMAGE]
        if save_multipass_image:
            multipass, separate = self._collect_multipass(
                render_data, files_resolver
            )
            merged_aovs.extend(separate)
            # Multi-layer file next to the regular image is its own product
            if "" in products and "" in multipass:
                multipass["multipass"] = multipass.pop("")
                merged_aovs.append("multipass")
            products.update(multipass)
        instance.data["mergedAovs"] = merged_aovs

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
            self.log.warning(
                "No render outputs collected; outputDir set to None."
            )

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
    ) -> tuple[dict[str, list[str]], list[str]]:
        """Return the Multi-Pass outputs and the AOVs written separately.

        Returns:
            tuple: The files by AOV name and the AOV names that belong to
                the render product instead of being their own product.
        """
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

        redshift_vp = None
        renderer: int = render_data[c4d.RDATA_RENDERENGINE]
        if renderer == redshift.VPrsrenderer:
            self.log.debug("Renderer is Redshift.")
            redshift_vp = lib_renderproducts.find_video_post(
                render_data,
                lib_renderproducts.REDSHIFT_RENDER_ENGINE_ID
            )

        if multipass_enabled and multilayer_file:
            # Single file, plus the AOVs Redshift can't merge into it
            products = {"": files_resolver(multipass_token_path)}
            separate = {}
            if redshift_vp:
                separate = self._collect_redshift_direct_aovs(
                    redshift_vp, files_resolver
                )
            products.update(separate)
            return products, list(separate)

        if redshift_vp:
            return self._collect_redshift_aovs(
                redshift_vp,
                files_resolver_fn=files_resolver,
                multipass_token_path=multipass_token_path
            ), []

        return {}, []

    def _collect_redshift_direct_aovs(
        self,
        redshift_vp: c4d.documents.BaseVideoPost,
        files_resolver_fn
    ) -> dict[str, list[str]]:
        """Collect the AOVs Redshift writes into their own file.

        Cryptomatte can't be stored in the merged Multi-Layer file, Redshift
        enables its Direct Output and names the file itself, so the effective
        path is the source of truth for any name the artist picked.
        """
        products: dict[str, list[str]] = {}
        for aov in lib_renderproducts.iter_redshift_aovs(redshift_vp):
            if not aov.enabled or not aov.direct_enabled:
                continue

            path = aov.file_effective_path
            if not path:
                self.log.warning(
                    f"AOV '{aov.effective_name}' has Direct Output enabled"
                    " but no effective path, skipping it."
                )
                continue

            name = aov.name or aov.effective_name
            key = self._get_aov_key(name, products)
            products[key] = files_resolver_fn(
                lib_renderproducts.strip_frame_suffix(path)
            )
            self.log.debug(
                f"Collected separate AOV '{key}' from: {path}"
            )
        return products

    @staticmethod
    def _get_aov_key(name: str, products: dict) -> str:
        """Return a unique representation name for an AOV."""
        key = re.sub(r"[^a-zA-Z0-9]", "", name).lower() or "aov"
        if key not in products:
            return key
        index = 2
        while f"{key}{index}" in products:
            index += 1
        return f"{key}{index}"

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
                files = files_resolver_fn(
                    lib_renderproducts.strip_frame_suffix(
                        aov.file_effective_path
                    )
                )
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
