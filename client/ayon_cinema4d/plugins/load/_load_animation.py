import json
import os
import re

import c4d

from ayon_cinema4d.api import lib, pipeline, plugin


class AbcAnimationLoader(plugin.Cinema4DLoader):
    """Load alembic animation on existing models.

    The animation is exported as alembic. Models are loaded as XRef. Then the alembic is
    added to the models with alembic tags.
    """

    label = "Load animation"
    product_types = {"animation"}
    representations = {"abc"}
    order = -10
    icon = "play-circle"
    color = "orange"

    def _filter_alembic_paths(self, path_list):
        """Only return the paths that end with 'ShapeDeformed' or 'Shape'."""

        shape_regex = re.compile(r".*shape[0-9]*(?:deformed)?$", re.IGNORECASE)
        for path in path_list:
            if shape_regex.match(path):
                yield path

    def _get_obj_from_full_path(self, obj_path):
        """Return the object name from the full path.

        E.g. in Maya we might have:
            /marjolein_01:Group/marjolein_01:RIG/marjolein_01:Geometry/
            marjolein_01:model:marjolein_GRP/marjolein_01:model:hoofd_kind_GRP/
            marjolein_01:model:tong/marjolein_01:model:tongShape
        In Cinema4D this might translate to:
            marjolein_01::tong
        """

        # Get the short object name
        obj_name = obj_path.rsplit("/", 2)[-2]
        parts = obj_name.split(":")
        # Assume the first part is the name space and the last part is the actual
        # object name. If there are extra parts, these are probably introduced by
        # the rig and we don't have them in the model.
        # E.g.: wesley_01:model:head -> wesley_01::head
        if len(parts) > 2:
            parts = [parts[0], parts[-1]]

        # By convention a double colon is used as namespace separator in Cinema 4D.
        return "::".join(parts)

    def _make_path_match_dict(self, path_list):
        """Return a filtered path dictionary.

        The keys are the names of the objects as they should be in Cinema, the
        values are the paths that should be passed to the Alembic tags.
        """

        match_dict = {}
        for path in sorted(self._filter_alembic_paths(path_list)):
            key = self._get_obj_from_full_path(path)
            match_dict[key] = path

        return match_dict

    def load(self, context, name=None, namespace=None, options=None):

        doc = lib.active_document()
        doc_fps = doc.GetFps()

        folder = context["folder"]
        start_frame: int = folder["attrib"]["frameStart"]
        end_frame: int = folder["attrib"]["frameEnd"]

        namespace = namespace or lib.get_unique_namespace(
            folder["name"], doc=doc
        )

        filepath = self.filepath_from_context(context)
        filename = os.path.splitext(filepath)[0]
        json_file = "{filename}.json".format(filename=filename)

        with open(json_file, "r") as jsonfile:
            animation_info = json.load(jsonfile)
        path_list = animation_info.get("alembic_paths")
        path_dict = self._make_path_match_dict(path_list)

        nodes = []

        # Add animation to objects with alembic tag
        for obj_name, obj_id in path_dict.items():
            obj = lib.get_objects_by_name(
                obj_name, doc.GetFirstObject(), obj_type="Polygon"
            )
            if not obj:
                self.log.error("Object not found: %s", obj_name)
                continue
            else:
                obj = obj[0]
            self.log.debug("Adding alembic tag to: %s", obj_name)
            alembic_tag = c4d.BaseTag(c4d.Talembicmorphtag)
            obj.InsertTag(alembic_tag)
            alembic_tag[c4d.ALEMBIC_MT_PATH] = filepath
            alembic_tag[c4d.ALEMBIC_MT_IDENTIFIER] = str(obj_id)
            alembic_tag[c4d.ALEMBIC_MT_ANIMATION_OFFSET] = c4d.BaseTime(
                # subtract 1, because the animation already starts at frame 1
                start_frame - 1,
                doc_fps,
            )
            # Turn off interpolation
            alembic_tag[c4d.ALEMBIC_MT_INTERPOLATION] = False
            nodes.append(alembic_tag)

        # Set visibility of objects
        visibility = animation_info["visibility"]
        # In Cinema4d the mode has 3 'states': c4d.MODE_ON (0), c4d.MODE_OFF (1), and
        # c4d.MODE_UNDEF (2)
        # If we have exported the visibility it means it's never undefined. So we can
        # convert from bool to mode with not(bool):
        #     True -> not(True) = False = 0 is MODE_ON
        # TODO: keyframe the visibility when there is more then 1 frame
        for obj_path in visibility:
            for frame, is_visible in visibility[obj_path]:
                obj_name = self._get_obj_from_full_path(obj_path)
                obj = lib.get_objects_by_name(obj_name, doc.GetFirstObject())
                if not obj:
                    self.log.error("Object not found: %s", obj_name)
                    continue
                else:
                    obj = obj[0]
                obj.SetEditorMode(not is_visible)
                obj.SetRenderMode(not is_visible)

        # Update start and end frame of document
        doc.SetMinTime(c4d.BaseTime(start_frame, doc.GetFps()))
        doc.SetLoopMinTime(c4d.BaseTime(start_frame, doc.GetFps()))
        if end_frame:
            doc.SetMaxTime(c4d.BaseTime(end_frame, doc.GetFps()))
            doc.SetLoopMaxTime(c4d.BaseTime(end_frame, doc.GetFps()))

        # Update start and end frame in the render settings and use manual framerange
        render_data = doc.GetActiveRenderData()
        render_data[c4d.RDATA_FRAMESEQUENCE] = c4d.RDATA_FRAMESEQUENCE_MANUAL
        render_data[c4d.RDATA_FRAMEFROM] = c4d.BaseTime(start_frame, doc.GetFps())
        if end_frame:
            render_data[c4d.RDATA_FRAMETO] = c4d.BaseTime(end_frame, doc.GetFps())

        c4d.EventAdd()

        container = pipeline.containerise(
            name=str(name),
            namespace=str(namespace),
            nodes=nodes,
            context=context,
            loader=str(self.__class__.__name__),
        )

        return container

    def update(self, container, context):
        # TODO: add alembic tags to objects that are added
        # TODO: update visibility
        # loop over all alembic tags and update the file path
        filepath = self.filepath_from_context(context)
        container_node = container["node"]
        for alembic_tag in lib.get_objects_from_container(container_node):
            if alembic_tag.GetTypeName() == "Alembic Morph":
                alembic_tag[c4d.ALEMBIC_MT_PATH] = str(filepath)

        for i, base_container in container_node.GetUserDataContainer():
            if base_container[c4d.DESC_NAME] == "representation":
                container_node[i] = context["representation"]["id"]

        c4d.EventAdd()

    def remove(self, container):
        """Remove all sub containers"""
        container_node = container["node"]
        for obj in lib.get_objects_from_container(container_node):
            obj.Remove()
        container_node.Remove()
        c4d.EventAdd()
