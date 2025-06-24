from pydantic import validator
from ayon_server.settings import BaseSettingsModel, SettingsField
from ayon_server.settings.validators import ensure_unique_names


class ImageIOFileRuleModel(BaseSettingsModel):
    name: str = SettingsField("", title="Rule name")
    pattern: str = SettingsField("", title="Regex pattern")
    colorspace: str = SettingsField("", title="Colorspace name")
    ext: str = SettingsField("", title="File extension")


class ImageIOFileRulesModel(BaseSettingsModel):
    activate_host_rules: bool = SettingsField(False)
    rules: list[ImageIOFileRuleModel] = SettingsField(
        default_factory=list,
        title="Rules"
    )

    @validator("rules")
    def validate_unique_outputs(cls, value):
        ensure_unique_names(value)
        return value


class WorkfileImageIOModel(BaseSettingsModel):
    """Workfile settings help.

    Empty values will be skipped, allowing any existing env vars to
    pass through as defined.

    Note: The render space in Houdini is
    always set to the 'scene_linear' role."""

    enabled: bool = SettingsField(False, title="Enabled")
    render: str = SettingsField(
        default="ACES",
        title="Default render space",
        description="It behaves like the 'OCIO_RENDER_SPACE' env var,"
                    " The role of the working space, e.g scene_linear"
    )
    display: str = SettingsField(
        default="ACES",
        title="Default active displays",
        description="It behaves like the 'OCIO_ACTIVE_DISPLAYS' env var,"
                    " Colon-separated list of displays, e.g ACES:P3"
    )
    view: str = SettingsField(
        default="sRGB",
        title="Default active views",
        description="It behaves like the 'OCIO_ACTIVE_VIEWS' env var,"
                    " Colon-separated list of views, e.g sRGB:DCDM"
    )
    thumbnails: str = SettingsField(
        default="sRGB",
        title="Thumbnails",
    )


class Cinema4DImageIOModel(BaseSettingsModel):
    activate_host_color_management: bool = SettingsField(
        True, title="Enable Color Management"
    )
    file_rules: ImageIOFileRulesModel = SettingsField(
        default_factory=ImageIOFileRulesModel,
        title="File Rules"
    )
    workfile: WorkfileImageIOModel = SettingsField(
        default_factory=WorkfileImageIOModel,
        title="Workfile Color Management",
        description="Set workfile OCIO display/view."
    )


DEFAULT_IMAGEIO_SETTINGS = {
    "activate_host_color_management": True,
    "file_rules": {
        "activate_host_rules": False,
        "rules": []
    },
    "workfile": {
        "enabled": False,
        "render": "ACES",
        "display": "ACES",
        "view": "sRGB",
        "thumbnails": "sRGB",
    }
}
