"""JPEG sequence and Multi-Pass contact sheet of a Cinema 4D render.

These extractors run in the Cinema 4D session for local renders and in the
Deadline publish job for farm renders, so they must not import `c4d` or
`ayon_cinema4d.api`. See `Cinema4DAddon.get_publish_plugin_paths`.
"""
import functools
import math
import os
import shutil

import clique
import pyblish.api

from ayon_core.lib import get_oiio_tool_args, run_subprocess
from ayon_core.lib.transcoding import (
    get_oiio_info_for_input,
    get_review_info_by_layer_name,
)
from ayon_core.pipeline import get_temp_dir
from ayon_core.pipeline.publish.lib import add_repre_files_for_cleanup

# `plugin.LOCAL_RENDER_FAMILY` is not importable without Cinema 4D
RENDER_FAMILIES = ["render", "render.local.c4d"]
MULTIPASS_NAME = "multipass"
CONTACT_SHEET_NAME = "contactsheet"
# Fallbacks for cinema4d/render_settings
DEFAULT_SETTINGS = {
    "jpeg_sequence": True,
    "contact_sheet": True,
    "contact_sheet_columns": 0,
    "contact_sheet_tile_width": 640,
}


class RenderOutputPlugin:
    """Shared oiiotool helpers, a mixin so it isn't discovered itself."""

    families = RENDER_FAMILIES
    settings_category = "cinema4d"
    # Local renders publish in Cinema 4D, farm renders in the publish job
    targets = ["local", "farm"]

    @staticmethod
    def is_render_product(instance):
        """Only the render product itself, not its separate AOV products."""
        return bool(
            instance.data.get("representations")
            and not instance.data.get("aov")
        )

    @staticmethod
    def get_settings(instance):
        settings = dict(DEFAULT_SETTINGS)
        project_settings = instance.context.data.get("project_settings") or {}
        settings.update(
            project_settings.get("cinema4d", {}).get("render_settings") or {}
        )
        return settings

    @staticmethod
    def get_image_repres(instance):
        """Return the rendered image representations to convert from."""
        return [
            repre
            for repre in instance.data.get("representations") or []
            if repre.get("files")
            and "delete" not in (repre.get("tags") or [])
            and repre.get("ext", "").lower() in {"exr", "png", "tif", "tiff"}
        ]

    def get_source_repre(self, instance, name=None):
        """Return the representation with `name`, else the first image one.

        Without a regular image the Multi-Layer file is the rendered
        sequence itself, so the first one is the fallback for `multipass`.
        """
        repres = self.get_image_repres(instance)
        if name:
            for repre in repres:
                if repre.get("name") == name:
                    return repre
        return repres[0] if repres else None

    @staticmethod
    def iter_frames(repre):
        """Yield (frame, filename, padding) of a representation."""
        files = repre["files"]
        if isinstance(files, str):
            return [(None, files, 0)]

        collections, remainder = clique.assemble(files, minimum_items=1)
        if not collections:
            return [(None, name, 0) for name in remainder]

        # Other numbers in the name (a version) make more collections, the
        # frames are the last numbers shared by all files
        collection = max(
            collections, key=lambda item: (len(item.indexes), len(item.head))
        )
        indexes = sorted(collection.indexes)
        padding = collection.padding or len(str(indexes[-1]))
        return list(zip(indexes, list(collection), [padding] * len(indexes)))

    # Fallback with the OIIO built-in color config, writing linear values
    # into an 8 bit file would give a nearly black image
    BUILTIN_COLOR_ARGS = ["--colorconvert", "linear", "sRGB"]

    @classmethod
    def get_color_args(cls, repre):
        """Return (config args, display referred conversion args)."""
        data = repre.get("colorspaceData") or {}
        config = (data.get("config") or {}).get("path")
        colorspace = data.get("colorspace")
        display = data.get("display")
        view = data.get("view")

        if config and colorspace and display and view:
            return (
                ["--colorconfig", config],
                ["--iscolorspace", colorspace,
                 "--ociodisplay", display, view],
            )
        if config and colorspace:
            return (
                ["--colorconfig", config],
                ["--colorconvert", colorspace, "sRGB"],
            )
        return [], list(cls.BUILTIN_COLOR_ARGS)

    @staticmethod
    def get_input_args(layers):
        """Return the oiiotool arguments needed to read all passes.

        Subimages are only loaded with `-a`, without it oiiotool reads the
        first subimage of a file.
        """
        if any(layer["subimage"] for layer in layers):
            return ["-a"]
        return []

    def get_layers(self, filepath):
        """Return the reviewable layers of an image as list of dicts.

        Each layer has a `name`, its `subimage` index and the `channels` to
        read it with. Multi-Layer files store the passes either as channel
        groups or as subimages, both are supported.
        """
        infos = get_oiio_info_for_input(
            filepath, subimages=True, logger=self.log
        )
        layers = []
        for index, info in enumerate(infos):
            subimage_name = (info.get("attribs") or {}).get(
                "oiio:subimagename"
            )
            for layer in get_review_info_by_layer_name(
                info.get("channelnames") or []
            ):
                channels = layer["review_channels"]
                layers.append({
                    "name": layer["name"] or subimage_name or "rgba",
                    "subimage": index,
                    "channels": (
                        channels["R"], channels["G"], channels["B"]
                    ),
                    "width": info.get("width"),
                    "height": info.get("height"),
                })
        return layers

    def run_oiiotool(self, build, levels, state):
        """Run oiiotool, dropping optional arguments on failure.

        `build(**level)` returns the command for a level, the levels are
        tried in order until one works. Color management and the labels are
        optional, an OCIO config or font that oiiotool can't read must not
        cost the whole sequence. The working level is kept in `state` for
        the next frames.
        """
        for index in range(state.get("level", 0), len(levels)):
            try:
                run_subprocess(build(**levels[index]), logger=self.log)
                state["level"] = index
                return True
            except Exception as exc:
                self.log.warning(
                    "oiiotool failed with {}: {}".format(levels[index], exc)
                )
        return False

    def create_staging_dir(self, instance, suffix):
        return get_temp_dir(
            instance.context.data["projectName"],
            anatomy=instance.context.data["anatomy"],
            prefix=f"c4d_{suffix}_",
            use_local_temp=True,
        )

    def add_representation(self, instance, repre, review=False):
        instance.data.setdefault("representations", []).append(repre)
        add_repre_files_for_cleanup(instance, repre)
        if review:
            # `ExtractReview` matches on the instance, not the representation
            families = instance.data.setdefault("families", [])
            if "review" not in families:
                families.append("review")
            instance.data["review"] = True
        self.log.info(
            "Added representation '{}' with {} file(s).".format(
                repre["name"],
                1 if isinstance(repre["files"], str) else len(repre["files"]),
            )
        )

    @staticmethod
    def discard_staging_dir(staging_dir):
        """Remove the output of a failed conversion."""
        shutil.rmtree(staging_dir, ignore_errors=True)


