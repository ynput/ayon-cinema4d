from typing import Type

from ayon_server.addons import BaseServerAddon

from .settings import Cinema4DSettings, DEFAULT_VALUES


class Cinema4DAddon(BaseServerAddon):
    settings_model: Type[Cinema4DSettings] = Cinema4DSettings

    async def get_default_settings(self):
        settings_model_cls = self.get_settings_model()
        return settings_model_cls(**DEFAULT_VALUES)
