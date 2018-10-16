import maya.cmds as cmds

import pyblish.api
import pype.api
import pype.maya.lib as lib


class ValidateRenderSettings(pyblish.api.InstancePlugin):
    """Validates the global render settings

    * File Name Prefix must be as followed:
        * vray: <Scene>/<Layer>/<Layer>
        * arnold: <Scene>/<RenderLayer>/<RenderLayer>
        * default: <Scene>/<RenderLayer>/<RenderLayer>

    * Frame Padding must be:
        * default: 4

    * Animation must be toggle on, in Render Settings - Common tab:
        * vray: Animation on standard of specific
        * arnold: Frame / Animation ext: Any choice without "(Single Frame)"
        * redshift: Animation toggled on

    NOTE:
        The repair function of this plugin does not repair the animation
        setting of the render settings due to multiple possibilities.

    """

    order = pype.api.ValidateContentsOrder
    label = "Render Settings"
    hosts = ["maya"]
    families = ["studio.renderlayer"]
    actions = [pype.api.RepairAction]

    DEFAULT_PADDING = 4
    RENDERER_PREFIX = {"vray": "<Scene>/<Scene>_<Layer>/<Layer>"}
    DEFAULT_PREFIX = "<Scene>/<Scene>_<RenderLayer>/<RenderLayer>"

    def process(self, instance):

        invalid = self.get_invalid(instance)
        if invalid:
            raise ValueError("Invalid render settings found for '%s'!"
                             % instance.name)

    @classmethod
    def get_invalid(cls, instance):

        invalid = False

        renderer = instance.data['renderer']
        layer_node = instance.data['setMembers']

        # Collect the filename prefix in the render layer
        with lib.renderlayer(layer_node):

            render_attrs = lib.RENDER_ATTRS.get(renderer,
                                                lib.RENDER_ATTRS['default'])
            node = render_attrs["node"]
            padding_attr = render_attrs["padding"]
            prefix_attr = render_attrs["prefix"]

            prefix = cmds.getAttr("{}.{}".format(node, prefix_attr))
            padding = cmds.getAttr("{}.{}".format(node, padding_attr))

            anim_override = cmds.getAttr("defaultRenderGlobals.animation")
            if not anim_override:
                invalid = True
                cls.log.error("Animation needs to be enabled. Use the same "
                              "frame for start and end to render single frame")

            fname_prefix = cls.RENDERER_PREFIX.get(renderer,
                                                   cls.DEFAULT_PREFIX)
            if prefix != fname_prefix:
                invalid = True
                cls.log.error("Wrong file name prefix, expecting %s"
                              % fname_prefix)

            if padding != cls.DEFAULT_PADDING:
                invalid = True
                cls.log.error("Expecting padding of {} ( {} )".format(
                    cls.DEFAULT_PADDING, "0" * cls.DEFAULT_PADDING))

        return invalid

    @classmethod
    def repair(cls, instance):

        renderer = instance.data['renderer']
        layer_node = instance.data['setMembers']

        with lib.renderlayer(layer_node):
            default = lib.RENDER_ATTRS['default']
            render_attrs = lib.RENDER_ATTRS.get(renderer, default)

            # Repair prefix
            node = render_attrs["node"]
            prefix_attr = render_attrs["prefix"]

            fname_prefix = cls.RENDERER_PREFIX.get(renderer, cls.DEFAULT_PREFIX)
            cmds.setAttr("{}.{}".format(node, prefix_attr),
                         fname_prefix, type="string")

            # Repair padding
            padding_attr = render_attrs["padding"]
            cmds.setAttr("{}.{}".format(node, padding_attr),
                         cls.DEFAULT_PADDING)
