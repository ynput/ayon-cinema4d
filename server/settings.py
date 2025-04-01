from ayon_server.settings import BaseSettingsModel, SettingsField

from .imageio import Cinema4DImageIOModel
from .publish import DEFAULT_PUBLISH_SETTINGS, PublishPluginsModel

DEFAULT_VALUES = {
    "imageio": {
        "activate_host_color_management": True,
        "file_rules": {
            "enabled": False,
            "rules": []
        }
    },
    "publish": DEFAULT_PUBLISH_SETTINGS,
}


class Cinema4DSettings(BaseSettingsModel):
    imageio: Cinema4DImageIOModel = SettingsField(
        default_factory=Cinema4DImageIOModel,
        title="Color Management (ImageIO)"
    )
    publish: PublishPluginsModel = SettingsField(
        default_factory=PublishPluginsModel, title="Publish plugins"
    )
