import json
import logging
import os

import c4d

log = logging.getLogger(__name__)


FBX_EXPORTER_ID = 1026370

# Note: Cinema 4D render settings are strictly typed. Float parameters
# (see RDATA_* docs) must be set with floats, ints with ints. The helper
# `set_parameters` below coerces values to the stored parameter type.
PLAYBLAST_SETTINGS = {
    # Resolution (overridden by the render_playblast arguments)
    "RDATA_XRES": 1920.0,
    "RDATA_YRES": 1080.0,
    "RDATA_LOCKRATIO": False,
    "RDATA_ADAPT_DATARATE": True,
    "RDATA_PIXELRESOLUTION_VIRTUAL": 72.0,
    "RDATA_PIXELRESOLUTIONUNIT": 1,
    "RDATA_RENDERREGION": False,
    "RDATA_PIXELASPECT": 1.0,
    # Frame rate and range are set in `render_playblast`
    "RDATA_FRAMESTEP": 1,
    "RDATA_FIELD": 0,
    "RDATA_GLOBALSAVE": True,
    "RDATA_SAVEIMAGE": True,
    "RDATA_MULTIPASS_ENABLE": False,
    "RDATA_PROJECTFILE": False,
    "RDATA_FORMAT": c4d.FILTER_MOVIE,  # save as movie (mp4)
}

# Hardware preview (viewport render) video post settings
HARDWARE_SETTINGS = {
    "VP_PREVIEWHARDWARE_ENHANCEDOPENGL": False,
    "VP_PREVIEWHARDWARE_ANTIALIASING": 2,
    "VP_PREVIEWHARDWARE_SUPERSAMPLING": c4d.VP_PREVIEWHARDWARE_SUPERSAMPLING_NONE,  # noqa: E501
}

# Display filters excluded from a review render. The suffixes are shared by
# the viewport render effect (`VP_PREVIEWHARDWARE_*`) and the view itself
# (`BASEDRAW_*`), both of which are set on a throwaway copy of the document.
HIDDEN_DISPLAY_FILTERS = [
    "DISPLAYFILTER_GRID",  # Workplane
    "DISPLAYFILTER_BASEGRID",  # World Grid
    "DISPLAYFILTER_WORLDAXIS",  # World Axis
    "DISPLAYFILTER_HORIZON",  # Horizon
    "DISPLAYFILTER_HUD",  # HUD
    "DISPLAYFILTER_CAMERA",  # Camera
    "DISPLAYFILTER_FIELD",  # Field
    "DISPLAYFILTER_DEFORMER",  # Deformer
    "DISPLAYFILTER_LIGHT",  # Light
    "DISPLAYFILTER_JOINT",  # Joint
    "DISPLAYFILTER_GUIDELINES",  # Guides
    "DISPLAYFILTER_OBJECTHANDLES",  # Axis
    "DISPLAYFILTER_MULTIAXIS",  # Multi-Select Axes
    "DISPLAYFILTER_HANDLES",  # Handles
    "DISPLAYFILTER_SDS",  # SDS Mesh
    "DATA_SHOWPATH",  # Animation Path
    "DISPLAYFILTER_ONION",  # Ghosting
]

SPLINE_DISPLAY_FILTER = "DISPLAYFILTER_SPLINE"
NULL_DISPLAY_FILTER = "DISPLAYFILTER_NULL"


class RenderError(RuntimeError):
    pass


def get_plugin_imexport_options(plugin, label=None):
    if label is None:
        label = str(plugin)

    plugin_obj = c4d.plugins.FindPlugin(
        plugin,
        c4d.PLUGINTYPE_SCENESAVER,
    )
    if plugin_obj is None:
        raise Exception(f"Could not find plug-in: {label}.")

    options = {}
    # Send MSG_RETRIEVEPRIVATEDATA to Alembic export plugin
    if plugin_obj.Message(c4d.MSG_RETRIEVEPRIVATEDATA, options):
        if "imexporter" not in options:
            raise Exception(
                f"Could not find options container for the {label} exporter."
            )

    # BaseList2D object stored in "imexporter" key hold the settings
    imexporter_options = options["imexporter"]
    if imexporter_options is None:
        raise Exception(f"Could not find options for the {label} exporter.")

    return imexporter_options


