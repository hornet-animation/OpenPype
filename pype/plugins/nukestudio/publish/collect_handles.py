import json
from pyblish import api


class CollectClipHandles(api.ContextPlugin):
    """Collect Handles from all instanes and add to assetShared."""

    order = api.CollectorOrder + 0.1025
    label = "Collect Handles"
    hosts = ["nukestudio"]

    def process(self, context):
        assets_shared = context.data.get("assetsShared")
        assert assets_shared, "Context data missing `assetsShared` key"

        # find all main types instances and add its handles to asset shared
        instances = context[:]
        filtered_instances = []
        for instance in instances:
            families = instance.data.get("families", [])
            families += [instance.data["family"]]
            if "clip" in families:
                filtered_instances.append(instance)
            else:
                continue

            # get handles
            handles = int(instance.data["handles"])
            handle_start = int(instance.data["handleStart"])
            handle_end = int(instance.data["handleEnd"])

            if instance.data.get("main"):
                name = instance.data["asset"]
                if assets_shared.get(name):
                    self.log.debug("Adding to shared assets: `{}`".format(
                        instance.data["name"]))
                    assets_shared[name].update({
                        "handles": handles,
                        "handleStart": handle_start,
                        "handleEnd": handle_end
                    })

        for instance in filtered_instances:
            if not instance.data.get("main"):
                self.log.debug("Synchronize handles on: `{}`".format(
                    instance.data["name"]))
                name = instance.data["asset"]
                s_asset_data = assets_shared.get(name)
                instance.data["handles"] = s_asset_data.get("handles", 0)
                instance.data["handleStart"] = s_asset_data.get(
                    "handleStart", 0
                )
                instance.data["handleEnd"] = s_asset_data.get("handleEnd", 0)
