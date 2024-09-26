import pyblish.api
from ayon_core.pipeline import registered_host


class SaveCurrentScene(pyblish.api.ContextPlugin):
    """Save current scene"""

    label = "Save current file"
    order = pyblish.api.ExtractorOrder - 0.49
    hosts = ["cinema4d"]

    def process(self, context):

        host = registered_host()
        assert context.data['currentFile'] == host.current_file()

        # If file has no modifications, skip forcing a file save
        if not host.has_unsaved_changes():
            self.log.debug("Skipping file save as there "
                           "are no modifications..")
            return

        self.log.info("Saving current file..")
        host.save_file()
