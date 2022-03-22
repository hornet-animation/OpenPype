import os

import avalon.maya
import openpype.api

from maya import cmds


class ExtractMultiverseUsd(openpype.api.Extractor):
    """Extractor for USD by Multiverse."""

    label = "Extract Multiverse USD"
    hosts = ["maya"]
    families = ["usd"]

    @property
    def options(self):
        """Overridable options for Multiverse USD Export

        Given in the following format
            - {NAME: EXPECTED TYPE}

        If the overridden option's type does not match,
        the option is not included and a warning is logged.

        """

        return {
            "stripNamespaces": bool,
            "mergeTransformAndShape": bool,
            "writeAncestors": bool,
            "flattenParentXforms": bool,
            "writeSparseOverrides": bool,
            "useMetaPrimPath": bool,
            "customRootPath": str,
            "customAttributes": str,
            "nodeTypesToIgnore": str,
            "writeMeshes": bool,
            "writeCurves": bool,
            "writeParticles": bool,
            "writeCameras": bool,
            "writeLights": bool,
            "writeJoints": bool,
            "writeCollections": bool,
            "writePositions": bool,
            "writeNormals": bool,
            "writeUVs": bool,
            "writeColorSets": bool,
            "writeTangents": bool,
            "writeRefPositions": bool,
            "writeBlendShapes": bool,
            "writeDisplayColor": bool,
            "writeSkinWeights": bool,
            "writeMaterialAssignment": bool,
            "writeHardwareShader": bool,
            "writeShadingNetworks": bool,
            "writeTransformMatrix": bool,
            "writeUsdAttributes": bool,
            "timeVaryingTopology": bool,
            "customMaterialNamespace": str,
            "numTimeSamples": int,
            "timeSamplesSpan": float
        }

    @property
    def default_options(self):
        """The default options for Multiverse USD extraction."""

        return {
            "stripNamespaces": False,
            "mergeTransformAndShape": False,
            "writeAncestors": True,
            "flattenParentXforms": False,
            "writeSparseOverrides": False,
            "useMetaPrimPath": False,
            "customRootPath": '',
            "customAttributes": '',
            "nodeTypesToIgnore": '',
            "writeMeshes": True,
            "writeCurves": True,
            "writeParticles": True,
            "writeCameras": False,
            "writeLights": False,
            "writeJoints": False,
            "writeCollections": False,
            "writePositions": True,
            "writeNormals": True,
            "writeUVs": True,
            "writeColorSets": False,
            "writeTangents": False,
            "writeRefPositions": False,
            "writeBlendShapes": False,
            "writeDisplayColor": False,
            "writeSkinWeights": False,
            "writeMaterialAssignment": False,
            "writeHardwareShader": False,
            "writeShadingNetworks": False,
            "writeTransformMatrix": True,
            "writeUsdAttributes": False,
            "timeVaryingTopology": False,
            "customMaterialNamespace": '',
            "numTimeSamples": 1,
            "timeSamplesSpan": 0.0
        }

    def process(self, instance):
        # Load plugin firstly
        cmds.loadPlugin("MultiverseForMaya", quiet=True)

        # Define output file path
        staging_dir = self.staging_dir(instance)
        file_name = "{}.usd".format(instance.name)
        file_path = os.path.join(staging_dir, file_name)
        file_path = file_path.replace('\\', '/')

        # Parse export options
        options = self.default_options
        self.log.info("Export options: {0}".format(options))
        self.log.info("Export instance data: {0}".format(instance.data))

        # Perform extraction
        self.log.info("Performing extraction ...")

        with avalon.maya.maintained_selection():
            members = instance.data("setMembers")
            members = cmds.ls(members,
                              dag=True,
                              shapes=True,
                              type=("mesh"),
                              noIntermediate=True,
                              long=True)
            self.log.info('Collected object {}'.format(members))

            import multiverse

            time_opts = None
            frame_start = instance.data['frameStart']
            frame_end = instance.data['frameEnd']
            step = instance.data['step']
            fps = instance.data['fps']
            if frame_end != frame_start:
                time_opts = multiverse.TimeOptions()

                time_opts.writeTimeRange = True
                time_opts.frameRange = (frame_start, frame_end)
                time_opts.frameIncrement = step
                time_opts.numTimeSamples = instance.data["numTimeSamples"]
                time_opts.timeSamplesSpan = instance.data["timeSamplesSpan"]
                time_opts.framePerSecond = fps

            asset_write_opts = multiverse.AssetWriteOptions(time_opts)
            options_items = getattr(options, "iteritems", options.items)
            options_discard_keys = [
                'numTimeSamples',
                'timeSamplesSpan',
                'frameStart',
                'frameEnd',
                'handleStart',
                'handleEnd',
                'step',
                'fps'
            ]
            for key, value in options_items():
                if key in options_discard_keys:
                    continue
                setattr(asset_write_opts, key, instance.data[key])

            multiverse.WriteAsset(file_path, members, asset_write_opts)

        if "representations" not in instance.data:
            instance.data["representations"] = []

        representation = {
            'name': 'usd',
            'ext': 'usd',
            'files': file_name,
            "stagingDir": staging_dir
        }
        instance.data["representations"].append(representation)

        self.log.info("Extracted instance {} to {}".format(
            instance.name, file_path))
