"""Library functions for Cinema4d."""
import contextlib
import math
import json
import re

import ayon_api
import c4d

from ayon_core.lib import NumberDef
from ayon_core.version import __version__ as core_version

AYON_CONTAINERS = "AYON_CONTAINERS"
JSON_PREFIX = "JSON::"
# First ayon-core version integrating `versionTags`
VERSION_TAGS_CORE_VERSION = (1, 9, 8)
TAG_COLOR = "#5bb8f5"


def collect_animation_defs(create_context, fps=False):
    """Get the basic animation attribute definitions for the publisher.

    Arguments:
        create_context (CreateContext): The context of publisher will be
            used to define the defaults for the attributes to use the current
            context's entity frame range as default values.
        fps (bool): Whether to include `fps` attribute definition.

    Returns:
        List[NumberDef]: List of number attribute definitions.

    """

    # use task entity attributes to set defaults based on current context
    task_entity = create_context.get_current_task_entity()
    attrib: dict = task_entity["attrib"]
    frame_start: int = attrib["frameStart"]
    frame_end: int = attrib["frameEnd"]
    handle_start: int = attrib["handleStart"]
    handle_end: int = attrib["handleEnd"]

    # build attributes
    defs = [
        NumberDef("frameStart",
                  label="Frame Start",
                  default=frame_start,
                  decimals=0),
        NumberDef("frameEnd",
                  label="Frame End",
                  default=frame_end,
                  decimals=0),
        NumberDef("handleStart",
                  label="Handle Start",
                  tooltip="Frames added before frame start to use as handles.",
                  default=handle_start,
                  decimals=0),
        NumberDef("handleEnd",
                  label="Handle End",
                  tooltip="Frames added after frame end to use as handles.",
                  default=handle_end,
                  decimals=0),
    ]

    if fps:
        # Task fps, the document fps is an integer in Cinema 4D
        default_fps = attrib.get("fps") or active_document().GetFps()
        fps_def = NumberDef(
            "fps", label="FPS", default=float(default_fps), decimals=5
        )
        defs.append(fps_def)

    return defs


def collect_resolution_defs(create_context):
    """Get the resolution attribute definitions, defaults from the task.

    Returns:
        List[NumberDef]: Width, height and pixel aspect definitions.
    """
    attrib: dict = create_context.get_current_task_entity()["attrib"]
    return [
        NumberDef("resolutionWidth",
                  label="Resolution Width",
                  default=int(attrib["resolutionWidth"]),
                  decimals=0,
                  minimum=1,
                  maximum=65535),
        NumberDef("resolutionHeight",
                  label="Resolution Height",
                  default=int(attrib["resolutionHeight"]),
                  decimals=0,
                  minimum=1,
                  maximum=65535),
        NumberDef("pixelAspect",
                  label="Pixel Aspect",
                  default=float(attrib["pixelAspect"]),
                  decimals=4,
                  minimum=0.01),
    ]


def get_main_window():
    return None


def active_document():
    """Get the active Cinema4d document.

    Returns:
        c4d.documents.BaseDocument: The active document.
    """

    return c4d.documents.GetActiveDocument()


@contextlib.contextmanager
def maintained_selection():
    """Maintain selection during context."""

    doc = active_document()
    previous_selection = doc.GetSelection()
    try:
        yield
    finally:
        set_selection(doc, previous_selection)


def set_selection(doc, nodes):
    if not nodes:
        # Clear selection
        for node in doc.GetSelection():
            doc.SetSelection(node, c4d.SELECTION_SUB)
        return

    it = iter(nodes)
    doc.SetSelection(next(it), c4d.SELECTION_NEW)
    for node in it:
        # SELECTION_NEW would clear the nodes selected before
        doc.SetSelection(node, c4d.SELECTION_ADD)


@contextlib.contextmanager
def undo_chunk():
    """Open a undo chunk during context."""
    doc = active_document()
    try:
        doc.StartUndo()
        yield
    finally:
        doc.EndUndo()


