"""Host API required Work Files tool"""
import os
import c4d


def file_extensions():
    return [".c4d"]


def has_unsaved_changes():
    doc = c4d.documents.GetActiveDocument()
    return doc.GetChanged()


def save_file(filepath=None):
    doc = c4d.documents.GetActiveDocument()

    # Cinema4D does not update the current document path and name when
    # you save because the same function is used to export data.
    # If you rename current document after saving then it assumed
    # it has been changed again which we can't seem to disable.
    # So we update the work file path and name beforehand
    doc.SetDocumentPath(os.path.dirname(filepath))
    doc.SetDocumentName(os.path.basename(filepath))

    c4d.CallCommand(12098)  # save
    # return c4d.documents.SaveDocument(doc,
    #                                   filepath,
    #                                   c4d.SAVEDOCUMENTFLAGS_NONE,
    #                                   c4d.FORMAT_C4DEXPORT)


def open_file(filepath):
    return c4d.documents.LoadFile(filepath)


def current_file() -> str:
    doc = c4d.documents.GetActiveDocument()
    doc_root = doc.GetDocumentPath()
    doc_name = doc.GetDocumentName()
    if doc_root and doc_name:
        return os.path.join(doc_root, doc_name)

    return ""
