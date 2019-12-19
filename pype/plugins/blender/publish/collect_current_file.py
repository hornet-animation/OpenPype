import bpy

import pyblish.api


class CollectBlenderCurrentFile(pyblish.api.ContextPlugin):
    """Inject the current working file into context"""

    order = pyblish.api.CollectorOrder - 0.5
    label = "Blender Current File"
    hosts = ['blender']

    def process(self, context):
        """Inject the current working file"""
        current_file = bpy.context.blend_data.filepath
        context.data['currentFile'] = current_file