def get_unique_namespace(folder_name, prefix=None, suffix=None, doc=None):
    """Get a unique namespace for a newly loaded asset.

    Go through all loaded assets and if a loaded asset with the same name in
    encountered, go 1 version higher. So for example if you load 'foo'
    and there is already a 'foo_01', set the namespace to 'foo_02'.

    You can optionally set a prefix or suffix.

    Arguments:
        folder_name (str): The name of the folder.
        prefix (optional str): An optional prefix for the namespace.
        suffix (optional str): An optional suffix for the namespace.
        doc (optional c4d.documents.BaseDocument): Optional Cinema4d document
            to work on. Default is the active document.

    Returns:
        str: The unique namespace.
    """
    doc = doc or active_document()
    prefix = prefix or ""
    suffix = suffix or ""
    iteration = 1
    unique = "{prefix}{asset_name}_{iteration:02d}{suffix}".format(
        prefix=prefix,
        asset_name=folder_name,
        iteration=iteration,
        suffix=suffix,
    )

    while doc.SearchObject(unique):
        iteration += 1
        unique = "{prefix}{asset_name}_{iteration:02d}{suffix}".format(
            prefix=prefix,
            asset_name=folder_name,
            iteration=iteration,
            suffix=suffix,
        )

    return unique


def imprint(node, data, group=None):
    """Write `data` to `node` as userDefined attributes

    Arguments:
        node (c4d.BaseObject): The selection object
        data (dict): Dictionary of key/value pairs
    """

    existing_user_data = node.GetUserDataContainer()
    existing_to_id = {}
    for description_id, base_container in existing_user_data:
        key = base_container[c4d.DESC_NAME]
        existing_to_id[key] = description_id

    # If `group` is specified, find the group to add new attributes to.
    group_id = None
    if group:
        # Search the group first, if it does not exist, create it.
        for description_id, base_container in existing_user_data:
            name = base_container[c4d.DESC_NAME]
            if name == group and description_id[1].dtype == c4d.DTYPE_GROUP:
                group_id = description_id
                break
        else:
            # Create the group
            group_bc = c4d.GetCustomDatatypeDefault(c4d.DTYPE_GROUP)
            group_bc[c4d.DESC_NAME] = group
            group_bc[c4d.DESC_SHORT_NAME] = group
            group_bc[c4d.DESC_TITLEBAR] = True
            group_bc[c4d.DESC_GUIOPEN] = False
            group_id = node.AddUserData(group_bc)

    for key, value in data.items():

        if callable(value):
            # Support values evaluated at imprint
            value = value()

        if isinstance(value, bool):
            add_type = c4d.DTYPE_BOOL
        elif isinstance(value, str):
            add_type = c4d.DTYPE_STRING
        elif isinstance(value, int):
            add_type = c4d.DTYPE_LONG
        elif isinstance(value, float):
            add_type = c4d.DTYPE_REAL
        elif isinstance(value, (dict, list)):
            add_type = c4d.DTYPE_STRING
            value = f"{JSON_PREFIX}{json.dumps(value)}"
        else:
            raise TypeError(
                f"Unsupported type for {key}: {value} ({type(value)})")

        if key in existing_to_id:
            # Set existing
            element = existing_to_id[key]
        else:
            # Create new
            base_container = c4d.GetCustomDataTypeDefault(add_type)
            base_container[c4d.DESC_NAME] = key
            base_container[c4d.DESC_SHORT_NAME] = key
            base_container[c4d.DESC_ANIMATE] = c4d.DESC_ANIMATE_OFF
            if group_id:
                base_container[c4d.DESC_PARENTGROUP] = group_id

            element = node.AddUserData(base_container)

        node[element] = value

    c4d.EventAdd()


def get_objects_by_type(object_type, obj, object_list):
    while obj:
        if obj.GetTypeName() == object_type:
            object_list.append(obj)
        get_objects_by_type(object_type, obj.GetDown(), object_list)
        obj = obj.GetNext()
    return object_list


def obj_user_data_to_dict(obj) -> dict:
    """Construct a simple dictionary from the user data.

    Convert the user data to a dictionary so it's easier to work with.

    Returns:
        dict[str, Any]: User data of object..

    """
    if not obj.GetUserDataContainer():
        return None

    user_data = {}

    for description_id, base_container in obj.GetUserDataContainer():
        key = base_container[c4d.DESC_NAME]

        try:
            value = obj[description_id]
        except AttributeError:
            # Fix #23: Silently ignore values that are not wrapped to Python
            #  because we know user data we are interested in isn't any of
            #  those anyway. Avoids object unknown in Python error.
            continue

        user_data[key] = value

    return user_data


