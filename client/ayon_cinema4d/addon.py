import os
from ayon_core.addon import AYONAddon, IHostAddon, IPluginPaths

from .version import __version__

CINEMA4D_ADDON_ROOT = os.path.dirname(os.path.abspath(__file__))


class Cinema4DAddon(AYONAddon, IHostAddon, IPluginPaths):
    name = "cinema4d"
    version = __version__
    host_name = "cinema4d"

    def get_publish_plugin_paths(self, host_name):
        """Publish plugins that run without Cinema 4D.

        Registered in the Cinema 4D session and in the Deadline publish job,
        which runs `AYON_HOST_NAME` = cinema4d without the application. The
        plugins must not import `c4d` or `ayon_cinema4d.api`.
        """
        if host_name != self.host_name:
            return []
        return [
            os.path.join(CINEMA4D_ADDON_ROOT, "plugins", "publish_shared")
        ]

    def get_launch_hook_paths(self, app):
        if app.host_name != self.host_name:
            return []
        return [os.path.join(CINEMA4D_ADDON_ROOT, "hooks")]

    def add_implementation_envs(self, env, app):
        # Set default values if are not already set via settings
        defaults = {"AYON_LOG_NO_COLORS": "1"}
        for key, value in defaults.items():
            if not env.get(key):
                env[key] = value

        # Register the startup `ayon_cinema4d.pyp`
        startup_path = os.path.join(CINEMA4D_ADDON_ROOT, "startup")
        new_g_module_path = [startup_path]

        path_key = "g_additionalModulePath"
        if os.name == "nt":
            path_key = path_key.upper()

        old_g_module_path = env.get(path_key) or ""
        for path in old_g_module_path.split(os.pathsep):
            if not path:
                continue

            norm_path = os.path.normpath(path)
            if norm_path not in new_g_module_path:
                new_g_module_path.append(norm_path)

        env[path_key] = os.pathsep.join(new_g_module_path)

    def get_workfile_extensions(self):
        return [".c4d"]
