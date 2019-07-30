import os

from pyblish import api


class CollectPlates(api.InstancePlugin):
    """Collect plates from tags.

    Tag is expected to have metadata:
        {
            "family": "plate"
            "subset": "main"
        }
    """

    # Run just before CollectSubsets
    order = api.CollectorOrder + 0.1025
    label = "Collect Plates"
    hosts = ["nukestudio"]
    families = ["clip"]

    def process(self, instance):
        # Exclude non-tagged instances.
        tagged = False
        for tag in instance.data["tags"]:
            family = dict(tag["metadata"]).get("tag.family", "")
            if family.lower() == "plate":
                tagged = True
                break

        if not tagged:
            self.log.debug(
                "Skipping \"{}\" because its not tagged with "
                "\"plate\"".format(instance)
            )
            return

        # Collect data.
        data = {}
        for key, value in instance.data.iteritems():
            data[key] = value

        data["family"] = family.lower()
        data["families"] = ["ftrack"] + instance.data["families"][1:]
        data["source"] = data["sourcePath"]

        subset = ""
        for tag in instance.data["tags"]:
            tag_data = dict(tag["metadata"])
            if "tag.subset" in tag_data:
                subset = tag_data["tag.subset"]
        data["subset"] = data["family"] + subset.title()

        data["name"] = data["subset"] + "_" + data["asset"]

        data["label"] = "{} - {} - ({})".format(
            data['asset'], data["subset"], os.path.splitext(data["sourcePath"])[1]
        )

        # adding SourceResolution if Tag was present
        if instance.data.get("sourceResolution") and instance.data.get("main"):
            item = instance.data["item"]
            width = int(item.source().mediaSource().width())
            height = int(item.source().mediaSource().height())
            self.log.info("Source Width and Height are: `{0} x {1}`".format(
                width, height))
            data.update({
                "width": width,
                "height": height
            })

        self.log.debug("Creating instance with name: {}".format(data["name"]))
        instance.context.create_instance(**data)

        # # remove original instance
        # instance.context.remove(instance)


class CollectPlatesData(api.InstancePlugin):
    """Collect plates"""

    order = api.CollectorOrder + 0.495
    label = "Collect Plates Data"
    hosts = ["nukestudio"]
    families = ["plate"]

    def process(self, instance):
        import os
        if "review" in instance.data.get("track", ""):
            self.log.debug(
                "Skipping \"{}\" because its `review` track "
                "\"plate\"".format(instance)
            )
            return

        # add to representations
        if not instance.data.get("representations"):
            instance.data["representations"] = list()

        version_data = dict()
        context = instance.context
        anatomy = context.data.get("anatomy", None)
        padding = int(anatomy.templates['render']['padding'])

        name = instance.data["subset"]
        source_path = instance.data["sourcePath"]
        source_file = os.path.basename(source_path)

        # Filter out "clip" family.
        families = instance.data["families"] + [instance.data["family"]]
        families = list(set(families))
        if "clip" in families:
            families.remove("clip")
        family = families[-1]

        # staging dir creation
        staging_dir = os.path.dirname(
            source_path)

        item = instance.data["item"]

        transfer_data = [
            "handleStart", "handleEnd", "sourceIn", "sourceOut", "startFrame", "endFrame", "sourceInH", "sourceOutH", "timelineIn", "timelineOut", "timelineInH", "timelineOutH", "asset", "track", "version"
        ]

        # pass data to version
        version_data.update({k: instance.data[k] for k in transfer_data})

        # add to data of representation
        version_data.update({
            "handles": version_data['handleStart'],
            "colorspace": item.sourceMediaColourTransform(),
            "families": [f for f in families if 'ftrack' not in f],
            "subset": name,
            "fps": instance.context.data["fps"]
        })
        instance.data["versionData"] = version_data

        try:
            basename, ext = os.path.splitext(source_file)
            head, padding = os.path.splitext(basename)
            ext = ext[1:]
            padding = padding[1:]
            # head, padding, ext = source_file.split('.')
            source_first_frame = int(padding)
            padding = len(padding)
            file = "{head}.%0{padding}d.{ext}".format(
                head=head,
                padding=padding,
                ext=ext
            )

            start_frame = source_first_frame + instance.data["sourceInH"]
            duration = instance.data["sourceOutH"] - instance.data["sourceInH"]
            end_frame = start_frame + duration
            files = [file % i for i in range(start_frame, (end_frame + 1), 1)]
        except Exception as e:
            self.log.debug("Exception in file: {}".format(e))
            head, ext = os.path.splitext(source_file)
            ext = ext[1:]
            files = source_file
            start_frame = instance.data["sourceInH"]
            end_frame = instance.data["sourceOutH"]

        mov_file = head + ".mov"
        mov_path = os.path.normpath(os.path.join(staging_dir, mov_file))
        if os.path.exists(mov_path):
            # adding mov into the representations
            self.log.debug("__ mov_path: {}".format(mov_path))
            plates_mov_representation = {
                'files': mov_file,
                'stagingDir': staging_dir,
                'startFrame': 0,
                'endFrame': instance.data["sourceOut"] - instance.data["sourceIn"] + 1,
                'step': 1,
                'frameRate': instance.context.data["fps"],
                'preview': True,
                'thumbnail': False,
                'name': "preview",
                'ext': "mov",
            }

            if mov_file not in source_file:
                instance.data["representations"].append(
                    plates_mov_representation)

        thumb_file = head + ".png"
        thumb_path = os.path.join(staging_dir, thumb_file)

        thumbnail = item.thumbnail(instance.data["sourceIn"]).save(
            thumb_path,
            format='png'
        )
        self.log.debug("__ thumbnail: {}".format(thumbnail))

        thumb_representation = {
            'files': thumb_file,
            'stagingDir': staging_dir,
            'name': "thumbnail",
            'thumbnail': True,
            'ext': "png"
        }
        instance.data["representations"].append(
            thumb_representation)

        # adding representation for plates
        plates_representation = {
            'files': files,
            'stagingDir': staging_dir,
            'name': ext,
            'ext': ext,
            'startFrame': instance.data["startFrame"] - instance.data["handleStart"],
            'endFrame': instance.data["endFrame"] + instance.data["handleEnd"],
        }
        instance.data["representations"].append(plates_representation)

        # testing families
        family = instance.data["family"]
        families = instance.data["families"]

        # test prints version_data
        self.log.debug("__ version_data: {}".format(version_data))
        self.log.debug("__ representations: {}".format(
            instance.data["representations"]))
        self.log.debug("__ after family: {}".format(family))
        self.log.debug("__ after families: {}".format(families))