def read(node) -> dict:
    """Return user-defined attributes from `node`"""

    data = obj_user_data_to_dict(node)

    # data can be None, if so just return it
    if data is None:
        return {}

    data = {
        key: value
        for key, value in data.items()
        # Ignore hidden/internal data
        if not key.startswith("_")
        # Ignore values that are None (e.g. groups in user data)
        and value is not None
    }

    for key, value in data.items():
        if isinstance(value, str) and value.startswith(JSON_PREFIX):
            data[key] = json.loads(value[len(JSON_PREFIX):])

    return data


def get_object_user_data_by_name(obj, user_data_name):
    for description_id, base_container in obj.GetUserDataContainer():
        if base_container[c4d.DESC_NAME] == user_data_name:
            try:
                return obj[description_id]
            except AttributeError:
                # Fix #23: Silently ignore values that are not wrapped to
                #  Python because we know user data we are interested in isn't
                #  any of those anyway. Avoids object unknown in Python error.
                continue


def get_siblings(obj, include_self=True):
    result = []
    if include_self:
        result.append(obj)

    # Get pred siblings
    pred_obj = obj.GetPred()
    while pred_obj:
        result.append(pred_obj)
        pred_obj = pred_obj.GetPred()

    # Get next sibilings
    next_obj = obj.GetNext()
    while next_obj:
        result.append(next_obj)
        next_obj = next_obj.GetNext()

    return result


def iter_objects_by_name(object_name, root_obj, obj_type=None):
    for obj in iter_objects(root_obj):
        if obj.GetName() == object_name:
            if not obj_type or obj_type == obj.GetTypeName():
                yield obj


def get_objects_by_name(object_name, root_obj, obj_type=None):
    return list(iter_objects_by_name(object_name, root_obj, obj_type))


def iter_objects(root_obj):
    if not root_obj:
        # This way we 'pass' silently when passed `doc.GetFirstObject()` but
        # the scene has no objects whatsoever.
        return

    for root_obj in get_siblings(root_obj, include_self=True):
        yield root_obj

        for child in iter_all_children(root_obj):
            yield child


def iter_all_children(obj):
    """Yield all children of an object, including grandchildren."""
    stack = obj.GetChildren()
    while stack:
        child_obj = stack.pop()
        stack.extend(child_obj.GetChildren())
        yield child_obj


def get_all_children(obj):
    """Returns all children of an object, including grandchildren."""
    return list(iter_all_children(obj))


def get_objects_from_container(container, existing_only=True):
    """Get the objects from the container.

    A container in Cinema4d is a selection object. We have to get the so called
    InExcludeData, get the object count and then get the objects at the indices.

    Arguments:
        container (c4d.BaseObject): The object containing selections.

    Returns:
        generator: The objects in the selection object.
    """
    doc: c4d.documents.BaseDocument = container.GetMain()
    assert isinstance(doc, c4d.documents.BaseDocument)
    in_exclude_data = container[c4d.SELECTIONOBJECT_LIST]

    # If the container is not a selection object list yield no child objects
    if not in_exclude_data:
        return

    object_count = in_exclude_data.GetObjectCount()
    for i in range(object_count):
        obj = in_exclude_data.ObjectFromIndex(doc, i)
        if existing_only and not obj:
            continue

        yield obj


def add_objects_to_container(container, nodes):
    """Add the nodes to the container.

    A container in Cinema4d is a selection object. We have to get the so called
    InExcludeData and add the objects to it.

    Args:
        container: The Avalon container to add the nodes to
        nodes (list): The nodes to add to the container
    """
    in_exclude_data = container[c4d.SELECTIONOBJECT_LIST]
    for node in nodes:
        in_exclude_data.InsertObject(node, 1)
    container[c4d.SELECTIONOBJECT_LIST] = in_exclude_data
    c4d.EventAdd()


