import pyblish.api
from ayon_cinema4d import api


class CollectCinema4DCurrentFile(pyblish.api.ContextPlugin):
    """Inject the current working file into context"""

    order = pyblish.api.CollectorOrder - 0.5
    label = "Cinema4D Current File"
    hosts = ["cinema4d"]

    def process(self, context):
        """Inject the current working file"""

        current_file = api.current_file()
        context.data['currentFile'] = current_file
        if not current_file:
            self.log.warning(
                "Current file is not saved. Save the file before continuing."
            )