def extract_alembic(filepath,
                    frame_start=None,
                    frame_end=None,
                    frame_step=1,
                    sub_frames=1,
                    global_matrix=False,
                    selection=True,
                    doc=None,
                    verbose=False,
                    **kwargs):
    """Extract a single Alembic Cache."""
    doc = doc or c4d.documents.GetActiveDocument()

    # Fallback to Cinema4d timeline if no start or end frame provided.
    if frame_start is None:
        frame_start = doc.GetMinTime().GetFrame(doc.GetFps())
    if frame_end is None:
        frame_end = doc.GetMinTime().GetFrame(doc.GetFps())

    # Set export options
    options = get_plugin_imexport_options(c4d.FORMAT_ABCEXPORT,
                                          label="Alembic")

    applied_options = {
        # Animation
        "ABCEXPORT_FRAME_START": frame_start,
        "ABCEXPORT_FRAME_END": frame_end,
        "ABCEXPORT_FRAME_STEP": frame_step,
        "ABCEXPORT_SUBFRAMES": sub_frames,

        # General
        # "ABCEXPORT_SCALE": 1  # "UnitScaleData
        "ABCEXPORT_SELECTION_ONLY": selection,
        "ABCEXPORT_CAMERAS": kwargs.get("cameras", True),
        "ABCEXPORT_SPLINES": kwargs.get("splines", False),
        "ABCEXPORT_HAIR": kwargs.get("hair", False),
        "ABCEXPORT_XREFS": kwargs.get("xrefs", True),
        "ABCEXPORT_GLOBAL_MATRIX": global_matrix,

        # Subdivision surface
        "ABCEXPORT_HYPERNURBS": kwargs.get(
            "subdivisionSurfaces", True
        ),
        "ABCEXPORT_SDS_WEIGHTS": kwargs.get(
            "subdivisionSurfaceWeights", False
        ),
        "ABCEXPORT_PARTICLES": kwargs.get("particles", False),
        "ABCEXPORT_PARTICLE_GEOMETRY": kwargs.get(
            "particleGeometry", False
        ),

        # Optional data
        "ABCEXPORT_VISIBILITY": kwargs.get("visibility", True),
        "ABCEXPORT_UVS": kwargs.get("uvs", True),
        "ABCEXPORT_VERTEX_MAPS": kwargs.get("vertexMaps", False),

        # Vertex normals
        "ABCEXPORT_NORMALS": kwargs.get("normals", False),
        "ABCEXPORT_POLYGONSELECTIONS": kwargs.get("polygonSelections", True),
        "ABCEXPORT_VERTEX_COLORS": kwargs.get("vertexColors", False),
        "ABCEXPORT_POINTS_ONLY": kwargs.get("pointsOnly", False),
        "ABCEXPORT_DISPLAY_COLORS": kwargs.get("displayColors", False),
        "ABCEXPORT_MERGE_CACHE": kwargs.get("mergeCache", False)

        # "ABCEXPORT_GROUP": None,  # ???
        # # Don't export child objects with only selected?
        # "ABCEXPORT_PARENTS_ONLY_MODE": False,
        # "ABCEXPORT_STR_ANIMATION": None,  # ???
        # "ABCEXPORT_STR_GENERAL": None,  # ???
        # "ABCEXPORT_STR_OPTIONS": None,  # ???
    }
    if verbose:
        log.debug(
            "Preparing Alembic export with options: %s",
            json.dumps(applied_options, indent=4),
        )

    for key, value in applied_options.items():
        key_id = getattr(c4d, key)
        # There appears to be a bug where if the value is just set directly
        # that it fails to apply them for the export, e.g. still exporting the
        # whole scene even though `c4d.ABCEXPORT_SELECTION_ONLY` is True.
        # See: https://developers.maxon.net/forum/topic/12767/alembic-export-options-not-working/6  # noqa: E501
        options[key_id] = not value
        options[key_id] = value

    # Ensure output directory exists
    parent_dir = os.path.dirname(filepath)
    os.makedirs(parent_dir, exist_ok=True)

    if c4d.documents.SaveDocument(
        doc,
        filepath,
        c4d.SAVEDOCUMENTFLAGS_DONTADDTORECENTLIST,
        c4d.FORMAT_ABCEXPORT,
    ):
        if verbose:
            log.debug("Extracted Alembic to: %s", filepath)
    else:
        log.error("Extraction of Alembic failed: %s", filepath)

    return filepath