def get_materials_from_objects(objects):
    """Get the materials assigned to the objects.

    Arguments:
        objects (List[c4d.BaseObject]): Objects to get materials for.

    Returns:
        List[c4d.BaseMaterial]: List of assigned materials.
    """

    materials = []
    for obj in objects:
        material_tags = [
            tag for tag in obj.GetTags() if tag.GetTypeName() == "Material"
        ]
        for material_tag in material_tags:
            material = material_tag.GetMaterial()
            if material:
                materials.append(material)

    return materials


def get_document_fps(fps):
    """Return the integer document fps used for a (fractional) fps."""
    return int(math.ceil(fps))


def set_frame_range_from_entity(task_entity, doc=None):
    """Set scene fps and frame range from task entity"""
    if doc is None:
        doc = active_document()
    attrib = task_entity["attrib"]

    # get handles values
    handle_start = int(attrib["handleStart"])
    handle_end = int(attrib["handleEnd"])

    f_fps = float(attrib["fps"])
    i_fps = get_document_fps(f_fps)
    frame_start = int(attrib["frameStart"]) - handle_start
    frame_end = int(attrib["frameEnd"]) + handle_end
    bt_frame_start = c4d.BaseTime(frame_start, i_fps)
    bt_frame_end = c4d.BaseTime(frame_end, i_fps)

    # set document fps
    doc.SetFps(i_fps)

    # set document frame range
    doc.SetMinTime(bt_frame_start)
    doc.SetMaxTime(bt_frame_end)
    doc.SetLoopMinTime(bt_frame_start)
    doc.SetLoopMaxTime(bt_frame_end)

    rd = doc.GetFirstRenderData()
    while rd:
        set_render_frame_range(rd, frame_start, frame_end, f_fps)
        rd = rd.GetNext()

    c4d.EventAdd()


def set_resolution_from_entity(task_entity, doc=None):
    """Set render resolution from task entity"""
    if doc is None:
        doc = active_document()

    attrib = task_entity["attrib"]
    rd = doc.GetFirstRenderData()
    while rd:
        set_render_resolution(rd,
                              attrib["resolutionWidth"],
                              attrib["resolutionHeight"],
                              attrib["pixelAspect"])
        rd = rd.GetNext()
    c4d.EventAdd()


def get_take_render_data(doc, take=None):
    """Return a take and the render settings it renders with.

    Args:
        doc (c4d.documents.BaseDocument): Document of the take.
        take (Optional[c4d.modules.takesystem.BaseTake]): Take, defaults to
            the current take.

    Returns:
        tuple[BaseTake, c4d.documents.RenderData]: Take and its effective
            render settings (inherited from parent takes).
    """
    take_data = doc.GetTakeData()
    if take is None:
        take = take_data.GetCurrentTake()
    result = take.GetEffectiveRenderData(take_data)
    render_data = result[0] if result else doc.GetActiveRenderData()
    return take, render_data


def get_render_frame_range(doc, render_data):
    """Return the frame range the render settings render.

    Resolves the Frame Range mode (Manual, Current Frame, All Frames,
    Preview Range) of the render settings.

    Returns:
        Optional[tuple[int, int]]: Start and end frame, None for Custom
            frames which have no continuous range.
    """
    mode = render_data[c4d.RDATA_FRAMESEQUENCE]
    if mode == c4d.RDATA_FRAMESEQUENCE_MANUAL:
        times = (render_data[c4d.RDATA_FRAMEFROM],
                 render_data[c4d.RDATA_FRAMETO])
    elif mode == c4d.RDATA_FRAMESEQUENCE_CURRENTFRAME:
        times = (doc.GetTime(), doc.GetTime())
    elif mode == c4d.RDATA_FRAMESEQUENCE_ALLFRAMES:
        times = (doc.GetMinTime(), doc.GetMaxTime())
    elif mode == c4d.RDATA_FRAMESEQUENCE_PREVIEWRANGE:
        times = (doc.GetLoopMinTime(), doc.GetLoopMaxTime())
    else:
        return None
    fps = doc.GetFps()
    return int(times[0].GetFrame(fps)), int(times[1].GetFrame(fps))


