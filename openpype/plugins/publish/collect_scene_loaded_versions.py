
import pyblish.api


class CollectSceneLoadedVersions(pyblish.api.ContextPlugin):

    order = pyblish.api.CollectorOrder + 0.0001
    label = "Collect Versions Loaded in Scene"
    hosts = [
        "aftereffects",
        "blender",
        "celaction",
        "fusion",
        "harmony",
        "hiero",
        "houdini",
        "maya",
        "nuke",
        "photoshop",
        "resolve",
        "tvpaint"
    ]

    def process(self, context):
        from avalon import api, io

        current_file = context.data.get("currentFile")
        if not current_file:
            self.log.warn("No work file collected.")
            return

        host = api.registered_host()
        if host is None:
            self.log.warn("No registered host.")
            return

        if not hasattr(host, "ls"):
            host_name = host.__name__
            self.log.warn("Host %r doesn't have ls() implemented." % host_name)
            return

        loaded_versions = []
        _containers = list(host.ls())
        _repr_ids = [io.ObjectId(c["representation"]) for c in _containers]
        version_by_repr = {
            str(doc["_id"]): doc["parent"] for doc in
            io.find({"_id": {"$in": _repr_ids}}, projection={"parent": 1})
        }

        for con in _containers:
            # NOTE:
            # may have more then one representation that are same version
            version = {
                "objectName": con["objectName"],  # container node name
                "subsetName": con["name"],
                "representation": io.ObjectId(con["representation"]),
                "version": version_by_repr[con["representation"]],  # _id
            }
            loaded_versions.append(version)

        context.data["loadedVersions"] = loaded_versions
