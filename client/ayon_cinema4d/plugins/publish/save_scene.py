import os
import pyblish.api
import c4d


def get_document_path(doc: c4d.documents.BaseDocument):
    doc_root = doc.GetDocumentPath()
    doc_name = doc.GetDocumentName()
    if doc_root and doc_name:
        return os.path.join(doc_root, doc_name)
    return


class SaveCurrentScene(pyblish.api.ContextPlugin):
    """Save current scene"""

    label = "Save current file"
    order = pyblish.api.ExtractorOrder - 0.49
    hosts = ["cinema4d"]

    def process(self, context):

        doc: c4d.documents.BaseDocument = context.data["doc"]
        # If file has no modifications, skip forcing a file save
        if not doc.GetChanged():
            self.log.debug("Skipping file save as there "
                           "are no unsaved changes..")
            return

        current_file = get_document_path(doc)
        assert context.data['currentFile'] == current_file

        self.log.debug(f"Saving current file: {current_file}")
        c4d.documents.SaveDocument(
            doc, current_file,
            saveflags=c4d.SAVEDOCUMENTFLAGS_NONE,
            format=c4d.FORMAT_C4DEXPORT
        )
