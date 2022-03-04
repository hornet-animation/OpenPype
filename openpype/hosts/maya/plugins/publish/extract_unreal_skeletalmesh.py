# -*- coding: utf-8 -*-
"""Create Unreal Skeletal Mesh data to be extracted as FBX."""
import os

from maya import cmds  # noqa

import pyblish.api
import openpype.api
from openpype.hosts.maya.api.lib import (
    root_parent,
    maintained_selection,
    delete_after
)
from openpype.hosts.maya.api import fbx


class ExtractUnrealSkeletalMesh(openpype.api.Extractor):
    """Extract Unreal Skeletal Mesh as FBX from Maya. """

    order = pyblish.api.ExtractorOrder - 0.1
    label = "Extract Unreal Skeletal Mesh"
    families = ["skeletalMesh"]

    def process(self, instance):
        fbx_exporter = fbx.FBXExtractor(log=self.log)

        # Define output path
        staging_dir = self.staging_dir(instance)
        filename = "{0}.fbx".format(instance.name)
        path = os.path.join(staging_dir, filename)

        # The export requires forward slashes because we need
        # to format it into a string in a mel expression
        path = path.replace('\\', '/')

        self.log.info("Extracting FBX to: {0}".format(path))
        self.log.info("Members: {0}".format(instance))
        self.log.info("Instance: {0}".format(instance[:]))

        fbx_exporter.set_options_from_instance(instance)
        with maintained_selection():
            with root_parent(instance):
                self.log.info("Un-parenting: {}".format(instance))
                fbx_exporter.export(instance, path)

        if "representations" not in instance.data:
            instance.data["representations"] = []

        representation = {
            'name': 'fbx',
            'ext': 'fbx',
            'files': filename,
            "stagingDir": staging_dir,
        }
        instance.data["representations"].append(representation)

        self.log.info("Extract FBX successful to: {0}".format(path))
