import os
import glob
import re

from maya import cmds

import pyblish.api

from colorbleed.maya import lib


SETTINGS = {"renderDensity",
            "renderWidth",
            "renderLength",
            "increaseRenderBounds",
            "imageSearchPath",
            "cbId"}


class CollectYetiRig(pyblish.api.InstancePlugin):
    """Collect all information of the Yeti Rig"""

    order = pyblish.api.CollectorOrder + 0.4
    label = "Collect Yeti Rig"
    families = ["colorbleed.yetiRig"]
    hosts = ["maya"]

    def process(self, instance):

        assert "input_SET" in cmds.sets(instance.name, query=True), (
            "Yeti Rig must have an input_SET")

        # Get the input meshes information
        input_content = cmds.sets("input_SET", query=True)
        input_nodes = cmds.listRelatives(input_content,
                                         allDescendents=True,
                                         fullPath=True) or input_content

        # Get all the shapes
        input_shapes = cmds.ls(input_nodes, long=True)

        # Store all connections
        connections = cmds.listConnections(input_shapes,
                                           source=True,
                                           destination=False,
                                           connections=True,
                                           plugs=True) or []

        # Group per source, destination pair
        grouped = [(item, connections[i+1]) for i, item in
                   enumerate(connections) if i % 2 == 0]

        inputs = []
        for src, dest in grouped:
            src_node, src_attr = src.split(".", 1)
            dest_node, dest_attr = dest.split(".", 1)

            # The plug must go in the socket, remember this for the loader
            inputs.append({"connections": [src_attr, dest_attr],
                           "destinationID": lib.get_id(dest_node),
                           "sourceID": lib.get_id(src_node)})

        # Collect any textures if used
        yeti_resources = []
        yeti_nodes = cmds.ls(instance[:], type="pgYetiMaya")
        for node in yeti_nodes:
            # Get Yeti resources (textures)
            # TODO: referenced files in Yeti Graph
            resources = self.get_yeti_resources(node)
            yeti_resources.extend(resources)

        instance.data["rigsettings"] = {"inputs": inputs}

        instance.data["resources"] = yeti_resources

        # Force frame range for export
        instance.data["startFrame"] = 1
        instance.data["endFrame"] = 1

    def get_yeti_resources(self, node):
        """Get all texture file paths

        If a texture is a sequence it gathers all sibling files to ensure
        the texture sequence is complete.

        Args:
            node (str): node name of the pgYetiMaya node

        Returns:
            list
        """
        resources = []
        image_search_path = cmds.getAttr("{}.imageSearchPath".format(node))
        texture_filenames = cmds.pgYetiCommand(node, listTextures=True)

        if texture_filenames and not image_search_path:
            raise ValueError("pgYetiMaya node '%s' is missing the path to the "
                             "files in the 'imageSearchPath "
                             "atttribute'" % node)

        for texture in texture_filenames:
            node_resources = {"files": [], "source": texture, "node": node}
            texture_filepath = os.path.join(image_search_path, texture)
            if len(texture.split(".")) > 2:

                # For UDIM based textures (tiles)
                if "<UDIM>" in texture:
                    sequences = self.get_sequence(texture_filepath,
                                                  pattern="<UDIM>")
                    node_resources["files"].extend(sequences)

                # Based textures (animated masks f.e)
                elif "%04d" in texture:
                    sequences = self.get_sequence(texture_filepath,
                                                  pattern="%04d")
                    node_resources["files"].extend(sequences)
                # Assuming it is a fixed name
                else:
                    node_resources["files"].append(texture_filepath)
            else:
                node_resources["files"].append(texture_filepath)

            resources.append(node_resources)

        return resources

    def get_sequence(self, filename, pattern="%04d"):
        """Get sequence from filename

        Supports negative frame ranges like -001, 0000, 0001 and -0001,
        0000, 0001.

        Arguments:
            filename (str): The full path to filename containing the given
            pattern.
            pattern (str): The pattern to swap with the variable frame number.

        Returns:
            list: file sequence.

        """

        from avalon.vendor import clique

        glob_pattern = filename.replace(pattern, "*")

        escaped = re.escape(filename)
        re_pattern = escaped.replace(pattern, "-?[0-9]+")

        files = glob.glob(glob_pattern)
        files = [str(f) for f in files if re.match(re_pattern, f)]

        pattern = [clique.PATTERNS["frames"]]
        collection, remainer = clique.assemble(files, patterns=pattern)

        return collection