def extract_fbx(filepath, verbose=False, **kwargs):
    """Extract a single fbx file."""

    doc = c4d.documents.GetActiveDocument()
    options = get_plugin_imexport_options(FBX_EXPORTER_ID,
                                                     label="FBX")

    # File format
    options[c4d.FBXEXPORT_FBX_VERSION] = kwargs.get("fbxVersion", 0)
    options[c4d.FBXEXPORT_ASCII] = kwargs.get("fbxAscii", False)

    # General
    options[c4d.FBXEXPORT_SELECTION_ONLY] = kwargs.get("selectionOnly", False)
    options[c4d.FBXEXPORT_CAMERAS] = kwargs.get("cameras", True)
    options[c4d.FBXEXPORT_SPLINES] = kwargs.get("splines", True)
    options[c4d.FBXEXPORT_INSTANCES] = kwargs.get("instances", True)
    options[c4d.FBXEXPORT_GLOBAL_MATRIX] = kwargs.get("globalMatrix", False)
    options[c4d.FBXEXPORT_SDS] = kwargs.get("subdivisionSurfaces", True)
    options[c4d.FBXEXPORT_LIGHTS] = kwargs.get("lights", True)

    # Animation
    options[c4d.FBXEXPORT_TRACKS] = kwargs.get("tracks", False)
    options[c4d.FBXEXPORT_BAKE_ALL_FRAMES] = kwargs.get(
        "bakeAllFrames", False
    )
    options[c4d.FBXEXPORT_PLA_TO_VERTEXCACHE] = kwargs.get(
        "plaToVertexCache", False
    )

    # Geometry
    options[c4d.FBXEXPORT_SAVE_NORMALS] = kwargs.get("normals", False)
    options[c4d.FBXEXPORT_SAVE_VERTEX_MAPS_AS_COLORS] = kwargs.get(
        "vertexMapsAsColors", False
    )
    options[c4d.FBXEXPORT_SAVE_VERTEX_COLORS] = kwargs.get(
        "vertexColors", False
    )
    options[c4d.FBXEXPORT_TRIANGULATE] = kwargs.get("triangulate", False)
    options[c4d.FBXEXPORT_SDS_SUBDIVISION] = kwargs.get(
        "bakedSubdivisionSurfaces", False
    )
    options[c4d.FBXEXPORT_LOD_SUFFIX] = kwargs.get("lodSuffix", False)

    # Additional
    if hasattr(c4d, "FBXEXPORT_TEXTURES"):
        # Cinema4d S22 doesn't have this option anymore
        options[c4d.FBXEXPORT_TEXTURES] = kwargs.get("textures", False)
    if hasattr(c4d, "FBXEXPORT_BAKE_MATERIALS"):
        # Cinema4d S22 now has the ability to bake materials
        options[c4d.FBXEXPORT_BAKE_MATERIALS] = kwargs.get(
            "bakeMaterials", False
        )
    options[c4d.FBXEXPORT_EMBED_TEXTURES] = kwargs.get(
        "embedTextures", False
    )
    options[c4d.FBXEXPORT_FLIP_Z_AXIS] = kwargs.get("flipZAxis", False)
    options[c4d.FBXEXPORT_SUBSTANCES] = kwargs.get("substances", False)
    options[c4d.FBXEXPORT_UP_AXIS] = kwargs.get(
        "upAxis", c4d.FBXEXPORT_UP_AXIS_Y
    )

    # Ensure output directory exists
    parent_dir = os.path.dirname(filepath)
    if not os.path.exists(parent_dir):
        os.makedirs(parent_dir)

    if verbose:
        log.debug(
            "Preparing FBX export with options: %s",
            json.dumps(kwargs, indent=4),
        )

    if c4d.documents.SaveDocument(
        doc,
        filepath,
        c4d.SAVEDOCUMENTFLAGS_DONTADDTORECENTLIST,
        FBX_EXPORTER_ID,
    ):
        if verbose:
            log.debug("Extracted FBX to: %s", filepath)
    else:
        log.error("Extraction of FBX failed: %s", filepath)

    return filepath


