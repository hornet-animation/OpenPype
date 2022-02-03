import pyblish.api


class CollectExampleAddon(pyblish.api.ContextPlugin):
    order = pyblish.api.CollectorOrder + 0.4
    label = "Collect Kitsu"

    def process(self, context):
        self.log.info("I'm in Kitsu's plugin!")
