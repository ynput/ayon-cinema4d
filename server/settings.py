from ayon_server.settings import BaseSettingsModel, SettingsField

from .imageio import DEFAULT_IMAGEIO_SETTINGS, Cinema4DImageIOModel
from .create import CreatePluginsModel
from .publish import DEFAULT_PUBLISH_SETTINGS, PublishPluginsModel

DEFAULT_VALUES = {
    "imageio": DEFAULT_IMAGEIO_SETTINGS,
    "publish": DEFAULT_PUBLISH_SETTINGS,
}


class Cinema4DSettings(BaseSettingsModel):
    imageio: Cinema4DImageIOModel = SettingsField(
        default_factory=Cinema4DImageIOModel,
        title="Color Management (ImageIO)"
    )
    create: CreatePluginsModel = SettingsField(
        default_factory=CreatePluginsModel,
        title="Create plugins",
    )
    publish: PublishPluginsModel = SettingsField(
        default_factory=PublishPluginsModel,
        title="Publish plugins",
    )