class ExtractRenderJpegSequence(RenderOutputPlugin,
                                pyblish.api.InstancePlugin):
    """Convert the rendered frames to a display referred JPEG sequence.

    Published next to the rendered sequence as `jpg` representation, so the
    frames can be viewed without an EXR viewer.
    """

    label = "Extract Render JPEG Sequence"
    # Before `ExtractReview`
    order = pyblish.api.ExtractorOrder + 0.01

    def process(self, instance):
        if not self.is_render_product(instance):
            return
        if not self.get_settings(instance)["jpeg_sequence"]:
            return

        repre = self.get_source_repre(instance)
        if repre is None:
            self.log.debug("No rendered sequence found.")
            return

        staging_dir = self.create_staging_dir(instance, "jpg")
        source_dir = repre["stagingDir"]
        config_args, color_args = self.get_color_args(repre)
        frames = self.iter_frames(repre)
        input_args, channel_args = self.get_channel_args(
            os.path.join(source_dir, frames[0][1])
        )

        def build(source, output, config):
            args = get_oiio_tool_args("oiiotool")
            args.extend(config_args if config else [])
            args.extend(input_args)
            args.extend(["-i", source])
            args.extend(channel_args)
            args.extend(color_args if config else self.BUILTIN_COLOR_ARGS)
            args.extend(["-d", "uint8", "-o", output])
            return args

        state = {}
        filenames = []
        for frame, filename, padding in frames:
            output = self.get_output_name(instance, frame, padding)
            built = functools.partial(
                build,
                os.path.join(source_dir, filename),
                os.path.join(staging_dir, output),
            )
            if not self.run_oiiotool(built, [{"config": True},
                                             {"config": False}], state):
                self.log.warning(f"No JPEG created for '{filename}'.")
                self.discard_staging_dir(staging_dir)
                return
            filenames.append(output)

        self.add_representation(instance, {
            "name": "jpg",
            "ext": "jpg",
            "outputName": "jpg",
            "files": filenames if len(filenames) > 1 else filenames[0],
            "stagingDir": staging_dir,
            "frameStart": repre.get("frameStart"),
            "frameEnd": repre.get("frameEnd"),
            "fps": repre.get("fps") or instance.data.get("fps"),
            "tags": [],
        })

    def get_channel_args(self, filepath):
        """Return (input args, channels) of the first reviewable layer."""
        try:
            layers = self.get_layers(filepath)
        except Exception as exc:
            self.log.warning(f"Could not read layers of '{filepath}': {exc}")
            return [], []
        if not layers:
            return [], []

        layer = layers[0]
        red, green, blue = layer["channels"]
        args = []
        if layer["subimage"]:
            args.extend(["--subimage", str(layer["subimage"])])
        args.extend(["--ch", f"R={red},G={green},B={blue}"])
        return self.get_input_args([layer]), args

    @staticmethod
    def get_output_name(instance, frame, padding):
        name = instance.data["productName"]
        if frame is None:
            return f"{name}.jpg"
        return "{}.{:0{}d}.jpg".format(name, frame, padding)


