#!/usr/bin/env python

from openpype.pipeline import publish
import maya.cmds as cmds
class ExtractUNCPaths(publish.Extractor):
    """
    clean UNC pathed textures out of the scene and replace them with drive letters
    """
    label = "Extract UNC Paths"
    hosts = ['maya']
    families = ['render', 'look','renderlayer']

    def process(self, instance):
        mappings = {
            '//fs.hellohornet.lan/production/': 'P:/',
            '//fs.hellohornet.lan/resources/': 'R:/'
        }
        texFiles = cmds.ls(type="file")
        for texFile in texFiles:
            texPath = cmds.getAttr('%s.fileTextureName' %texFile)
            # replace UNC path

            for key, value in mappings.items():
                if key in texPath:
                    texPath = texPath.replace(key, value)
                    cmds.setAttr('%s.fileTextureName' %texFile, texPath, type="string")
            # Uppercase the drive codes
            cmds.setAttr('%s.fileTextureName' %texFile, texPath.capitalize(), type="string")
