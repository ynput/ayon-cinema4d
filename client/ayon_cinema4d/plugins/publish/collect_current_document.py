import pyblish.api
import c4d.documents


class CollectCinema4DActiveDocument(pyblish.api.ContextPlugin):
    """Inject the c4d.documents.GetActiveDocument() into context"""

    order = pyblish.api.CollectorOrder - 0.5
    label = "Cinema4D Active Docuemnt"
    hosts = ['cinema4d']

    def process(self, context):
        context.data['doc'] = c4d.documents.GetActiveDocument()
