import pyblish.api
import colorbleed.api

from maya import cmds


class ValidateVRayTranslatorEnabled(pyblish.api.ContextPlugin):

    order = colorbleed.api.ValidateContentsOrder
    label = "VRay Translator Settings"
    families = ["colorbleed.vrayscene"]
    actions = [colorbleed.api.RepairContextAction]

    def process(self, context):

        invalid = self.get_invalid(context)
        if invalid:
            raise RuntimeError("Found invalid VRay Translator settings!")

    @classmethod
    def get_invalid(cls, context):

        invalid = False

        # Check if there are any vray scene instances
        # The reason to not use host.lsattr() as used in collect_vray_scene
        # is because that information is already available in the context
        vrayscene_instances = [i for i in context[:] if i.data["family"]
                               in cls.families]

        if not vrayscene_instances:
            cls.log.info("No VRay Scene instances found, skipping..")
            return

        # Ignore if no VRayScenes are enabled for publishing
        if not any(i.data.get("publish", True) for i in vrayscene_instances):
            cls.log.info("VRay Scene instances are disabled, skipping..")
            return

        # Get vraySettings node
        vray_settings = cmds.ls(type="VRaySettingsNode")
        assert vray_settings, "Please ensure a VRay Settings Node is present"

        node = vray_settings[0]

        if cmds.setAttr("{}.vrscene_render_on".format(node)):
            cls.log.error("Render is enabled, this should be disabled")
            invalid = True

        if not cmds.getAttr("{}.vrscene_on".format(node)):
            cls.log.error("Export vrscene not enabled")
            invalid = True

        if not cmds.getAttr("{}.misc_eachFrameInFile".format(node)):
            cls.log.error("Each Frame in File not enabled")
            invalid = True

        vrscene_filename = cmds.getAttr("{}.vrscene_filename".format(node))
        if vrscene_filename != "vrayscene/<Scene>/<Scene>_<Layer>/<Layer>":
            cls.log.error("Template for file name is wrong")
            invalid = True

        return invalid

    @classmethod
    def repair(cls, context):

        vray_settings = cmds.ls(type="VRaySettingsNode")
        if not vray_settings:
            node = cmds.createNode("VRaySettingsNode")
        else:
            node = vray_settings[0]

        cmds.setAttr("{}.vrscene_render_on".format(node), False)
        cmds.setAttr("{}.vrscene_on".format(node), True)
        cmds.setAttr("{}.misc_eachFrameInFile".format(node), True)
        cmds.setAttr("{}.vrscene_filename".format(node),
                     "vrayscene/<Scene>/<Scene>_<Layer>/<Layer>",
                     type="string")
