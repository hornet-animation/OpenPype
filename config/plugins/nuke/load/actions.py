"""A module containing generic loader actions that will display in the Loader.

"""

from avalon import api


class NukeSetFrameRangeLoader(api.Loader):
    """Specific loader of Alembic for the avalon.animation family"""

    families = ["studio.animation",
                "studio.camera",
                "studio.imagesequence",
                "studio.yeticache",
                "studio.pointcache"]
    representations = ["*"]

    label = "Set frame range"
    order = 11
    icon = "clock-o"
    color = "white"

    def load(self, context, name, namespace, data):

        from config.nuke import lib

        version = context['version']
        version_data = version.get("data", {})

        start = version_data.get("startFrame", None)
        end = version_data.get("endFrame", None)

        if start is None or end is None:
            print("Skipping setting frame range because start or "
                  "end frame data is missing..")
            return

        lib.update_frame_range(start, end)


class NukeSetFrameRangeWithHandlesLoader(api.Loader):
    """Specific loader of Alembic for the avalon.animation family"""

    families = ["studio.animation",
                "studio.camera",
                "studio.imagesequence",
                "studio.yeticache",
                "studio.pointcache"]
    representations = ["*"]

    label = "Set frame range (with handles)"
    order = 12
    icon = "clock-o"
    color = "white"

    def load(self, context, name, namespace, data):

        from config.nuke import lib

        version = context['version']
        version_data = version.get("data", {})

        start = version_data.get("startFrame", None)
        end = version_data.get("endFrame", None)

        if start is None or end is None:
            print("Skipping setting frame range because start or "
                  "end frame data is missing..")
            return

        # Include handles
        handles = version_data.get("handles", 0)
        start -= handles
        end += handles

        lib.update_frame_range(start, end)
