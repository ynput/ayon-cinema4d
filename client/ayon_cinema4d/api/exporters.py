import json
import logging
import os

import c4d

log = logging.getLogger(__name__)


FBX_EXPORTER_ID = 1026370

PLAYBLAST_SETTINGS = {
    # Resolution
    "RDATA_XRES": 1920,
    "RDATA_YRES": 1080,
    "RDATA_LOCKRATIO": True,
    "RDATA_ADAPT_DATARATE": True,
    "RDATA_PIXELRESOLUTION_VIRTUAL": 72,
    "RDATA_PIXELRESOLUTIONUNIT": 1,
    "RDATA_RENDERREGION": False,
    "RDATA_FILMASPECT": 1.778,
    "RDATA_PIXELASPECT": 1,
    # Frame rate and range
    # "RDATA_FRAMERATE": 12,
    # "RDATA_FRAMESEQUENCE": c4d.RDATA_FRAMESEQUENCE_ALLFRAMES,
    # "RDATA_FRAMEFROM": 0,
    # "RDATA_FRAMETO": 11,
    "RDATA_FRAMESTEP": 1,
    "RDATA_FIELD": 0,
    "RDATA_GLOBALSAVE": True,
    "RDATA_SAVEIMAGE": True,
    "RDATA_MULTIPASS_ENABLE": False,
    "RDATA_PROJECTFILE": False,
    "RDATA_FORMAT": c4d.FILTER_MOVIE,  # save as Quicktime movie,
}

HARDWARE_SETTINGS = {
    "VP_PREVIEWHARDWARE_ENHANCEDOPENGL": False,
    "VP_PREVIEWHARDWARE_ANTIALIASING": 2,
    "VP_PREVIEWHARDWARE_SUPERSAMPLING": c4d.VP_PREVIEWHARDWARE_SUPERSAMPLING_NONE,
}


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


def render_playblast(filepath,
                     frame_start=None,
                     frame_end=None,
                     fps=None,
                     width=1920,
                     height=1080,
                     doc=None):
    """Create a playblast of the given or active document.

    Args:
        filepath(str): The filepath to render the movie to.
        frame_start (Optional[int]): Frame start.
            Defaults to document start time if not provided.
        frame_end (Optional[int]): Frame end.
            Defaults to document end time if not provided.
        fps (int): Frames per seconds.
        width (int): Resolution width for the render.
        height (int): Resolution height for the render.
        doc (Optional[c4d.documents.BaseDocument]): Document to operate in.
            Defaults to active document if not set.

    Returns:
        str: The filepath of the rendered movie.
    """

    # Retrieves the current active render settings
    doc = doc or c4d.documents.GetActiveDocument()
    doc_fps = doc.GetFps()
    if fps is None:
        fps = doc_fps
    if frame_start is None:
        frame_start = doc.GetMinTime().GetFrame(doc_fps)
    if frame_end is None:
        frame_end = doc.GetMaxTime().GetFrame(doc_fps)

    renderdata = doc.GetActiveRenderData().GetData()
    previous_render_engine = renderdata[c4d.RDATA_RENDERENGINE]
    renderdata[c4d.RDATA_RENDERENGINE] = c4d.RDATA_RENDERENGINE_PREVIEWHARDWARE

    # Set render settings
    for attr, value in PLAYBLAST_SETTINGS.items():
        renderdata[getattr(c4d, attr)] = value

    # Set FPS and frame range
    renderdata[c4d.RDATA_FRAMERATE] = fps
    renderdata[c4d.RDATA_FRAMESEQUENCE] = c4d.RDATA_FRAMESEQUENCE_MANUAL
    renderdata[c4d.RDATA_FRAMEFROM] = frame_start
    renderdata[c4d.RDATA_FRAMETO] = frame_end

    # Set resolution
    renderdata[c4d.RDATA_XRES] = width
    renderdata[c4d.RDATA_YRES] = height

    renderdata[c4d.RDATA_ALPHACHANNEL] = True

    # TODO: Somehow figure out how to (temporarily) overwrite a video post,
    #    or add a new one and remove it afterwards.
    # Set hardware video post
    # hardware_vp = c4d.documents.BaseVideoPost(c4d.RDATA_RENDERENGINE_PREVIEWHARDWARE)
    # for k, v in HARDWARE_SETTINGS.items():
    #     hardware_vp[getattr(c4d, k)] = v
    # renderdata.InsertVideoPost(hardware_vp)
    bmp = c4d.bitmaps.BaseBitmap()
    bmp.Init(x=width, y=height, depth=24)
    if bmp is None:
        raise RenderError(
            "An error occurred during rendering: could not create bitmap."
        )

    renderdata.SetFilename(c4d.RDATA_PATH, filepath)

    # Renders the document
    result = c4d.documents.RenderDocument(
        doc,
        renderdata,
        bmp,
        c4d.RENDERFLAGS_EXTERNAL | c4d.RENDERFLAGS_NODOCUMENTCLONE,
    )
    if result != c4d.RENDERRESULT_OK:
        raise RenderError(
            "Failed to render {filepath}. (error code: {result})".format(
                filepath=filepath, result=result
            )
        )

    # Switch back to previous render engine,
    # although this doesn't seem to be needed.
    renderdata[c4d.RDATA_RENDERENGINE] = previous_render_engine
    return filepath
