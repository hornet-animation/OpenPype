import pyblish.api

import maya.cmds as cmds


class CollectLook(pyblish.api.InstancePlugin):
    """Collect out hierarchy data for instance.

    Collect all hierarchy nodes which reside in the out_SET of the animation
    instance or poitncache instance. This is to unify the logic of retrieving
    that specifc data. This eliminates the need to write two separate pieces
    of logic to fetch all hierarchy nodes.

    Results in a list of nodes from the content of the instances

    """

    order = pyblish.api.CollectorOrder + 0.4
    families = ["colorbleed.animation", "colorbleed.pointcache"]
    label = "Collect Animation"
    hosts = ["maya"]

    ignore_type = ["constraints"]

    def process(self, instance):
        """Collect the hierarchy nodes"""

        family = instance.data["family"]
        if family == "colorbleed.animation":
            out_set = next((i for i in instance.data["setMembers"] if
                            i.endswith("out_SET")), None)

            assert out_set, ("Expecting out_SET for instance of family"
                             "'%s'" % family)
            members = cmds.ls(cmds.sets(out_set, query=True), long=True)
        else:
            members = cmds.ls(instance, long=True)

        # Get all the relatives of the members
        descendants = cmds.listRelatives(members,
                                         allDescendents=True,
                                         fullPath=True) or []
        descendants = cmds.ls(descendants, noIntermediate=True, long=True)

        # Add members and descendants together for a complete overview
        hierarchy = members + descendants

        # Ignore certain node types (e.g. constraints)
        ignore = cmds.ls(hierarchy, type=self.ignore_type, long=True)
        if ignore:
            ignore = set(ignore)
            hierarchy = [node for node in hierarchy if node not in ignore]

            return hierarchy

        # Store data in the instance for the validator
        instance.data["pointcache_data"] = hierarchy