def extract_redshiftproxy(
        filepath,
        frame_start=None,
        frame_end=None,
        frame_step=1,
        selection=True,
        export_lights=True,
        export_compress=True,
        export_polygon_connectivity=False,
        doc=None,
        verbose=False):
    """Extract a Redshift Proxy."""

    # Redshift may not be available so we import here
    import redshift  # noqa

    doc = doc or c4d.documents.GetActiveDocument()

    # Fallback to Cinema4d timeline if no start or end frame provided.
    if frame_start is None:
        frame_start = doc.GetMinTime().GetFrame(doc.GetFps())
    if frame_end is None:
        frame_end = doc.GetMinTime().GetFrame(doc.GetFps())

    # Export at default 1cm scale
    scale = c4d.UnitScaleData()
    scale.SetUnitScale(1.0, c4d.DOCUMENT_UNIT_CM)

    # Set export options
    options = get_plugin_imexport_options(redshift.Frsproxyexport,
                                          label="Alembic")

    applied_options = {
        "REDSHIFT_PROXYEXPORT_ANIMATION_FRAME_END": frame_end,
        "REDSHIFT_PROXYEXPORT_ANIMATION_FRAME_START": frame_start,
        "REDSHIFT_PROXYEXPORT_ANIMATION_FRAME_STEP": frame_step,
        "REDSHIFT_PROXYEXPORT_ANIMATION_RANGE": c4d.REDSHIFT_PROXYEXPORT_ANIMATION_RANGE_MANUAL,
        "REDSHIFT_PROXYEXPORT_EXPORT_COMPRESS": export_compress,
        "REDSHIFT_PROXYEXPORT_EXPORT_LIGHTS": export_lights,
        "REDSHIFT_PROXYEXPORT_EXPORT_POLYGON_CONNECTIVITY": export_polygon_connectivity,
        "REDSHIFT_PROXYEXPORT_OBJECTS": (
            c4d.REDSHIFT_PROXYEXPORT_OBJECTS_SELECTION if selection
            else c4d.REDSHIFT_PROXYEXPORT_OBJECTS_ALL
        ),

        # Proxy Origin:
        #   - World Origin: REDSHIFT_PROXYEXPORT_ORIGIN_WORLD
        #   - Object Bounds: REDSHIFT_PROXYEXPORT_ORIGIN_OBJECTS
        "REDSHIFT_PROXYEXPORT_ORIGIN": c4d.REDSHIFT_PROXYEXPORT_ORIGIN_WORLD,

        # Include default beauty AOV
        # Keep the default beauty config in the proxy. Used primarily when
        # exporting entire scenes for rendering with the redshiftCmdLine tool
        "REDSHIFT_PROXYEXPORT_AOV_DEFAULT_BEAUTY": False,

        "REDSHIFT_PROXYEXPORT_AUTOPROXY_CREATE": False,
        # "REDSHIFT_PROXYEXPORT_AUTOPROXY_PREFIX": "RS Proxy",

        # Do not remove the exported objects
        "REDSHIFT_PROXYEXPORT_REMOVE_OBJECTS": False,

        "REDSHIFT_PROXYEXPORT_SCALE": scale,

        # TODO: Set more parameters
        # "REDSHIFT_PROXYEXPORT_GROUP": ...,
        # "REDSHIFT_PROXYEXPORT_GROUP_ANIMATION": ...,
        # "REDSHIFT_PROXYEXPORT_GROUP_AOV": ...,
        # "REDSHIFT_PROXYEXPORT_GROUP_AUTOPROXY": ...,
        # "REDSHIFT_PROXYEXPORT_GROUP_OPTIONS": ...,
    }
    if verbose:
        log.debug(
            "Preparing Redshift Proxy export with options: %s",
            json.dumps(applied_options, indent=4, default=str),
        )

    for key, value in applied_options.items():
        key_id = getattr(c4d, key)
        # There appears to be a bug where if the value is just set directly
        # that it fails to apply them for the export, e.g. still exporting the
        # whole scene even though `c4d.ABCEXPORT_SELECTION_ONLY` is True.
        # See: https://developers.maxon.net/forum/topic/12767/alembic-export-options-not-working/6  # noqa: E501
        if isinstance(value, (bool, int)):
            options[key_id] = not value
        options[key_id] = value

    # Ensure output directory exists
    parent_dir = os.path.dirname(filepath)
    os.makedirs(parent_dir, exist_ok=True)

    if c4d.documents.SaveDocument(
        doc,
        filepath,
        c4d.SAVEDOCUMENTFLAGS_DONTADDTORECENTLIST,
        redshift.Frsproxyexport,
    ):
        if verbose:
            log.debug("Extracted Redshift Proxy to: %s", filepath)
    else:
        log.error("Extraction of Redshift Proxy failed: %s", filepath)

    return filepath


def resolve_parameters(values):
    """Map c4d attribute names to their ids, skipping unknown attributes.

    Args:
        values (dict[str, Any]): Attribute name to value mapping.

    Returns:
        dict[int, Any]: Parameter id to value mapping.
    """
    settings = {}
    for name, value in values.items():
        param_id = getattr(c4d, name, None)
        if param_id is None:
            log.debug("Skipping unknown Cinema 4D attribute: %s", name)
            continue
        settings[param_id] = value
    return settings


