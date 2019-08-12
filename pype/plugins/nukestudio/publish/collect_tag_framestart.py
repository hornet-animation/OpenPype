from pyblish import api


class CollectClipTagFrameStart(api.InstancePlugin):
    """Collect FrameStart from Tags of selected track items."""

    order = api.CollectorOrder + 0.013
    label = "Collect Frame Start"
    hosts = ["nukestudio"]
    families = ['clip']

    def process(self, instance):
        # gets tags
        tags = instance.data["tags"]

        for t in tags:
            t_metadata = dict(t["metadata"])
            t_family = t_metadata.get("tag.family", "")

            # gets only task family tags and collect labels
            if "frameStart" in t_family:
                t_number = t_metadata.get("tag.number", "")
                start_frame = int(t_number)
                instance.data["startingFrame"] = start_frame
                self.log.info("Start frame on `{0}` set to `{1}`".format(
                    instance, start_frame
                    ))
