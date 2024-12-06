import c4d

from ayon_cinema4d.api import plugin


class RedshiftProxyLoader(plugin.Cinema4DSingleObjLoader):
    """Load Redshift Proxy."""

    color = "orange"
    product_types = {"*"}
    icon = "code-fork"
    label = "Load Redshift Proxy"
    order = -10
    representations = {"rs"}

    # TODO: Automatically enable 'animation' on the redshift proxy with
    #  the correct frame start / frame end and offsets so it plays at the
    #  same frames as the source scene.

    @property
    def _node_type_id(self):
        return 1038649  # Redshift Proxy ID

    @property
    def _filepath_attribute(self):
        return c4d.REDSHIFT_PROXY_FILE, c4d.REDSHIFT_FILE_PATH