def set_parameters(container, values):
    """Set container values, coerced to the type each parameter stores.

    Cinema 4D containers are strictly typed, e.g. assigning an `int` to a
    float parameter like `c4d.RDATA_XRES` raises a `TypeError`.

    Args:
        container (c4d.BaseContainer): Container to set the values on.
        values (dict[int, Any]): Parameter id to value mapping.
    """
    for param_id, value in values.items():
        param_type = container.GetType(param_id)
        if param_type == c4d.DA_REAL:
            value = float(value)
        elif param_type in (c4d.DA_LONG, c4d.DA_LLONG):
            value = int(value)
        container[param_id] = value


def set_node_parameters(node, values):
    """Set parameters on a node instead of writing its container directly.

    Node assignment goes through the plug-in's parameter handling, which the
    viewport render effect relies on - writing its raw container leaves the
    display filters without effect.

    Args:
        node (c4d.BaseList2D): Node to set the values on.
        values (dict[int, Any]): Parameter id to value mapping.
    """
    for param_id, value in values.items():
        node[param_id] = value
        if node[param_id] != value:
            log.debug("Parameter %s did not apply: %s", param_id, value)


def get_display_filters(prefix, show_splines=False, show_nulls=False):
    """Resolve the display filter values for a review render.

    Args:
        prefix (str): Attribute prefix, `VP_PREVIEWHARDWARE_` for the viewport
            render effect or `BASEDRAW_` for the view.
        show_splines (bool): Include splines.
        show_nulls (bool): Include nulls.

    Returns:
        dict[int, bool]: Parameter id to value mapping.
    """
    values = {prefix + name: False for name in HIDDEN_DISPLAY_FILTERS}
    values[prefix + SPLINE_DISPLAY_FILTER] = show_splines
    values[prefix + NULL_DISPLAY_FILTER] = show_nulls
    return resolve_parameters(values)


def create_playblast_render_data(filepath,
                                 frame_start,
                                 frame_end,
                                 fps,
                                 width,
                                 height,
                                 geometry_only=True,
                                 show_splines=False,
                                 show_nulls=False):
    """Create the render settings for a playblast.

    These are standalone render settings using the viewport renderer with its
    own video post, so none of the scene's render settings are used.

    Args:
        filepath (str): The filepath to render the movie to.
        frame_start (int): Frame start.
        frame_end (int): Frame end.
        fps (float): Frames per second.
        width (int): Resolution width.
        height (int): Resolution height.
        geometry_only (bool): Render geometry only, excluding splines, nulls
            and all other viewport-only elements.
        show_splines (bool): Include splines. Requires `geometry_only` off.
        show_nulls (bool): Include nulls. Requires `geometry_only` off.

    Returns:
        c4d.documents.RenderData: The playblast render settings.
    """
    render_data = c4d.documents.RenderData()
    render_data.SetName("AYON Review")

    settings = resolve_parameters(PLAYBLAST_SETTINGS)
    settings.update({
        c4d.RDATA_RENDERENGINE: c4d.RDATA_RENDERENGINE_PREVIEWHARDWARE,
        # Frame rate and range. Frame from/to are `c4d.BaseTime` parameters.
        c4d.RDATA_FRAMERATE: float(fps),
        c4d.RDATA_FRAMESEQUENCE: c4d.RDATA_FRAMESEQUENCE_MANUAL,
        c4d.RDATA_FRAMEFROM: c4d.BaseTime(frame_start, fps),
        c4d.RDATA_FRAMETO: c4d.BaseTime(frame_end, fps),
        # Resolution
        c4d.RDATA_XRES: float(width),
        c4d.RDATA_YRES: float(height),
        c4d.RDATA_FILMASPECT: float(width) / float(height),
        c4d.RDATA_ALPHACHANNEL: True,
    })
    container = render_data.GetDataInstance()
    set_parameters(container, settings)
    container.SetFilename(c4d.RDATA_PATH, filepath)

    # The viewport render effect defines what of the scene is rendered. It
    # must be inserted before its parameters are set.
    video_post = c4d.documents.BaseVideoPost(
        c4d.RDATA_RENDERENGINE_PREVIEWHARDWARE
    )
    render_data.InsertVideoPostLast(video_post)

    vp_settings = resolve_parameters(HARDWARE_SETTINGS)
    vp_settings.update(get_display_filters("VP_PREVIEWHARDWARE_",
                                           show_splines=show_splines,
                                           show_nulls=show_nulls))
    vp_settings[c4d.VP_PREVIEWHARDWARE_ONLY_GEOMETRY] = geometry_only
    set_node_parameters(video_post, vp_settings)

    return render_data