def set_render_frame_range(render_data, frame_start, frame_end, fps):
    """Set a manual frame range and frame rate on render settings.

    Args:
        render_data (c4d.documents.RenderData): Render settings.
        frame_start (int): Start frame, handles included.
        frame_end (int): End frame, handles included.
        fps (float): Frame rate.
    """
    doc_fps = get_document_fps(fps)
    render_data[c4d.RDATA_FRAMESEQUENCE] = c4d.RDATA_FRAMESEQUENCE_MANUAL
    render_data[c4d.RDATA_FRAMEFROM] = c4d.BaseTime(int(frame_start), doc_fps)
    render_data[c4d.RDATA_FRAMETO] = c4d.BaseTime(int(frame_end), doc_fps)
    render_data[c4d.RDATA_FRAMERATE] = float(fps)


@contextlib.contextmanager
def unlocked_ratio(render_data):
    """Temporarily unlock the ratio of the render resolution."""
    original = render_data[c4d.RDATA_LOCKRATIO]
    render_data[c4d.RDATA_LOCKRATIO] = False
    try:
        yield
    finally:
        render_data[c4d.RDATA_LOCKRATIO] = original


def set_render_resolution(render_data, width, height, pixel_aspect):
    """Set resolution and pixel aspect on render settings."""
    # Fix #20: Set the virtual resolution with user interaction so Redshift
    # still triggers some additional checks on the attribute change.
    with unlocked_ratio(render_data):
        flag = c4d.DESCFLAGS_SET_USERINTERACTION
        render_data.SetParameter(c4d.RDATA_XRES_VIRTUAL, float(width), flag)
        render_data.SetParameter(c4d.RDATA_YRES_VIRTUAL, float(height), flag)

    render_data[c4d.RDATA_PIXELASPECT] = float(pixel_aspect)


def iter_takes(take):
    """Yield `take`, its siblings and all child takes in Take Manager order."""
    while take:
        yield take
        yield from iter_takes(take.GetDown())
        take = take.GetNext()


def iter_marked_takes(doc):
    """Yield the takes marked for rendering/export in the Take Manager.

    Args:
        doc (c4d.documents.BaseDocument): Document to get the takes from.

    Yields:
        c4d.modules.takesystem.BaseTake: Marked take, Main take included.
    """
    take_data = doc.GetTakeData()
    if take_data is None:
        return
    for take in iter_takes(take_data.GetMainTake()):
        if take.IsChecked():
            yield take


def get_take_variant(take):
    """Return the take name as a valid product variant, e.g. `Take_1`."""
    return re.sub(r"[^A-Za-z0-9_]", "_", take.GetName())


def find_take_in_document(take, doc):
    """Return the take in `doc` at the same hierarchy position as `take`.

    Used to find a take in a copy of its document.

    Args:
        take (c4d.modules.takesystem.BaseTake): Take in the source document.
        doc (c4d.documents.BaseDocument): Document to search, e.g. a copy.

    Returns:
        Optional[c4d.modules.takesystem.BaseTake]: The matching take.
    """
    # Sibling index per level, from the Main take down to `take`
    path = []
    while take.GetUp():
        index = 0
        pred = take.GetPred()
        while pred:
            index += 1
            pred = pred.GetPred()
        path.insert(0, index)
        take = take.GetUp()

    match = doc.GetTakeData().GetMainTake()
    for index in path:
        match = match.GetDown()
        for _ in range(index):
            if match is None:
                break
            match = match.GetNext()
        if match is None:
            return None
    return match


def get_marked_takes_label(doc):
    """Return a UI label listing the marked takes of the document."""
    names = [take.GetName() for take in iter_marked_takes(doc)]
    if not names:
        return "Marked takes: none"
    return "Marked takes: {}".format(", ".join(names))


FRAME_MODE_LABELS = {
    c4d.RDATA_FRAMESEQUENCE_MANUAL: "Manual",
    c4d.RDATA_FRAMESEQUENCE_CURRENTFRAME: "Current Frame",
    c4d.RDATA_FRAMESEQUENCE_ALLFRAMES: "All Frames",
    c4d.RDATA_FRAMESEQUENCE_PREVIEWRANGE: "Preview Range",
}


