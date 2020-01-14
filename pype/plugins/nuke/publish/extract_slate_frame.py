import os
import nuke
from avalon.nuke import lib as anlib
import pyblish.api
import pype


class ExtractSlateFrame(pype.api.Extractor):
    """Extracts movie and thumbnail with baked in luts

    must be run after extract_render_local.py

    """

    order = pyblish.api.ExtractorOrder + 0.01
    label = "Extract Slate Frame"

    families = ["slate"]
    hosts = ["nuke"]

    def process(self, instance):

        with anlib.maintained_selection():
            self.log.debug("instance: {}".format(instance))
            self.log.debug("instance.data[families]: {}".format(
                instance.data["families"]))

            self.render_slate(instance)

    def render_slate(self, instance):
        node = instance[0]  # group node
        self.log.info("Creating staging dir...")
        if "representations" in instance.data:
            staging_dir = instance.data[
                "representations"][0]["stagingDir"].replace("\\", "/")
            instance.data["stagingDir"] = staging_dir
        else:
            instance.data["representations"] = []
            # get output path
            render_path = instance.data['path']
            staging_dir = os.path.normpath(os.path.dirname(render_path))
            instance.data["stagingDir"] = staging_dir

        self.log.info(
            "StagingDir `{0}`...".format(instance.data["stagingDir"]))

        temporary_nodes = []
        collection = instance.data.get("collection", None)

        if collection:
            # get path
            fname = os.path.basename(collection.format(
                "{head}{padding}{tail}"))
            fhead = collection.format("{head}")

            # get first and last frame
            first_frame = min(collection.indexes) - 1
            last_frame = first_frame
        else:
            fname = os.path.basename(instance.data.get("path", None))
            fhead = os.path.splitext(fname)[0] + "."
            first_frame = instance.data.get("frameStart", None) - 1
            last_frame = first_frame

        if "#" in fhead:
            fhead = fhead.replace("#", "")[:-1]

        previous_node = node

        # get input process and connect it to baking
        ipn = self.get_view_process_node()
        if ipn is not None:
            ipn.setInput(0, previous_node)
            previous_node = ipn
            temporary_nodes.append(ipn)

        dag_node = nuke.createNode("OCIODisplay")
        dag_node.setInput(0, previous_node)
        previous_node = dag_node
        temporary_nodes.append(dag_node)

        # create write node
        write_node = nuke.createNode("Write")
        file = fhead + "slate.png"
        path = os.path.join(staging_dir, file).replace("\\", "/")
        instance.data["slateFrame"] = path
        write_node["file"].setValue(path)
        write_node["file_type"].setValue("png")
        write_node["raw"].setValue(1)
        write_node.setInput(0, previous_node)
        temporary_nodes.append(write_node)

        # Render frames
        nuke.execute(write_node.name(), int(first_frame), int(last_frame))

        self.log.debug(
            "representations: {}".format(instance.data["representations"]))
        self.log.debug(
            "slate frame path: {}".format(instance.data["slateFrame"]))

        # Clean up
        for node in temporary_nodes:
            nuke.delete(node)

        # fill slate node with comments
        self.add_comment_slate_node(instance)

    def get_view_process_node(self):

        # Select only the target node
        if nuke.selectedNodes():
            [n.setSelected(False) for n in nuke.selectedNodes()]

        ipn_orig = None
        for v in [n for n in nuke.allNodes()
                  if "Viewer" in n.Class()]:
            ip = v['input_process'].getValue()
            ipn = v['input_process_node'].getValue()
            if "VIEWER_INPUT" not in ipn and ip:
                ipn_orig = nuke.toNode(ipn)
                ipn_orig.setSelected(True)

        if ipn_orig:
            nuke.nodeCopy('%clipboard%')

            [n.setSelected(False) for n in nuke.selectedNodes()]  # Deselect all

            nuke.nodePaste('%clipboard%')

            ipn = nuke.selectedNode()

            return ipn

    def add_comment_slate_node(self, instance):
        node = instance.data.get("slateNode")
        if not node:
            return

        comment = instance.context.data.get("comment")
        intent = instance.context.data.get("intent")

        try:
            node["f_submission_note"].setValue(comment)
            node["f_submitting_for"].setValue(intent)
        except NameError:
            return
