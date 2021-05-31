"""Create a model asset."""

import bpy

from avalon import api
from avalon.blender import lib
from avalon.blender.pipeline import AVALON_INSTANCES
from openpype.hosts.blender.api import plugin


class CreateModel(plugin.Creator):
    """Polygonal static geometry"""

    name = "modelMain"
    label = "Model"
    family = "model"
    icon = "cube"

    def process(self):
        # Get Instance Containter or create it if it does not exist
        instances = bpy.data.collections.get(AVALON_INSTANCES)
        if not instances:
            instances = bpy.data.collections.new(name=AVALON_INSTANCES)
            bpy.context.scene.collection.children.link(instances)

        # Create instance object
        asset = self.data["asset"]
        subset = self.data["subset"]
        name = plugin.asset_name(asset, subset)
        asset_group = bpy.data.objects.new(name=name, object_data=None)
        instances.objects.link(asset_group)
        self.data['task'] = api.Session.get('AVALON_TASK')
        lib.imprint(asset_group, self.data)

        # Add selected objects to instance
        if (self.options or {}).get("useSelection"):
            bpy.context.view_layer.objects.active = asset_group
            selected = lib.get_selection()
            for obj in selected:
                obj.select_set(True)
            selected.append(asset_group)
            context = plugin.create_blender_context(
                active=asset_group, selected=selected)
            bpy.ops.object.parent_set(context, keep_transform=True)

        return asset_group
