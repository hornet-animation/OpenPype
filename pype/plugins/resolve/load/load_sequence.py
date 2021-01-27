from avalon import io, api
from pype.hosts import resolve


class LoadClip(resolve.SequenceLoader):
    """Load a subset to timeline as clip

    Place clip to timeline on its asset origin timings collected
    during conforming to project
    """

    families = ["render2d", "source", "plate", "render", "review"]
    representations = ["exr", "dpx", "jpg", "jpeg", "png", "h264"]

    label = "Load as clip"
    order = -10
    icon = "code-fork"
    color = "orange"

    # for loader multiselection
    timeline = None

    # presets
    clip_color_last = "Olive"
    clip_color = "Orange"

    def load(self, context, name, namespace, options):

        # in case loader uses multiselection
        if self.timeline:
            options.update({
                "timeline": self.timeline,
            })

        # load clip to timeline and get main variables
        timeline_item = resolve.plugin.ClipLoader(
            self, context, **options).load()
        namespace = namespace or timeline_item.GetName()
        version = context['version']
        version_data = version.get("data", {})
        version_name = version.get("name", None)
        colorspace = version_data.get("colorspace", None)
        object_name = "{}_{}".format(name, namespace)

        # add additional metadata from the version to imprint Avalon knob
        add_keys = [
            "frameStart", "frameEnd", "source", "author",
            "fps", "handleStart", "handleEnd"
        ]

        # move all version data keys to tag data
        data_imprint = {}
        for key in add_keys:
            data_imprint.update({
                key: version_data.get(key, str(None))
            })

        # add variables related to version context
        data_imprint.update({
            "version": version_name,
            "colorspace": colorspace,
            "objectName": object_name
        })

        # update color of clip regarding the version order
        self.set_item_color(timeline_item, version)

        self.log.info("Loader done: `{}`".format(name))

        return resolve.containerise(
            timeline_item,
            name, namespace, context,
            self.__class__.__name__,
            data_imprint)

    def switch(self, container, representation):
        self.update(container, representation)

    def update(self, container, representation):
        """ Updating previously loaded clips
        """

        # load clip to timeline and get main variables
        name = container['name']
        namespace = container['namespace']
        timeline_item = resolve.lib.get_pype_track_item_by_name(namespace)
        version = io.find_one({
            "type": "version",
            "_id": representation["parent"]
        })
        version_data = version.get("data", {})
        version_name = version.get("name", None)
        colorspace = version_data.get("colorspace", None)
        object_name = "{}_{}".format(name, namespace)
        file = api.get_representation_path(representation).replace("\\", "/")

        # TODO: implement update
        # # reconnect media to new path
        # track_item.source().reconnectMedia(file)
        #
        # # add additional metadata from the version to imprint Avalon knob
        # add_keys = [
        #     "frameStart", "frameEnd", "source", "author",
        #     "fps", "handleStart", "handleEnd"
        # ]
        #
        # # move all version data keys to tag data
        # data_imprint = {}
        # for key in add_keys:
        #     data_imprint.update({
        #         key: version_data.get(key, str(None))
        #     })
        #
        # # add variables related to version context
        # data_imprint.update({
        #     "representation": str(representation["_id"]),
        #     "version": version_name,
        #     "colorspace": colorspace,
        #     "objectName": object_name
        # })
        #
        # # update color of clip regarding the version order
        # self.set_item_color(timeline_item, version)
        #
        # return resolve.set_track_item_pype_tag(timeline_item, data_imprint)

    @classmethod
    def set_item_color(cls, timeline_item, version):

        # define version name
        version_name = version.get("name", None)
        # get all versions in list
        versions = io.find({
            "type": "version",
            "parent": version["parent"]
        }).distinct('name')

        max_version = max(versions)

        # set clip colour
        if version_name == max_version:
            timeline_item.SetClipColor(cls.clip_color_last)
        else:
            timeline_item.SetClipColor(cls.clip_color)
