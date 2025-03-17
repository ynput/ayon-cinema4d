from __future__ import annotations
from typing import Any, Optional

import attr

import c4d.documents
import redshift

REDSHIFT_RENDER_ENGINE_ID = 1036219
ARNOLD_RENDER_ENGINE_ID = 1029988

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

    This should hold all the data to be able to define the resolved path.
    """
    item: Any = attr.ib()  # The Redshift AOV object
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

    @property
    def layer_name(self) -> str:
        return self.effective_name

    @property
    def layer_type_name(self) -> str:
        return self.name


def iter_redshift_aovs(video_post: c4d.documents.BaseVideoPost):
    """Using a Video Post from Redshift render yield all Redshift AOVs."""
    aovs = redshift.RendererGetAOVs(video_post)
    for aov in aovs:
        # TODO: Support light-groups in separate FILES
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
            multipass=bool(
                aov.GetParameter(c4d.REDSHIFT_AOV_MULTIPASS_ENABLED)),
            file_enabled=bool(aov.GetParameter(c4d.REDSHIFT_AOV_FILE_ENABLED)),
            filepath=aov.GetParameter(c4d.REDSHIFT_AOV_FILE_PATH),
            file_effective_path=aov.GetParameter(
                c4d.REDSHIFT_AOV_FILE_EFFECTIVE_PATH),
            always_separate_file=always_separate_file
        )


@attr.s
class LayerMetadata(object):
    """Data class for Render Layer metadata."""
    frameStart = attr.ib()
    frameEnd = attr.ib()


@attr.s
class RenderProduct(object):
    """
    Getting Colorspace as Specific Render Product Parameter for submitting
    publish job.
    """
    colorspace = attr.ib()  # colorspace
    view = attr.ib()        # OCIO view transform
    productName = attr.ib(default=None)


class ARenderProduct(object):
    def __init__(self, frame_start, frame_end):
        """Constructor."""
        # Initialize
        self.layer_data = self._get_layer_data(frame_start, frame_end)
        self.layer_data.products = self.get_render_products()

    def _get_layer_data(
        self,
        frame_start: int,
        frame_end: int
    ) -> LayerMetadata:
        return LayerMetadata(
            frameStart=int(frame_start),
            frameEnd=int(frame_end),
        )

    def get_render_products(self):
        """To be implemented by renderer class.
        This should return a list of RenderProducts.
        Returns:
            list: List of RenderProduct
        """
        return [
            RenderProduct(
                colorspace="sRGB",
                view="ACES 1.0",
                productName=""
            )
        ]