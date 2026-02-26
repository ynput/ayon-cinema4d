from ayon_server.settings import BaseSettingsModel, SettingsField


class ProductTypeItemModel(BaseSettingsModel):
    _layout = "compact"
    product_type: str = SettingsField(
        title="Product type",
        description="Product type name"
    )
    label: str = SettingsField(
        "",
        title="Label",
        description="Label to show in UI for the product type"
    )


class BaseCreatePluginModel(BaseSettingsModel):
    product_type_items: list[ProductTypeItemModel] = SettingsField(
        default_factory=list,
        title="Product type items",
        description=(
            "Optional list of product types this plugin can create. "
        ),
    )


class CreatePluginsModel(BaseSettingsModel):
    RenderlayerCreator: BaseCreatePluginModel = SettingsField(
        title="Create Render",
        default_factory=BaseCreatePluginModel,
    )
    CreateCamera: BaseCreatePluginModel = SettingsField(
        title="Create Camera",
        default_factory=BaseCreatePluginModel,
    )
    CreatePointcache: BaseCreatePluginModel = SettingsField(
        title="Create Pointcache",
        default_factory=BaseCreatePluginModel,
    )
    CreateRedshiftProxy: BaseCreatePluginModel = SettingsField(
        title="Create Redshift Proxy",
        default_factory=BaseCreatePluginModel,
    )
