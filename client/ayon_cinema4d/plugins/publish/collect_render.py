from __future__ import annotations
from typing import Optional, Any
import attr
import pyblish.api

import clique

from ayon_core.pipeline import publish

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


def find_video_post(
    render_data, plugin_id
) -> Optional[c4d.documents.BaseVideoPost]:
    vp = render_data.GetFirstVideoPost()
    while vp is not None:
        if vp.IsInstanceOf(plugin_id):
            return vp
        vp = vp.GetNext()
    return None


def find_add_video_post(
    render_data, vp_plugin_id
) -> c4d.documents.BaseVideoPost:
    vp = find_video_post(render_data, vp_plugin_id)
    # If not exists, create it
    if vp is None:
        vp = c4d.documents.BaseVideoPost(vp_plugin_id)
        if vp is not None:
            render_data.InsertVideoPost(vp)
    return vp


def get_multipasses(
    render_data: c4d.documents.RenderData,
) -> list[c4d.BaseList2D]:
    """Return all multipasses in render data."""
    multipasses = []
    multipass = render_data.GetFirstMultipass()
    while multipass is not None:
        multipasses.append(multipass)
        multipass = multipass.GetNext()
    return multipasses


def resolve_filepath(
    token_path: str,
    doc: Optional[c4d.documents.BaseDocument] = None,
    render_data: Optional[c4d.documents.RenderData] = None,
    render_settings: Optional[c4d.BaseContainer] = None,
    frame: Optional[int] = None,
    take: Optional[c4d.modules.takesystem.BaseTake] = None,
    layer_name: Optional[str] = None,
    layer_type_name: Optional[str] = None,
    layer_type: Optional[int] = None,
) -> str:
    """Resolve a path with tokens to a resolved path.

    See: https://developers.maxon.net/docs/py/2024_4_0a/modules/c4d.modules/tokensystem/index.html  # noqa

    Constructs the `rpData (RenderPathData)` dictionary:
        _doc: BaseDocument     -> $prj
        _rData: RenderData     -> $res, $height, $rs, $renderer
        _rBc: BaseContainer
        _take: BaseTake        -> $take
        _frame: int            -> $frame
        _layerName: str        -> $userpass
        _layerTypeName: str    -> $pass
        _layerType: int
        _isLight: bool
        _lightNumber: int
        _isMaterial: bool
        _nodeName: str
        _checkUnresolved: bool
    """
    if doc is None:
        doc = c4d.documents.GetActiveDocument()
    if render_data is None:
        render_data = doc.GetActiveRenderData()
    if render_settings is None:
        render_settings = render_data.GetData()
    if frame is None:
        frame = doc.GetTime().GetFrame(doc.GetFps())
    if take is None:
        take = doc.GetTakeData().GetCurrentTake()

    rpd = {
        "_doc": doc,
        "_rData": render_data,
        "_rBc": render_settings,
        "_frame": frame,
    }
    optionals = {
        "_take": take,
        "_layerName": layer_name,
        "_layerTypeName": layer_type_name,
        "_layerType": layer_type,
    }
    for key, value in optionals.items():
        if value is not None:
            rpd[key] = value

    return c4d.modules.tokensystem.StringConvertTokens(token_path, rpd)


@attr.s
class AOV:
    """Dataclass for AOVs

    This should hole all the data to be able to define the resolved path.
    """
    item: Any = attr.ib()
    name: str = attr.ib()
    enabled: bool = attr.ib()
    name: str = attr.ib()
    effective_name: str = attr.ib()
    aov_type: int = attr.ib()
    multipass: bool = attr.ib()
    file_enabled: bool = attr.ib()
    filepath: str = attr.ib()
    file_effective_path: str = attr.ib()

    # If not allowed to be multilayer, then this AOV will still be written
    # as separate file when multi-layer file is enabled. For example, Redshift
    # Cryptomattes always write to a separate EXR.
    always_separate_file: bool = attr.ib(default=False)


def iter_redshift_aovs(video_post: c4d.documents.BaseVideoPost):
    aovs = redshift.RendererGetAOVs(video_post)
    for aov in aovs:
        # TODO: Support light-groups in separate files
        # Light group settings
        # REDSHIFT_AOV_LIGHTGROUP_ALL: int = 1025
        # REDSHIFT_AOV_LIGHTGROUP_GLOBALAOV: int = 1024
        # REDSHIFT_AOV_LIGHTGROUP_GLOBALAOV_ALL: int = 1
        # REDSHIFT_AOV_LIGHTGROUP_GLOBALAOV_NONE: int = 0
        # REDSHIFT_AOV_LIGHTGROUP_GLOBALAOV_REMAINDER: int = 2
        # REDSHIFT_AOV_LIGHTGROUP_NAMES: int = 1026

        # Redshift Cryptomatte is always seperate
        aov_type: int = aov.GetParameter(c4d.REDSHIFT_AOV_TYPE)
        always_separate_file = False
        if aov_type == c4d.REDSHIFT_AOV_TYPE_CRYPTOMATTE:
             always_separate_file = True

        yield AOV(
            item=aov,
            name=aov.GetParameter(c4d.REDSHIFT_AOV_NAME),
            effective_name=aov.GetParameter(c4d.REDSHIFT_AOV_EFFECTIVE_NAME),
            aov_type=aov_type,
            enabled=bool(aov.GetParameter(c4d.REDSHIFT_AOV_ENABLED)),
            multipass=bool(aov.GetParameter(c4d.REDSHIFT_AOV_MULTIPASS_ENABLED)),
            file_enabled=bool(aov.GetParameter(c4d.REDSHIFT_AOV_FILE_ENABLED)),
            filepath=aov.GetParameter(c4d.REDSHIFT_AOV_FILE_PATH),
            file_effective_path=aov.GetParameter(c4d.REDSHIFT_AOV_FILE_EFFECTIVE_PATH),
            always_separate_file=always_separate_file
        )


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
                attachTo=False,
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

                renderData=render_data
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

        # layer_name = "unresolved"  # $userpass if multi-layer file
        # layer_type_name = "unresolved"  # $pass if multi-layer file
        # if not is_multilayer_file:
        #     # Include all AOVs or multipasses separately
        #     pass
        # else:
        #     # Include just the main layer and assume everything ends in one
        #     # file, with the exception of e.g. Redshift Cryptomatte
        #     pass


        # Get all frames
        files = []
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
            for aov in iter_redshift_aovs(video_post):
                # TODO: Support AOV light groups
                pass
        resolved_path = resolve_filepath(token_path, doc, render_data)
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

        return products
