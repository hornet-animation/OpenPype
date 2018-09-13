from maya import cmds

import avalon.maya


class CreateRig(avalon.maya.Creator):
    """Artist-friendly rig with controls to direct motion"""

    name = "rigDefault"
    label = "Rig"
    family = "colorbleed.rig"
    icon = "wheelchair"

    def process(self):
        instance = super(CreateRig, self).process()

        self.log.info("Creating Rig instance set up ...")

        controls = cmds.sets(name="controls_SET", empty=True)
        pointcache = cmds.sets(name="out_SET", empty=True)
        cmds.sets([controls, pointcache], forceElement=instance)
