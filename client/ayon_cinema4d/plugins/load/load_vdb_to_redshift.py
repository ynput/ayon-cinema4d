import c4d

from ayon_cinema4d.api import plugin


class LoadVDBToRedshift(plugin.Cinema4DSingleObjLoader):
    """Load VDB to Redshift Volume."""

    color = "orange"
    product_types = {"*"}
    icon = "cloud"
    label = "Load VDB to Redshift"
    order = -10
    representations = {"vdb"}

    # TODO: Automatically set Animation to "Frame" when loading a vdb sequence
    #  and correctly set the start frame, end frame and offsets

    @property
    def _node_type_id(self) -> int:
        return 1038655  # Redshift Volume ID

    @property
    def _filepath_attribute(self):
        return c4d.REDSHIFT_VOLUME_FILE, c4d.REDSHIFT_FILE_PATH
