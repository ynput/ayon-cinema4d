from ayon_server.settings import BaseSettingsModel, SettingsField


class BasicEnabledStatesModel(BaseSettingsModel):
    enabled: bool = SettingsField(
        title="Enabled", description="Whether the plug-in is enabled"
    )
    optional: bool = SettingsField(
        title="Optional",
        description=(
            "If the plug-in is enabled, this defines whether it can be "
            "activated or deactivated by the artist in the publisher UI."
        ),
    )
    active: bool = SettingsField(
        title="Active",
        description=(
            "If the plug-in is optional, this defines the default "
            "enabled state."
        ),
    )


class PublishPluginsModel(BaseSettingsModel):
    # Frame range and resolution validators
    ValidateFrameRange: BasicEnabledStatesModel = SettingsField(
        default_factory=BasicEnabledStatesModel,
        title="Validate Frame Range",
        description=(
            "Validate the publish frame range matches AYON task entity."
        )
    )
    ValidateResolution: BasicEnabledStatesModel = SettingsField(
        default_factory=BasicEnabledStatesModel,
        title="Validate Resolution.",
        description=(
            "Validate publish resolution matches AYON task entity."
        )
    )


DEFAULT_PUBLISH_SETTINGS = {
    "ValidateFrameRange": {
        "enabled": True,
        "optional": True,
        "active": True,
    },
    "ValidateResolution": {
        "enabled": True,
        "optional": True,
        "active": True,
    },
}
