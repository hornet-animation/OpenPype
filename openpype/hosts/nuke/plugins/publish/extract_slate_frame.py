import os
from pprint import pformat
import nuke
import copy

import pyblish.api

import openpype
from openpype.hosts.nuke.api import (
    maintained_selection,
    duplicate_node,
    get_view_process_node
)


class ExtractSlateFrame(openpype.api.Extractor):
    """Extracts movie and thumbnail with baked in luts

    must be run after extract_render_local.py

    """

    order = pyblish.api.ExtractorOrder + 0.011
    label = "Extract Slate Frame"

    families = ["slate"]
    hosts = ["nuke"]

    # Settings values
    key_value_mapping = {
        "f_submission_note": [True, "{comment}"],
        "f_submitting_for": [True, "{intent[value]}"],
        "f_vfx_scope_of_work": [False, ""]
    }

    def process(self, instance):

        if "representations" not in instance.data:
            instance.data["representations"] = []

        self._create_staging_dir(instance)

        with maintained_selection():
            self.log.debug("instance: {}".format(instance))
            self.log.debug("instance.data[families]: {}".format(
                instance.data["families"]))

            if instance.data.get("bakePresets"):
                for o_name, o_data in instance.data["bakePresets"].items():
                    self.log.info("_ o_name: {}, o_data: {}".format(
                        o_name, pformat(o_data)))
                    self.render_slate(
                        instance,
                        o_name,
                        o_data["bake_viewer_process"],
                        o_data["bake_viewer_input_process"]
                    )
            else:
                # backward compatibility
                self.render_slate(instance)

            # also render image to sequence
            self._render_slate_to_sequence(instance)

    def _create_staging_dir(self, instance):

        self.log.info("Creating staging dir...")

        staging_dir = os.path.normpath(
            os.path.dirname(instance.data["path"]))

        instance.data["stagingDir"] = staging_dir

        self.log.info(
            "StagingDir `{0}`...".format(instance.data["stagingDir"]))

    def _check_frames_exists(self, instance):
        # rendering path from group write node
        fpath = instance.data["path"]

        # instance frame range with handles
        first = instance.data["frameStartHandle"]
        last = instance.data["frameEndHandle"]

        padding = fpath.count('#')

        test_path_template = fpath
        if padding:
            repl_string = "#" * padding
            test_path_template = fpath.replace(
                repl_string, "%0{}d".format(padding))

        for frame in range(first, last + 1):
            test_file = test_path_template % frame
            if not os.path.exists(test_file):
                self.log.debug("__ test_file: `{}`".format(test_file))
                return None

        return True

    def render_slate(
        self,
        instance,
        output_name=None,
        bake_viewer_process=True,
        bake_viewer_input_process=True
    ):
        """Slate frame renderer

        Args:
            instance (PyblishInstance): Pyblish instance with subset data
            output_name (str, optional):
                Slate variation name. Defaults to None.
            bake_viewer_process (bool, optional):
                Switch for viewer profile baking. Defaults to True.
            bake_viewer_input_process (bool, optional):
                Switch for input process node baking. Defaults to True.
        """
        slate_node = instance.data["slateNode"]

        # rendering path from group write node
        fpath = instance.data["path"]

        # instance frame range with handles
        first_frame = instance.data["frameStartHandle"]
        last_frame = instance.data["frameEndHandle"]

        # fill slate node with comments
        self.add_comment_slate_node(instance, slate_node)

        # solve output name if any is set
        _output_name = output_name or ""
        if _output_name:
            _output_name = "_" + _output_name

        slate_first_frame = first_frame - 1

        collection = instance.data.get("collection", None)

        if collection:
            # get path
            fname = os.path.basename(collection.format(
                "{head}{padding}{tail}"))
            fhead = collection.format("{head}")
        else:
            fname = os.path.basename(fpath)
            fhead = os.path.splitext(fname)[0] + "."

        if "#" in fhead:
            fhead = fhead.replace("#", "")[:-1]

        self.log.debug("__ first_frame: {}".format(first_frame))
        self.log.debug("__ slate_first_frame: {}".format(slate_first_frame))

        # fallback if files does not exists
        if self._check_frames_exists(instance):
            # Read node
            r_node = nuke.createNode("Read")
            r_node["file"].setValue(fpath)
            r_node["first"].setValue(first_frame)
            r_node["origfirst"].setValue(first_frame)
            r_node["last"].setValue(last_frame)
            r_node["origlast"].setValue(last_frame)
            r_node["colorspace"].setValue(instance.data["colorspace"])
            previous_node = r_node
            temporary_nodes = [previous_node]
        else:
            previous_node = slate_node.dependencies().pop()
            temporary_nodes = []

        # only create colorspace baking if toggled on
        if bake_viewer_process:
            if bake_viewer_input_process:
                # get input process and connect it to baking
                ipn = get_view_process_node()
                if ipn is not None:
                    ipn.setInput(0, previous_node)
                    previous_node = ipn
                    temporary_nodes.append(ipn)

            # add duplicate slate node and connect to previous
            duply_slate_node = duplicate_node(slate_node)
            duply_slate_node.setInput(0, previous_node)
            previous_node = duply_slate_node
            temporary_nodes.append(duply_slate_node)

            # add viewer display transformation node
            dag_node = nuke.createNode("OCIODisplay")
            dag_node.setInput(0, previous_node)
            previous_node = dag_node
            temporary_nodes.append(dag_node)

        else:
            # add duplicate slate node and connect to previous
            duply_slate_node = duplicate_node(slate_node)
            duply_slate_node.setInput(0, previous_node)
            previous_node = duply_slate_node
            temporary_nodes.append(duply_slate_node)

        # create write node
        write_node = nuke.createNode("Write")
        file = fhead[:-1] + _output_name + "_slate.png"
        path = os.path.join(
            instance.data["stagingDir"], file).replace("\\", "/")

        # add slate path to `slateFrames` instance data attr
        if not instance.data.get("slateFrames"):
            instance.data["slateFrames"] = {}

        instance.data["slateFrames"][output_name or "*"] = path

        # create write node
        write_node["file"].setValue(path)
        write_node["file_type"].setValue("png")
        write_node["raw"].setValue(1)
        write_node.setInput(0, previous_node)
        temporary_nodes.append(write_node)

        # Render frames
        nuke.execute(
            write_node.name(), int(slate_first_frame), int(slate_first_frame))

        # Clean up
        for node in temporary_nodes:
            nuke.delete(node)

    def _render_slate_to_sequence(self, instance):
        # set slate frame
        first_frame = instance.data["frameStartHandle"]
        slate_first_frame = first_frame - 1

        # render slate as sequence frame
        nuke.execute(
            instance.data["name"],
            int(slate_first_frame),
            int(slate_first_frame)
        )

    def add_comment_slate_node(self, instance, node):

        comment = instance.context.data.get("comment")
        intent = instance.context.data.get("intent")
        if not isinstance(intent, dict):
            intent = {
                "label": intent,
                "value": intent
            }

        fill_data = copy.deepcopy(instance.data["anatomyData"])
        fill_data.update({
            "custom": copy.deepcopy(
                instance.data.get("customData") or {}
            ),
            "comment": comment,
            "intent": intent
        })

        for key, _values in self.key_value_mapping.items():
            enabled, template = _values
            if not enabled:
                self.log.debug("Key \"{}\" is disabled".format(key))
                continue

            try:
                value = template.format(**fill_data)

            except ValueError:
                self.log.warning(
                    "Couldn't fill template \"{}\" with data: {}".format(
                        template, fill_data
                    ),
                    exc_info=True
                )
                continue

            except KeyError:
                self.log.warning(
                    (
                        "Template contains unknown key."
                        " Template \"{}\" Data: {}"
                    ).format(template, fill_data),
                    exc_info=True
                )
                continue

            try:
                node[key].setValue(value)
                self.log.info("Change key \"{}\" to value \"{}\"".format(
                    key, value
                ))
            except NameError:
                self.log.warning((
                    "Failed to set value \"{0}\" on node attribute \"{0}\""
                ).format(value))
