"""
Requires:
    None
Provides:
    context -> anatomy (pypeapp.Anatomy)
"""

from pypeapp import Anatomy
import pyblish.api


class CollectTemplates(pyblish.api.ContextPlugin):
    """Collect Anatomy into Context"""

    order = pyblish.api.CollectorOrder
    label = "Collect Templates"

    def process(self, context):
        context.data['anatomy'] = Anatomy()
        self.log.info("Anatomy templates collected...")