class ExtractRenderContactSheet(RenderOutputPlugin,
                                pyblish.api.InstancePlugin):
    """Create a labelled contact sheet of all passes for every frame.

    Needs a Multi-Layer file, the passes are read from it with oiiotool and
    put into one grid per frame. Published as JPEG sequence with the `review`
    tag, so AYON also creates a movie from it.
    """

    label = "Extract Render Contact Sheet"
    # Before `ExtractReview`
    order = pyblish.api.ExtractorOrder + 0.015

    def process(self, instance):
        if not self.is_render_product(instance):
            return
        settings = self.get_settings(instance)
        if not settings["contact_sheet"]:
            return

        repre = self.get_source_repre(instance, name=MULTIPASS_NAME)
        if repre is None:
            self.log.debug("No rendered sequence found.")
            return

        source_dir = repre["stagingDir"]
        frames = self.iter_frames(repre)
        first_file = os.path.join(source_dir, frames[0][1])
        try:
            layers = self.get_layers(first_file)
        except Exception as exc:
            self.log.warning(f"Could not read passes of '{first_file}': {exc}")
            return

        if len(layers) < 2:
            self.log.debug(
                "Less than two passes found, no contact sheet created."
                " Enable Multi-Layer File in the render settings to get one."
            )
            return

        columns, rows = self.get_grid(len(layers), settings)
        tile_width, tile_height = self.get_tile_size(
            instance, layers[0], settings
        )
        self.log.debug(
            f"Contact sheet {columns}x{rows} of {len(layers)} passes,"
            f" {tile_width}x{tile_height} per pass."
        )

        staging_dir = self.create_staging_dir(instance, "contactsheet")
        config_args, color_args = self.get_color_args(repre)

        input_args = self.get_input_args(layers)

        def build(source, output, config, text):
            args = get_oiio_tool_args("oiiotool")
            args.extend(config_args if config else [])
            args.extend(input_args)
            # The passes are pushed on the stack in reading order
            for layer in layers:
                args.extend(self.get_tile_args(
                    source, layer, tile_width, tile_height,
                    color_args if config else self.BUILTIN_COLOR_ARGS, text,
                ))
            # `--mosaic` needs an image for every cell of the grid
            for _ in range(columns * rows - len(layers)):
                args.extend(["--create", f"{tile_width}x{tile_height}", "3"])
            args.extend([
                "--mosaic", f"{columns}x{rows}",
                "-d", "uint8", "-o", output,
            ])
            return args

        state = {}
        levels = [
            {"config": True, "text": True},
            {"config": True, "text": False},
            {"config": False, "text": False},
        ]
        filenames = []
        for frame, filename, padding in frames:
            output = self.get_output_name(instance, frame, padding)
            built = functools.partial(
                build,
                os.path.join(source_dir, filename),
                os.path.join(staging_dir, output),
            )
            if not self.run_oiiotool(built, levels, state):
                self.log.warning(f"No contact sheet created for '{filename}'.")
                self.discard_staging_dir(staging_dir)
                return
            filenames.append(output)

        self.add_representation(instance, {
            "name": CONTACT_SHEET_NAME,
            "ext": "jpg",
            "outputName": CONTACT_SHEET_NAME,
            "files": filenames if len(filenames) > 1 else filenames[0],
            "stagingDir": staging_dir,
            "frameStart": repre.get("frameStart"),
            "frameEnd": repre.get("frameEnd"),
            "fps": repre.get("fps") or instance.data.get("fps"),
            # `reformatted` keeps the grid resolution in the movie
            "tags": ["review", "reformatted"],
        }, review=True)

    def get_tile_args(self, filepath, layer, width, height, color_args, text):
        """Return the oiiotool arguments for one pass of the grid."""
        red, green, blue = layer["channels"]
        args = ["-i", filepath]
        if layer["subimage"]:
            args.extend(["--subimage", str(layer["subimage"])])
        args.extend(["--ch", f"R={red},G={green},B={blue}"])
        args.extend(color_args)
        args.extend(["--resize", f"{width}x{height}"])
        if text:
            size = max(12, int(width / 24))
            args.extend([
                "--text:x={}:y={}:size={}:color=1,1,1".format(
                    int(size * 0.5), int(size * 1.6), size
                ),
                layer["name"],
            ])
        return args

    @staticmethod
    def get_grid(count, settings):
        """Return (columns, rows) for the number of passes."""
        columns = int(settings["contact_sheet_columns"] or 0)
        if columns < 1:
            columns = math.ceil(math.sqrt(count))
        columns = min(columns, count)
        return columns, math.ceil(count / columns)

    @staticmethod
    def get_tile_size(instance, layer, settings):
        """Return the pixel size of one pass in the contact sheet."""
        # Even sizes keep the movie encoders happy
        width = max(2, int(settings["contact_sheet_tile_width"]) // 2 * 2)
        source_width = layer.get("width") or instance.data.get(
            "resolutionWidth"
        )
        source_height = layer.get("height") or instance.data.get(
            "resolutionHeight"
        )
        if not source_width or not source_height:
            return width, width
        height = max(2, round(width * source_height / source_width / 2) * 2)
        return width, height

    @staticmethod
    def get_output_name(instance, frame, padding):
        name = "{}_{}".format(instance.data["productName"], CONTACT_SHEET_NAME)
        if frame is None:
            return f"{name}.jpg"
        return "{}.{:0{}d}.jpg".format(name, frame, padding)
