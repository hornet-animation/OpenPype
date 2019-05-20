
import pype.api as pype
from pypeapp import Anatomy

import pyblish.api


class CollectTemplates(pyblish.api.ContextPlugin):
    """Inject the current working file into context"""

    order = pyblish.api.CollectorOrder
    label = "Collect Templates"

    def process(self, context):
        # pype.load_data_from_templates()
        context.data['anatomy'] = Anatomy()
        self.log.info("Anatomy templates collected...")
