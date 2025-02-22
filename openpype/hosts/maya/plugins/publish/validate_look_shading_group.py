from maya import cmds

import pyblish.api
import openpype.hosts.maya.api.action
from openpype.pipeline.publish import (
    RepairAction,
    ValidateContentsOrder,
)


class ValidateShadingEngine(pyblish.api.InstancePlugin):
    """Validate all shading engines are named after the surface material.

    Shading engines should be named "{surface_shader}SG"
    """

    order = ValidateContentsOrder
    families = ["look"]
    hosts = ["maya"]
    label = "Look Shading Engine Naming"
    actions = [
        openpype.hosts.maya.api.action.SelectInvalidAction, RepairAction
    ]

    # The default connections to check
    def process(self, instance):

        invalid = self.get_invalid(instance)
        if invalid:
            self.log.warning(
                "Found shading engines with incorrect naming:"
                "\n{}".format(invalid)
            )

    @classmethod
    def get_invalid(cls, instance):
        shapes = cmds.ls(instance, type=["nurbsSurface", "mesh"], long=True)
        invalid = []
        for shape in shapes:
            shading_engines = cmds.listConnections(
                shape, destination=True, type="shadingEngine"
            ) or []
            for shading_engine in shading_engines:
                # Hornet HPIPE-335
                shader_name = cmds.listConnections(shading_engine + ".surfaceShader")
                if shader_name:     # in case there's an orphan shading engine node
                    shader_name = shader_name[0]
                    name = (
                        shader_name + "SG"
                    )
                    if shading_engine != name:
                        invalid.append(shading_engine)

        return list(set(invalid))

    @classmethod
    def repair(cls, instance):
        shading_engines = cls.get_invalid(instance)
        for shading_engine in shading_engines:
            name = (
                cmds.listConnections(shading_engine + ".surfaceShader")[0]
                + "SG"
            )
            cmds.rename(shading_engine, name)
