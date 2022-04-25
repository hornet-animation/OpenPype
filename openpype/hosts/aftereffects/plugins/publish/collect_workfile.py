import os

import pyblish.api
from openpype.lib import get_subset_name_with_asset_doc


class CollectWorkfile(pyblish.api.ContextPlugin):
    """ Adds the AE render instances """

    label = "Collect After Effects Workfile Instance"
    order = pyblish.api.CollectorOrder + 0.1

    def process(self, context):
        existing_instance = None
        for instance in context:
            if instance.data["family"] == "workfile":
                self.log.debug("Workfile instance found, won't create new")
                existing_instance = instance
                break

        current_file = context.data["currentFile"]
        staging_dir = os.path.dirname(current_file)
        scene_file = os.path.basename(current_file)
        if existing_instance is None:  # old publish
            instance = self._get_new_instance(context, scene_file)
        else:
            instance = existing_instance

        # creating representation
        representation = {
            'name': 'aep',
            'ext': 'aep',
            'files': scene_file,
            "stagingDir": staging_dir,
        }

        if not instance.data.get("representations"):
            instance.data["representations"] = []
        instance.data["representations"].append(representation)

        instance.data["publish"] = instance.data["active"]  # for DL

    def _get_new_instance(self, context, scene_file):
        task = api.Session["AVALON_TASK"]
        version = context.data["version"]
        asset_entity = context.data["assetEntity"]
        project_entity = context.data["projectEntity"]

        instance_data = {
            "active": True,
            "asset": asset_entity["name"],
            "task": task,
            "frameStart": asset_entity["data"]["frameStart"],
            "frameEnd": asset_entity["data"]["frameEnd"],
            "handleStart": asset_entity["data"]["handleStart"],
            "handleEnd": asset_entity["data"]["handleEnd"],
            "fps": asset_entity["data"]["fps"],
            "resolutionWidth": asset_entity["data"].get(
                "resolutionWidth",
                project_entity["data"]["resolutionWidth"]),
            "resolutionHeight": asset_entity["data"].get(
                "resolutionHeight",
                project_entity["data"]["resolutionHeight"]),
            "pixelAspect": 1,
            "step": 1,
            "version": version
        }

        # workfile instance
        family = "workfile"
        subset = get_subset_name_with_asset_doc(
            family,
            "",
            context.data["anatomyData"]["task"]["name"],
            context.data["assetEntity"],
            context.data["anatomyData"]["project"]["name"],
            host_name=context.data["hostName"]
        )
        # Create instance
        instance = context.create_instance(subset)

        # creating instance data
        instance.data.update({
            "subset": subset,
            "label": scene_file,
            "family": family,
            "families": [family],
            "representations": list()
        })

        instance.data.update(instance_data)

        return instance
