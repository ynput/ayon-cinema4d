import logging

from ayon_core.pipeline.context_tools import get_current_task_entity
from ayon_core.pipeline.colorspace import (
    get_current_context_imageio_config_preset,
)
from .lib import (
    set_resolution_from_entity,
    set_frame_range_from_entity
)

import c4d

log = logging.getLogger(__name__)

REDSHIFT_RENDER_ENGINE_ID = 1036219


def reset_frame_range():
    task_entity = get_current_task_entity()
    set_frame_range_from_entity(task_entity)


def reset_resolution():
    task_entity = get_current_task_entity()
    set_resolution_from_entity(task_entity)


def reset_colorspace():
    ocio_config = get_current_context_imageio_config_preset()
    if not ocio_config:
        log.info("No ocio config set.")
        return

    # Set the document colorspace to use OCIO from the OCIO env var
    doc = c4d.documents.GetActiveDocument()
    doc[c4d.DOCUMENT_COLOR_MANAGEMENT] = c4d.DOCUMENT_COLOR_MANAGEMENT_OCIO
    doc[c4d.DOCUMENT_OCIO_CONFIG] = "$OCIO"

    # TODO: Get preferred OCIO settings from project settings
    # colorspace: str = "colorspace"
    # display: str = "display"
    # view: str = "view"
    #
    # doc[c4d.DOCUMENT_OCIO_RENDER_COLORSPACE] = colorspace
    # doc[c4d.DOCUMENT_OCIO_DISPLAY_COLORSPACE] = display
    # doc[c4d.DOCUMENT_OCIO_VIEW_TRANSFORM] = view
    # doc[c4d.DOCUMENT_OCIO_VIEW_TRANSFORM_THUMBNAILS] = view
    #
    # # Iterate over the video post to find one matching the render engine.
    # render_data = c4d.documents.GetActiveDocument().GetActiveRenderData()
    # video_post = render_data.GetFirstVideoPost()
    # while video_post:
    #     # Set redshift render colorspace
    #     if video_post.CheckType(REDSHIFT_RENDER_ENGINE_ID):
    #         _set_redshift_colorspace(video_post, colorspace, display, view)
    #     video_post = video_post.GetNext()

    c4d.EventAdd()


def reset_render_settings():
    doc = c4d.documents.GetActiveDocument()
    render_data = doc.GetActiveRenderData()

    # TODO: Add redshift data if not existing
    #       Set as active renderer

    # Set renderer to Redshift
    render_data[c4d.RDATA_RENDERENGINE] = REDSHIFT_RENDER_ENGINE_ID

    # Set output filepaths
    # Render relatively to the scene
    render_path: str = "./renders/cinema4d/$prj/$take/$pass"
    render_data[c4d.RDATA_MULTIPASS_FILENAME] = render_path

    # Save only multipass
    render_data[c4d.RDATA_SAVEIMAGE] = False  # do not save regular image
    render_data[c4d.RDATA_MULTIPASS_SAVEIMAGE] = True  # save multipass
    render_data[c4d.RDATA_MULTIPASS_SUFFIX] = True  # pass name suffix
    render_data[c4d.RDATA_MULTIPASS_ENABLE] = True  # enable multi-layer-file
    # use the names of the multipass in render settings
    render_data[c4d.RDATA_MULTIPASS_USERNAMES] = False

    # Set EXR file format
    render_data[c4d.RDATA_MULTIPASS_SAVEFORMAT] = c4d.FILTER_EXR

    # Trigger update
    c4d.EventAdd()


def _set_redshift_colorspace(video_post, colorspace, display, view):
    # TODO: video_post[REDSHIFT_RENDERER_COLOR_MANAGEMENT_OCIO_CONFIG]?
    # TODO: video_post[REDSHIFT_RENDERER_COLOR_MANAGEMENT_OCIO_USE_FILE_RULES]?
    video_post[c4d.REDSHIFT_RENDERER_COLOR_MANAGEMENT_OCIO_RENDERING_COLORSPACE] = colorspace  # noqa: E501
    video_post[c4d.REDSHIFT_RENDERER_COLOR_MANAGEMENT_OCIO_DISPLAY] = display
    video_post[c4d.REDSHIFT_RENDERER_COLOR_MANAGEMENT_OCIO_VIEW] = view