def create_playblast_document(doc, show_splines=False, show_nulls=False):
    """Copy the document to render the playblast from.

    The viewport renderer mirrors the view it renders from, so the filters
    have to be set on the document's view as well. Rendering a copy keeps the
    artist's document, render settings and viewport untouched.

    Args:
        doc (c4d.documents.BaseDocument): Document to copy.
        show_splines (bool): Include splines.
        show_nulls (bool): Include nulls.

    Returns:
        c4d.documents.BaseDocument: The document copy to render.
    """
    render_doc = doc.GetClone(c4d.COPYFLAGS_DOCUMENT)

    # Keep the document location so relative asset paths keep resolving
    render_doc.SetDocumentPath(doc.GetDocumentPath())
    render_doc.SetDocumentName(doc.GetDocumentName())

    filters = get_display_filters("BASEDRAW_",
                                  show_splines=show_splines,
                                  show_nulls=show_nulls)
    base_draw_count = render_doc.GetBaseDrawCount()
    if not base_draw_count:
        log.debug("Document copy has no view to set display filters on.")
    for index in range(base_draw_count):
        base_draw = render_doc.GetBaseDraw(index)
        if base_draw is not None:
            set_node_parameters(base_draw, filters)

    return render_doc


def render_playblast(filepath,
                     frame_start=None,
                     frame_end=None,
                     fps=None,
                     width=1920,
                     height=1080,
                     geometry_only=True,
                     show_splines=False,
                     show_nulls=False,
                     doc=None):
    """Create a playblast of the given or active document.

    The playblast renders a copy of the document with its own render settings,
    so the scene, its render settings and the artist's viewport are never
    changed.

    Args:
        filepath(str): The filepath to render the movie to.
        frame_start (Optional[int]): Frame start.
            Defaults to document start time if not provided.
        frame_end (Optional[int]): Frame end.
            Defaults to document end time if not provided.
        fps (Optional[float]): Frames per second.
            Defaults to the document fps if not provided.
        width (int): Resolution width for the render.
        height (int): Resolution height for the render.
        geometry_only (bool): Render geometry only. Disable to include
            splines and/or nulls; all other viewport-only elements stay
            excluded either way.
        show_splines (bool): Include splines. Requires `geometry_only` off.
        show_nulls (bool): Include nulls. Requires `geometry_only` off.
        doc (Optional[c4d.documents.BaseDocument]): Document to operate in.
            Defaults to active document if not set.

    Returns:
        str: The filepath of the rendered movie.
    """

    doc = doc or c4d.documents.GetActiveDocument()
    doc_fps = doc.GetFps()
    if fps is None:
        fps = doc_fps
    if frame_start is None:
        frame_start = doc.GetMinTime().GetFrame(doc_fps)
    if frame_end is None:
        frame_end = doc.GetMaxTime().GetFrame(doc_fps)

    width = int(width)
    height = int(height)

    render_data = create_playblast_render_data(
        filepath,
        frame_start=frame_start,
        frame_end=frame_end,
        fps=fps,
        width=width,
        height=height,
        geometry_only=geometry_only,
        show_splines=show_splines,
        show_nulls=show_nulls,
    )

    render_doc = create_playblast_document(doc,
                                           show_splines=show_splines,
                                           show_nulls=show_nulls)
    render_doc.InsertRenderData(render_data)
    # The viewport renderer reads its settings from the active render data
    render_doc.SetActiveRenderData(render_data)

    bmp = c4d.bitmaps.BaseBitmap()
    if bmp.Init(x=width, y=height, depth=24) != c4d.IMAGERESULT_OK:
        raise RenderError(
            "An error occurred during rendering: could not create bitmap."
        )

    # Ensure output directory exists
    os.makedirs(os.path.dirname(filepath), exist_ok=True)

    result = c4d.documents.RenderDocument(
        render_doc,
        # `GetData()` is deprecated since 2024.0
        render_data.GetDataInstance(),
        bmp,
        c4d.RENDERFLAGS_EXTERNAL | c4d.RENDERFLAGS_NODOCUMENTCLONE,
    )
    if result != c4d.RENDERRESULT_OK:
        raise RenderError(
            "Failed to render {filepath}. (error code: {result})".format(
                filepath=filepath, result=result
            )
        )

    return filepath
