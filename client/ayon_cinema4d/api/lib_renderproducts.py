from __future__ import annotations
from typing import Any, Optional, Generator
import logging
import os
import copy

import attr

import c4d.documents
import redshift

from . import lib

log = logging.getLogger(__name__)

REDSHIFT_RENDER_ENGINE_ID = 1036219
# ARNOLD_RENDER_ENGINE_ID = 1029988


# See: https://developers.maxon.net/docs/py/2024_2_0/modules/c4d.documents/RenderData/index.html
def find_video_post(
        render_data: c4d.documents.RenderData, plugin_id: int
) -> Optional[c4d.documents.BaseVideoPost]:
    """Find first video post with plugin_id in render data."""
    vp = render_data.GetFirstVideoPost()
    while vp is not None:
        if vp.IsInstanceOf(plugin_id):
            return vp
        vp = vp.GetNext()
    return None


def find_add_video_post(
        render_data: c4d.documents.RenderData, vp_plugin_id: int
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
        render_settings = render_data.GetDataInstance()
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

    # When passing the token itself as the value for a token, e.g. $pass=$pass
    # it may hang Cinema4D. So, we swap those out to placeholders to replace
    # after resolving.
    placeholders = {}
    for key, value in rpd.items():
        if isinstance(value, str) and "$" in value:
            placeholder = f"____{key.upper()}__PLACEHOLDER____"
            placeholders[value] = placeholder
            rpd[key] = placeholder

    resolved = c4d.modules.tokensystem.StringConvertTokens(token_path, rpd)
    for value, placeholder in placeholders.items():
        resolved = resolved.replace(placeholder, value)
    return resolved


def apply_name_format(
    path: str,
    name_format: int,
    file_format: int,
    frame: int = 0
) -> str:
    """Apply the C4D render data name format to the given filepath.

    Reference:
        RDATA_NAMEFORMAT_0 = Name0000.TIF
        RDATA_NAMEFORMAT_1 = Name0000
        RDATA_NAMEFORMAT_2 = Name.0000
        RDATA_NAMEFORMAT_3 = Name000.TIF
        RDATA_NAMEFORMAT_4 = Name000
        RDATA_NAMEFORMAT_5 = Name.000
        RDATA_NAMEFORMAT_6 = Name.0000.TIF

    Args:
        path:
        name_format:
        file_format:
        frame:

    Returns:

    """
    head, _ = os.path.splitext(path)
    try:
        padding: int = {
            c4d.RDATA_NAMEFORMAT_0: 4,
            c4d.RDATA_NAMEFORMAT_1: 4,
            c4d.RDATA_NAMEFORMAT_2: 4,
            c4d.RDATA_NAMEFORMAT_3: 3,
            c4d.RDATA_NAMEFORMAT_4: 3,
            c4d.RDATA_NAMEFORMAT_5: 3,
            c4d.RDATA_NAMEFORMAT_6: 4,
        }[name_format]
    except KeyError as exc:
        raise ValueError(f"Unsupported name format: {name_format}") from exc
    frame_str = str(frame).zfill(padding)

    # Prefix frame number with a dot for specific name formats
    if name_format in {
        c4d.RDATA_NAMEFORMAT_2,
        c4d.RDATA_NAMEFORMAT_5,
        c4d.RDATA_NAMEFORMAT_6,
    }:
        frame_str = "." + frame_str
    # Whenever the frame number directly follows the name and the name ends
    # with a digit then C4D adds an underscore before the frame number.
    elif head and head[-1].isdigit():
        frame_str = "_" + frame_str

    # Add file format extension if name format includes it
    if name_format in {
        c4d.RDATA_NAMEFORMAT_0,
        c4d.RDATA_NAMEFORMAT_3,
        c4d.RDATA_NAMEFORMAT_6,
    }:
        extension: str = get_renderdata_file_format_extension(file_format)
    else:
        # No extension
        extension: str = ""

    return f"{head}{frame_str}{extension}"


def get_renderdata_file_format_extension(file_format: int) -> str:
    """Get the file extension for a given render data file format.

    The file format is e.g. render data like:
        - c4d.RDATA_FORMAT
        - c4d.RDATA_MULTIPASS_SAVEFORMAT

    Args:
        file_format: The C4D render data file format constant.

    Returns:
        str: A file extension.
    """
    try:
        return {
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
        }[file_format]
    except KeyError as exc:
        raise ValueError(f"Unsupported file format: {file_format}") from exc


@attr.s
class AOV:
    """Dataclass for AOVs

    This should hold all the data to be able to define the resolved path.
    """
    item: Any = attr.ib()  # The Redshift AOV object
    enabled: bool = attr.ib()
    name: str = attr.ib()
    effective_name: str = attr.ib()
    aov_type: int = attr.ib()
    multipass_enabled: bool = attr.ib()    # Multi-pass Output enabled
    direct_enabled: bool = attr.ib()       # Direct Output enabled
    filepath: str = attr.ib()              # Direct Output path
    file_effective_path: str = attr.ib()   # Effective path for direct output

    # If not allowed to be multilayer, then this AOV will still be written
    # as separate file when multi-layer file is enabled. For example, Redshift
    # Cryptomattes always write to a separate EXR.
    always_separate_file: bool = attr.ib(default=False)

    @property
    def layer_name(self) -> str:
        return self.effective_name

    @property
    def layer_type_name(self) -> str:
        return self.name


def get_redshift_light_groups(doc: c4d.documents.BaseDocument) -> set[str]:
    light_groups: set[str] = set()
    for obj in lib.iter_objects(doc.GetFirstObject()):
        if obj.GetType() != c4d.Orslight:
            continue
        print(obj.GetName())

        light_group: str = obj[c4d.REDSHIFT_LIGHT_LIGHT_GROUP]
        if light_group:
            light_groups.add(light_group)

    return light_groups


def iter_redshift_aovs(video_post: c4d.documents.BaseVideoPost) -> Generator[AOV, None, None]:
    """Using a Video Post from Redshift render yield all Redshift AOVs.

    This may separate light-groups into separate AOVs.
    """
    aovs = redshift.RendererGetAOVs(video_post)
    scene_light_groups = get_redshift_light_groups(video_post.GetDocument())

    for aov in aovs:
        # Redshift Cryptomatte is always separate
        aov_type: int = aov.GetParameter(c4d.REDSHIFT_AOV_TYPE)
        always_separate_file = False
        if aov_type == c4d.REDSHIFT_AOV_TYPE_CRYPTOMATTE:
            always_separate_file = True

        global_aov = AOV(
            item=aov,
            name=aov.GetParameter(c4d.REDSHIFT_AOV_NAME),
            effective_name=aov.GetParameter(c4d.REDSHIFT_AOV_EFFECTIVE_NAME),
            aov_type=aov_type,
            enabled=bool(aov.GetParameter(c4d.REDSHIFT_AOV_ENABLED)),
            multipass_enabled=bool(
                aov.GetParameter(c4d.REDSHIFT_AOV_MULTIPASS_ENABLED)),
            direct_enabled=bool(aov.GetParameter(c4d.REDSHIFT_AOV_FILE_ENABLED)),
            filepath=aov.GetParameter(c4d.REDSHIFT_AOV_FILE_PATH),
            file_effective_path=aov.GetParameter(
                c4d.REDSHIFT_AOV_FILE_EFFECTIVE_PATH),
            always_separate_file=always_separate_file
        )

        if global_aov.effective_name == "Z":
            # Z AOV gets merged into main layer?
            continue

        # The list of returned light group names may contain 'unused' entries
        # that do not exist (anymore?) so we must filter the list against the
        # scene light groups.
        light_groups: list[str] = [
            lg.strip() for lg in
            aov.GetParameter(c4d.REDSHIFT_AOV_LIGHTGROUP_NAMES).split("\n")
        ]
        light_groups = [
            lg for lg in light_groups if lg and lg in scene_light_groups
        ]
        all_light_groups: bool = aov.GetParameter(c4d.REDSHIFT_AOV_LIGHTGROUP_ALL)
        if all_light_groups:
            light_groups = list(scene_light_groups)

        light_group_mode: int = aov.GetParameter(c4d.REDSHIFT_AOV_LIGHTGROUP_GLOBALAOV)  # noqa

        # Global AOV (Main output)
        if not light_groups or light_group_mode == c4d.REDSHIFT_AOV_LIGHTGROUP_GLOBALAOV_ALL:
            yield global_aov

        # Global Remainder AOV
        if light_groups and light_group_mode == c4d.REDSHIFT_AOV_LIGHTGROUP_GLOBALAOV_REMAINDER:
            remainder_aov = copy.copy(global_aov)
            # Only specify name if already set
            if remainder_aov.name:
                remainder_aov.name += "_other"
            remainder_aov.effective_name += "_other"
            yield remainder_aov

        # AOV output per light group
        for light_group in light_groups:
            light_aov = copy.copy(global_aov)
            if light_aov.name:
                light_aov.name += f"_{light_group}"
            light_aov.effective_name += f"_{light_group}"
            yield light_aov


@attr.s
class LayerMetadata(object):
    """Data class for Render Layer metadata."""
    frameStart = attr.ib()
    frameEnd = attr.ib()
    products: list[RenderProduct] = attr.ib(factory=list)


@attr.s
class RenderProduct(object):
    """
    Getting Colorspace as Specific Render Product Parameter for submitting
    publish job.
    """
    productName: str = attr.ib()   # AOV name or "" for Beauty
    colorspace: str = attr.ib()  # Render Colorspace


class ARenderProduct(object):
    def __init__(self, frame_start, frame_end):
        self.layer_data = self._get_layer_data(frame_start, frame_end)

    def _get_layer_data(
        self,
        frame_start: int,
        frame_end: int
    ) -> LayerMetadata:
        return LayerMetadata(
            frameStart=int(frame_start),
            frameEnd=int(frame_end),
        )


def get_default_ocio_resource() -> str:
    """Return default OCIO config path for Cinema4D."""
    resources = c4d.storage.GeGetC4DPath(c4d.C4D_PATH_RESOURCE)
    return os.path.join(resources, "ocio", "config.ocio")


def set_scene_ocio_config(
    doc: c4d.documents.BaseDocument,
    config: Optional[str] = None,
    display: Optional[str] = None,
    view: Optional[str] = None,
    colorspace: Optional[str] = None,
    thumbnails: Optional[str] = None,
) -> None:
    # Set scene OCIO config, display and view
    if config is not None:
        doc[c4d.DOCUMENT_COLOR_MANAGEMENT] = c4d.DOCUMENT_COLOR_MANAGEMENT_OCIO
        doc[c4d.DOCUMENT_OCIO_CONFIG] = config

    if display is not None:
        ocio_displays = doc.GetOcioDisplayColorSpaceNames()
        if display in ocio_displays:
            display_index = ocio_displays.index(display)
            doc[c4d.DOCUMENT_OCIO_DISPLAY_COLORSPACE] = display_index

    if view is not None:
        ocio_views = doc.GetOcioViewTransformNames()
        if view in ocio_views:
            view_index = ocio_views.index(view)
            doc[c4d.DOCUMENT_OCIO_VIEW_TRANSFORM] = view_index

    if thumbnails:
        ocio_views = doc.GetOcioViewTransformNames()
        if thumbnails in ocio_views:
            view_index = ocio_views.index(thumbnails)
            doc[c4d.DOCUMENT_OCIO_VIEW_TRANSFORM_THUMBNAILS] = view_index

    if colorspace is not None:
        ocio_colorspaces = doc.GetOcioRenderingColorSpaceNames()
        if colorspace in ocio_colorspaces:
            colorspace_index = ocio_colorspaces.index(colorspace)
            doc[c4d.DOCUMENT_OCIO_RENDER_COLORSPACE] = colorspace_index


def get_scene_ocio_config(
    doc: c4d.documents.BaseDocument
) -> dict[str, Optional[str]]:

    # Get scene OCIO config, display and view
    config: str = doc.GetOcioConfigPath()

    # If OCIO management is not enabled then C4D renders using legacy (sRGB
    # linear workflow) for which we can't return a valid OCIO output.
    if doc[c4d.DOCUMENT_COLOR_MANAGEMENT] != c4d.DOCUMENT_COLOR_MANAGEMENT_OCIO:
        # When in legacy mode Cinema4D describes it as
        # "Current Render Space: Legacy (sRGB linear workflow)"
        log.debug("Using legacy color management...")
        return {
            "config": config,
            "display": None,
            "view": None,
            "colorspace": None
        }

    display: str = ""
    ocio_displays = doc.GetOcioDisplayColorSpaceNames()
    if ocio_displays:
        display = ocio_displays[doc[c4d.DOCUMENT_OCIO_DISPLAY_COLORSPACE]]

    view: str = ""
    ocio_views = doc.GetOcioViewTransformNames()
    if ocio_views:
        # In some cases if the attribute was not explicitly set then C4D may
        # raise `AttributeError: parameter access failed`. If that happens,
        # we assume it's just the first index.
        try:
            view_index: int = doc[c4d.DOCUMENT_OCIO_VIEW_TRANSFORM]
        except AttributeError:
            view_index = 0

        view = ocio_views[view_index]

    ocio_colorspaces: list[str] = doc.GetOcioRenderingColorSpaceNames()
    colorspace: str = ocio_colorspaces[
        doc[c4d.DOCUMENT_OCIO_RENDER_COLORSPACE]
    ]

    return {
        "config": config,
        "display": display,
        "view": view,
        "colorspace": colorspace
    }
