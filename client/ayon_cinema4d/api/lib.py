"""Library functions for Cinema4d."""
import contextlib
import math
import json

import c4d

from ayon_core.lib import NumberDef

AYON_CONTAINERS = "AYON_CONTAINERS"
JSON_PREFIX = "JSON::"


def collect_animation_defs(create_context, fps=False):
    """Get the basic animation attribute definitions for the publisher.

    Arguments:
        create_context (CreateContext): The context of publisher will be
            used to define the defaults for the attributes to use the current
            context's entity frame range as default values.
        step (bool): Whether to include `step` attribute definition.
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
        doc = active_document()
        current_fps = doc.GetFps()
        fps_def = NumberDef(
            "fps", label="FPS", default=current_fps, decimals=5
        )
        defs.append(fps_def)

    return defs


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
        doc.SetSelection(node, c4d.SELECTION_NEW)


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
            raise TypeError("Unsupported type: %r" % type(value))

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
        value = obj[description_id]
        user_data[key] = value

    return user_data


def read(node) -> dict:
    """Return user-defined attributes from `node`"""

    data = obj_user_data_to_dict(node)

    # data can be None, if so just return it
    if data is None:
        return {}

    # Ignore hidden/internal data
    data = {
        key: value
        for key, value in data.items() if not key.startswith("_")
    }

    for key, value in data.items():
        if isinstance(value, str) and value.startswith(JSON_PREFIX):
            data[key] = json.loads(value[len(JSON_PREFIX):])

    return data


def get_object_user_data_by_name(obj, user_data_name):
    for description_id, base_container in obj.GetUserDataContainer():
        if base_container[c4d.DESC_NAME] == user_data_name:
            return obj[description_id]


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
        next_obj = next_obj.GetPred()

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


def set_frame_range_from_entity(task_entity, doc=None):
    """Set scene FPS adn resolution from task entity"""
    if doc is None:
        doc = active_document()
    attrib = task_entity["attrib"]

    # get handles values
    handle_start = int(attrib["handleStart"])
    handle_end = int(attrib["handleEnd"])

    f_fps = float(attrib["fps"])
    i_fps = int(math.ceil(attrib["fps"]))
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
        # set render fps
        rd[c4d.RDATA_FRAMERATE] = f_fps
        # set render frame range
        rd[c4d.RDATA_FRAMEFROM] = bt_frame_start
        rd[c4d.RDATA_FRAMETO] = bt_frame_end
        rd = rd.GetNext()

    c4d.EventAdd()


def set_resolution_from_entity(task_entity, doc=None):
    """Set render resolution from task entity"""
    if doc is None:
        doc = active_document()

    attrib = task_entity["attrib"]
    width: int = int(attrib["resolutionWidth"])
    height: int = int(attrib["resolutionHeight"])

    rd = doc.GetFirstRenderData()
    while rd:
        rd[c4d.RDATA_XRES] = width
        rd[c4d.RDATA_YRES] = height
        rd = rd.GetNext()
    c4d.EventAdd()