def get_render_product(creator_attributes):
    """Return the render product settings from the instance attributes.

    Returns:
        dict: Frame range including handles, frame step, fps, resolution
            and pixel aspect.
    """
    attrs = creator_attributes
    return {
        "frame_start": int(attrs["frameStart"]) - int(attrs["handleStart"]),
        "frame_end": int(attrs["frameEnd"]) + int(attrs["handleEnd"]),
        "frame_step": max(int(attrs.get("frameStep", 1)), 1),
        "fps": float(attrs["fps"]),
        "width": int(attrs["resolutionWidth"]),
        "height": int(attrs["resolutionHeight"]),
        "pixel_aspect": float(attrs["pixelAspect"]),
    }


def apply_render_product(doc, render_data, product, dry_run=False):
    """Apply the render product frame and format settings to render settings.

    Args:
        doc (c4d.documents.BaseDocument): Document of the render settings.
        render_data (c4d.documents.RenderData): Render settings to change.
        product (dict): Settings from `get_render_product`.
        dry_run (bool): Only report the differences.

    Returns:
        list[str]: The differences, e.g. "Resolution 500x500 -> 1920x1920".
    """
    changes = []
    fps = product["fps"]
    doc_fps = get_document_fps(fps)
    if doc.GetFps() != doc_fps:
        changes.append(f"Project frame rate {doc.GetFps()} -> {doc_fps}")
        if not dry_run:
            doc.SetFps(doc_fps)

    # Frame range, handles included, in Manual mode
    expected = (product["frame_start"], product["frame_end"])
    current = get_render_frame_range(doc, render_data)
    render_fps = float(render_data[c4d.RDATA_FRAMERATE])
    if current != expected:
        mode = FRAME_MODE_LABELS.get(
            render_data[c4d.RDATA_FRAMESEQUENCE], "Custom"
        )
        if current:
            mode = "{}-{} {}".format(*current, mode)
        changes.append("Frame range ({}) -> {}-{}".format(mode, *expected))
    if abs(render_fps - fps) > 0.001:
        changes.append(f"Frame rate {render_fps:g} -> {fps:g}")
    if not dry_run and (current != expected or abs(render_fps - fps) > 0.001):
        set_render_frame_range(render_data, *expected, fps)

    step = int(render_data[c4d.RDATA_FRAMESTEP])
    if step != product["frame_step"]:
        changes.append(f"Frame step {step} -> {product['frame_step']}")
        if not dry_run:
            render_data[c4d.RDATA_FRAMESTEP] = product["frame_step"]

    size = (int(round(render_data[c4d.RDATA_XRES])),
            int(round(render_data[c4d.RDATA_YRES])))
    pixel_aspect = float(render_data[c4d.RDATA_PIXELASPECT])
    if size != (product["width"], product["height"]):
        changes.append("Resolution {}x{} -> {}x{}".format(
            *size, product["width"], product["height"]
        ))
    if abs(pixel_aspect - product["pixel_aspect"]) > 0.001:
        changes.append(
            f"Pixel aspect {pixel_aspect:g} -> {product['pixel_aspect']:g}"
        )
    if not dry_run and (
        size != (product["width"], product["height"])
        or abs(pixel_aspect - product["pixel_aspect"]) > 0.001
    ):
        set_render_resolution(render_data, product["width"],
                              product["height"], product["pixel_aspect"])

    if render_data[c4d.RDATA_RENDERREGION]:
        changes.append("Render Region on -> off")
        if not dry_run:
            render_data[c4d.RDATA_RENDERREGION] = False

    return changes


def core_supports_version_tags():
    """Return whether ayon-core integrates `versionTags`."""
    version = tuple(int(n) for n in re.findall(r"\d+", core_version)[:3])
    return version >= VERSION_TAGS_CORE_VERSION


def add_project_tag(project_name, tag_name):
    """Add a tag to the project anatomy, needs project manager rights.

    Returns:
        bool: Whether the tag was added, False if it already existed.
    """
    tags = ayon_api.get_project(project_name).get("tags") or []
    if tag_name in {tag["name"] for tag in tags}:
        return False
    ayon_api.update_project(
        project_name, tags=tags + [{"name": tag_name, "color": TAG_COLOR}]
    )
    return True
