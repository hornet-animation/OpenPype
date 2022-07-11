import os

import pyblish.api
from openpype.pipeline import OpenPypePyblishPluginMixin


class CollectMovBatch(
    pyblish.api.InstancePlugin, OpenPypePyblishPluginMixin
):
    """Collect file url for batch mov and create representation."""

    label = "Collect Mov Batch Files"
    order = pyblish.api.CollectorOrder

    hosts = ["traypublisher"]

    def process(self, instance):
        if not instance.data.get("creator_identifier") == "render_mov_batch":
            return

        file_url = instance.data["creator_attributes"]["filepath"]
        file_name = os.path.basename(file_url)
        _, ext = os.path.splitext(file_name)

        repre = {
            "name": ext[1:],
            "ext": ext[1:],
            "files": file_name,
            "stagingDir": os.path.dirname(file_url)
        }

        instance.data["representations"].append(repre)

        self.log.debug("instance.data {}".format(instance.data))
