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
    "RDATA_FRAMERATE": 12,
    "RDATA_FRAMESEQUENCE": c4d.RDATA_FRAMESEQUENCE_ALLFRAMES,
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
    alembic_plugin = c4d.plugins.FindPlugin(
        c4d.FORMAT_ABCEXPORT,
        c4d.PLUGINTYPE_SCENESAVER,
    )
    if alembic_plugin is None:
        raise Exception("Could not find Alembic plug-in.")

    options = {}
    # Send MSG_RETRIEVEPRIVATEDATA to Alembic export plugin
    if alembic_plugin.Message(c4d.MSG_RETRIEVEPRIVATEDATA, options):
        if "imexporter" not in options:
            raise Exception(
                "Could not find options container for the Alembic exporter."
            )

    # BaseList2D object stored in "imexporter" key hold the settings
    abc_export_options = options["imexporter"]
    if abc_export_options is None:
        raise Exception("Could not find options for the Alembic exporter.")

    # Fallback to Cinema4d timeline if no start or end frame provided.
    if frame_start is None:
        frame_start = doc.GetMinTime().GetFrame(doc.GetFps())
    if frame_end is None:
        frame_end = doc.GetMinTime().GetFrame(doc.GetFps())

    # Animation
    abc_export_options[c4d.ABCEXPORT_FRAME_START] = frame_start
    abc_export_options[c4d.ABCEXPORT_FRAME_END] = frame_end
    abc_export_options[c4d.ABCEXPORT_FRAME_STEP] = frame_step
    abc_export_options[c4d.ABCEXPORT_SUBFRAMES] = sub_frames

    # General
    # abc_export_options[c4d.ABCEXPORT_SCALE] = 1  # c4d.UnitScaleData
    abc_export_options[c4d.ABCEXPORT_SELECTION_ONLY] = selection
    abc_export_options[c4d.ABCEXPORT_CAMERAS] = kwargs.get("cameras", True)
    abc_export_options[c4d.ABCEXPORT_SPLINES] = kwargs.get("splines", False)
    abc_export_options[c4d.ABCEXPORT_HAIR] = kwargs.get("hair", False)
    abc_export_options[c4d.ABCEXPORT_XREFS] = kwargs.get("xrefs", True)
    abc_export_options[c4d.ABCEXPORT_GLOBAL_MATRIX] = global_matrix

    # Subdivision surface
    abc_export_options[c4d.ABCEXPORT_HYPERNURBS] = kwargs.get(
        "subdivisionSurfaces", True
    )
    abc_export_options[c4d.ABCEXPORT_SDS_WEIGHTS] = kwargs.get(
        "subdivisionSurfaceWeights", False
    )
    abc_export_options[c4d.ABCEXPORT_PARTICLES] = kwargs.get("particles", False)
    abc_export_options[c4d.ABCEXPORT_PARTICLE_GEOMETRY] = kwargs.get(
        "particleGeometry", False
    )

    # Optional data
    abc_export_options[c4d.ABCEXPORT_VISIBILITY] = kwargs.get("visibility", True)
    abc_export_options[c4d.ABCEXPORT_UVS] = kwargs.get("uvs", True)
    abc_export_options[c4d.ABCEXPORT_VERTEX_MAPS] = kwargs.get("vertexMaps", False)
    # Vertex normals
    abc_export_options[c4d.ABCEXPORT_NORMALS] = kwargs.get("normals", False)
    abc_export_options[c4d.ABCEXPORT_POLYGONSELECTIONS] = kwargs.get(
        "polygonSelections", True
    )
    abc_export_options[c4d.ABCEXPORT_VERTEX_COLORS] = kwargs.get("vertexColors", False)
    abc_export_options[c4d.ABCEXPORT_POINTS_ONLY] = kwargs.get("pointsOnly", False)
    abc_export_options[c4d.ABCEXPORT_DISPLAY_COLORS] = kwargs.get(
        "displayColors", False
    )
    abc_export_options[c4d.ABCEXPORT_MERGE_CACHE] = kwargs.get("mergeCache", False)

    # abc_export_options[c4d.ABCEXPORT_GROUP] = None  # ???
    # # Don't export child objects with only selected?
    # abc_export_options[c4d.ABCEXPORT_PARENTS_ONLY_MODE] = False
    # abc_export_options[c4d.ABCEXPORT_STR_ANIMATION] = None  # ???
    # abc_export_options[c4d.ABCEXPORT_STR_GENERAL] = None  # ???
    # abc_export_options[c4d.ABCEXPORT_STR_OPTIONS] = None  # ???

    if verbose:
        export_options = kwargs.copy()
        export_options["startFrame"] = frame_start
        export_options["endFrame"] = frame_end
        log.debug(
            "Preparing Alembic export with options: %s",
            json.dumps(export_options, indent=4),
        )

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
    fbx_plugin = c4d.plugins.FindPlugin(FBX_EXPORTER_ID, c4d.PLUGINTYPE_SCENESAVER)
    if fbx_plugin is None:
        raise Exception("Could not find FBX plug-in.")

    options = {}
    # Send MSG_RETRIEVEPRIVATEDATA to FBX export plugin
    if fbx_plugin.Message(c4d.MSG_RETRIEVEPRIVATEDATA, options):
        if "imexporter" not in options:
            raise Exception("Could not find options container for the FBX exporter.")

    # BaseList2D object stored in "imexporter" key hold the settings
    fbx_export_options = options["imexporter"]
    if fbx_export_options is None:
        raise Exception("Could not find options for the FBX exporter.")

    # File format
    fbx_export_options[c4d.FBXEXPORT_FBX_VERSION] = kwargs.get("fbxVersion", 0)
    fbx_export_options[c4d.FBXEXPORT_ASCII] = kwargs.get("fbxAscii", False)

    # General
    fbx_export_options[c4d.FBXEXPORT_SELECTION_ONLY] = kwargs.get(
        "selectionOnly", False
    )
    fbx_export_options[c4d.FBXEXPORT_CAMERAS] = kwargs.get("cameras", True)
    fbx_export_options[c4d.FBXEXPORT_SPLINES] = kwargs.get("splines", True)
    fbx_export_options[c4d.FBXEXPORT_INSTANCES] = kwargs.get("instances", True)
    fbx_export_options[c4d.FBXEXPORT_GLOBAL_MATRIX] = kwargs.get("globalMatrix", False)
    fbx_export_options[c4d.FBXEXPORT_SDS] = kwargs.get("subdivisionSurfaces", True)
    fbx_export_options[c4d.FBXEXPORT_LIGHTS] = kwargs.get("lights", True)

    # Animation
    fbx_export_options[c4d.FBXEXPORT_TRACKS] = kwargs.get("tracks", False)
    fbx_export_options[c4d.FBXEXPORT_BAKE_ALL_FRAMES] = kwargs.get(
        "bakeAllFrames", False
    )
    fbx_export_options[c4d.FBXEXPORT_PLA_TO_VERTEXCACHE] = kwargs.get(
        "plaToVertexCache", False
    )

    # Geometry
    fbx_export_options[c4d.FBXEXPORT_SAVE_NORMALS] = kwargs.get("normals", False)
    fbx_export_options[c4d.FBXEXPORT_SAVE_VERTEX_MAPS_AS_COLORS] = kwargs.get(
        "vertexMapsAsColors", False
    )
    fbx_export_options[c4d.FBXEXPORT_SAVE_VERTEX_COLORS] = kwargs.get(
        "vertexColors", False
    )
    fbx_export_options[c4d.FBXEXPORT_TRIANGULATE] = kwargs.get("triangulate", False)
    fbx_export_options[c4d.FBXEXPORT_SDS_SUBDIVISION] = kwargs.get(
        "bakedSubdivisionSurfaces", False
    )
    fbx_export_options[c4d.FBXEXPORT_LOD_SUFFIX] = kwargs.get("lodSuffix", False)

    # Additional
    if hasattr(c4d, "FBXEXPORT_TEXTURES"):
        # Cinema4d S22 doesn't have this option anymore
        fbx_export_options[c4d.FBXEXPORT_TEXTURES] = kwargs.get("textures", False)
    if hasattr(c4d, "FBXEXPORT_BAKE_MATERIALS"):
        # Cinema4d S22 now has the ability to bake materials
        fbx_export_options[c4d.FBXEXPORT_BAKE_MATERIALS] = kwargs.get(
            "bakeMaterials", False
        )
    fbx_export_options[c4d.FBXEXPORT_EMBED_TEXTURES] = kwargs.get(
        "embedTextures", False
    )
    fbx_export_options[c4d.FBXEXPORT_FLIP_Z_AXIS] = kwargs.get("flipZAxis", False)
    fbx_export_options[c4d.FBXEXPORT_SUBSTANCES] = kwargs.get("substances", False)
    fbx_export_options[c4d.FBXEXPORT_UP_AXIS] = kwargs.get(
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


def render_playblast(filepath, doc=None):
    """Create a playblast of the given or active document.

    Args:
        filepath(str): The filepath to render the movie to.
        doc (c4d.documents.BaseDocument)

    Returns:
        str: The filepath of the rendered movie.
    """

    # Retrieves the current active render settings
    doc = doc or c4d.documents.GetActiveDocument()
    renderdata = doc.GetActiveRenderData().GetData()
    previous_render_engine = renderdata[c4d.RDATA_RENDERENGINE]
    renderdata[c4d.RDATA_RENDERENGINE] = c4d.RDATA_RENDERENGINE_PREVIEWHARDWARE

    # Set render settings
    for k, v in PLAYBLAST_SETTINGS.items():
        renderdata[getattr(c4d, k)] = v
        # renderdata[c4d.RDATA_FRAMEFROM] = c4d.BaseTime(0, doc.GetFps())
        # renderdata[c4d.RDATA_FRAMETO] = c4d.BaseTime(11, doc.GetFps())

    # TODO: Somehow figure out how to (temporarily) overwrite a video post,
    #    or add a new one and remove it afterwards.
    # Set hardware video post
    # hardware_vp = c4d.documents.BaseVideoPost(c4d.RDATA_RENDERENGINE_PREVIEWHARDWARE)
    # for k, v in HARDWARE_SETTINGS.items():
    #     hardware_vp[getattr(c4d, k)] = v
    # renderdata.InsertVideoPost(hardware_vp)

    # prepare bitmap
    xres = PLAYBLAST_SETTINGS["RDATA_XRES"]
    yres = PLAYBLAST_SETTINGS["RDATA_YRES"]

    bmp = c4d.bitmaps.BaseBitmap()
    bmp.Init(x=xres, y=yres, depth=24)
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
