import os
from urllib.parse import unquote, urlparse

import opentimelineio as otio
from bson import json_util

import pyblish.api
from pype import lib
from avalon import io


class OTIO_View(pyblish.api.Action):
    """Currently disabled because OTIO requires PySide2. Issue on Qt.py:
    https://github.com/PixarAnimationStudios/OpenTimelineIO/issues/289
    """

    label = "OTIO View"
    icon = "wrench"
    on = "failed"

    def process(self, context, plugin):
        instance = context[0]
        representation = instance.data["representations"][0]
        file_path = os.path.join(
            representation["stagingDir"], representation["files"]
        )
        lib._subprocess(["otioview", file_path])


class CollectShots(pyblish.api.InstancePlugin):
    """Collect Anatomy object into Context"""

    order = pyblish.api.CollectorOrder
    label = "Collect Shots"
    hosts = ["standalonepublisher"]
    families = ["editorial"]
    actions = []

    def process(self, instance):
        representation = instance.data["representations"][0]
        file_path = os.path.join(
            representation["stagingDir"], representation["files"]
        )
        timeline = otio.adapters.read_from_file(file_path)
        tracks = timeline.each_child(
            descended_from_type=otio.schema.track.Track
        )
        asset_entity = instance.context.data["assetEntity"]
        asset_name = asset_entity["name"]

        # Project specific prefix naming. This needs to be replaced with some
        # options to be more flexible.
        asset_name = asset_name.split("_")[0]

        shot_number = 10
        for track in tracks:
            self.log.info(track)

            if "audio" in track.name.lower():
                continue

            instances = []
            for child in track.each_child():
                parse = urlparse(child.media_reference.target_url)

                # XML files from NukeStudio has extra "/" at the front of path.
                path = os.path.normpath(
                    os.path.abspath(unquote(parse.path)[1:])
                )

                frame_start = child.range_in_parent().start_time.value
                frame_end = child.range_in_parent().end_time_inclusive().value

                name = f"{asset_name}_sh{shot_number:04}"
                label = f"{name} (framerange: {frame_start}-{frame_end})"
                instances.append(
                    instance.context.create_instance(**{
                        "name": name,
                        "label": label,
                        "path": path,
                        "frameStart": frame_start,
                        "frameEnd": frame_end,
                        "family": "shot",
                        "asset": name,
                        "subset": "shotMain"
                    })
                )

                shot_number += 10

        visual_hierarchy = [asset_entity]
        while True:
            visual_parent = io.find_one(
                {"_id": visual_hierarchy[-1]["data"]["visualParent"]}
            )
            if visual_parent:
                visual_hierarchy.append(visual_parent)
            else:
                visual_hierarchy.append(instance.context.data["projectEntity"])
                break

        context_hierarchy = None
        for entity in visual_hierarchy:
            childs = {}
            if context_hierarchy:
                name = context_hierarchy.pop("name")
                childs = {name: context_hierarchy}
            else:
                for instance in instances:
                    childs[instance.data["name"]] = {
                        "childs": {}, "entity_type": "Shot"
                    }

            context_hierarchy = {
                "entity_type": entity["data"]["entityType"],
                "childs": childs,
                "name": entity["name"]
            }

        name = context_hierarchy.pop("name")
        context_hierarchy = {name: context_hierarchy}
        instance.context.data["hierarchyContext"] = context_hierarchy
        self.log.info(
            json_util.dumps(context_hierarchy, sort_keys=True, indent=4)
        )
