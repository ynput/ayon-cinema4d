import c4d

from ayon_cinema4d.api import plugin


class LoadVolume(plugin.Cinema4DSingleObjLoader):
    """Load VDB to Volume Loader."""

    color = "orange"
    product_types = {"*"}
    icon = "cloud"
    label = "Load VDB to Volume Loader"
    order = -10
    representations = {"vdb"}

    @property
    def _node_type_id(self) -> int:
        return 1039866  # Volume Loader ID

    @property
    def _filepath_attribute(self):
        return c4d.ID_VOLUMESEQUENCE_PATH
