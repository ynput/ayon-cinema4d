from ayon_server.settings import BaseSettingsModel, SettingsField

from .imageio import Cinema4DImageIOModel

DEFAULT_VALUES = {
    "imageio": {
        "activate_host_color_management": True,
        "file_rules": {
            "enabled": False,
            "rules": []
        }
    },
}


class Cinema4DSettings(BaseSettingsModel):
    imageio: Cinema4DImageIOModel = SettingsField(
        default_factory=Cinema4DImageIOModel,
        title="Color Management (ImageIO)"
    )
