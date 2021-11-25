import os
import random
import string

import avalon.nuke
from avalon.nuke import lib as anlib
from avalon import api

from openpype.api import (
    get_current_project_settings,
    PypeCreatorMixin
)
from .lib import check_subsetname_exists
import nuke


class PypeCreator(PypeCreatorMixin, avalon.nuke.pipeline.Creator):
    """Pype Nuke Creator class wrapper
    """
    def __init__(self, *args, **kwargs):
        super(PypeCreator, self).__init__(*args, **kwargs)
        self.presets = get_current_project_settings()["nuke"]["create"].get(
            self.__class__.__name__, {}
        )
        if check_subsetname_exists(
                nuke.allNodes(),
                self.data["subset"]):
            msg = ("The subset name `{0}` is already used on a node in"
                   "this workfile.".format(self.data["subset"]))
            self.log.error(msg + '\n\nPlease use other subset name!')
            raise NameError("`{0}: {1}".format(__name__, msg))
        return


def get_review_presets_config():
    settings = get_current_project_settings()
    review_profiles = (
        settings["global"]
        ["publish"]
        ["ExtractReview"]
        ["profiles"]
    )

    outputs = {}
    for profile in review_profiles:
        outputs.update(profile.get("outputs", {}))

    return [str(name) for name, _prop in outputs.items()]


class NukeLoader(api.Loader):
    container_id_knob = "containerId"
    container_id = ''.join(random.choice(
        string.ascii_uppercase + string.digits) for _ in range(10))

    def get_container_id(self, node):
        id_knob = node.knobs().get(self.container_id_knob)
        return id_knob.value() if id_knob else None

    def get_members(self, source):
        """Return nodes that has same 'containerId' as `source`"""
        source_id = self.get_container_id(source)
        return [node for node in nuke.allNodes(recurseGroups=True)
                if self.get_container_id(node) == source_id
                and node is not source] if source_id else []

    def set_as_member(self, node):
        source_id = self.get_container_id(node)

        if source_id:
            node[self.container_id_knob].setValue(self.container_id)
        else:
            HIDEN_FLAG = 0x00040000
            _knob = anlib.Knobby(
                "String_Knob",
                self.container_id,
                flags=[nuke.READ_ONLY, HIDEN_FLAG])
            knob = _knob.create(self.container_id_knob)
            node.addKnob(knob)

    def clear_members(self, parent_node):
        members = self.get_members(parent_node)

        dependent_nodes = None
        for node in members:
            _depndc = [n for n in node.dependent() if n not in members]
            if not _depndc:
                continue

            dependent_nodes = _depndc
            break

        for member in members:
            self.log.info("removing node: `{}".format(member.name()))
            nuke.delete(member)

        return dependent_nodes


class ExporterReview(object):
    """
    Base class object for generating review data from Nuke

    Args:
        klass (pyblish.plugin): pyblish plugin parent
        instance (pyblish.instance): instance of pyblish context

    """
    data = dict({
        "representations": list()
    })

    def __init__(self,
                 klass,
                 instance
                 ):

        self.log = klass.log
        self.instance = instance
        self.path_in = self.instance.data.get("path", None)
        self.staging_dir = self.instance.data["stagingDir"]
        self.collection = self.instance.data.get("collection", None)

    def get_file_info(self):
        if self.collection:
            self.log.debug("Collection: `{}`".format(self.collection))
            # get path
            self.fname = os.path.basename(self.collection.format(
                "{head}{padding}{tail}"))
            self.fhead = self.collection.format("{head}")

            # get first and last frame
            self.first_frame = min(self.collection.indexes)
            self.last_frame = max(self.collection.indexes)
            if "slate" in self.instance.data["families"]:
                self.first_frame += 1
        else:
            self.fname = os.path.basename(self.path_in)
            self.fhead = os.path.splitext(self.fname)[0] + "."
            self.first_frame = self.instance.data.get("frameStartHandle", None)
            self.last_frame = self.instance.data.get("frameEndHandle", None)

        if "#" in self.fhead:
            self.fhead = self.fhead.replace("#", "")[:-1]

    def get_representation_data(self, tags=None, range=False):
        add_tags = tags or []

        repre = {
            'outputName': self.name,
            'name': self.name,
            'ext': self.ext,
            'files': self.file,
            "stagingDir": self.staging_dir,
            "tags": [self.name.replace("_", "-")] + add_tags
        }

        if range:
            repre.update({
                "frameStart": self.first_frame,
                "frameEnd": self.last_frame,
            })

        self.data["representations"].append(repre)

    def get_view_input_process_node(self):
        """
        Will get any active view process.

        Arguments:
            self (class): in object definition

        Returns:
            nuke.Node: copy node of Input Process node
        """
        anlib.reset_selection()
        ipn_orig = None
        for v in nuke.allNodes(filter="Viewer"):
            ip = v['input_process'].getValue()
            ipn = v['input_process_node'].getValue()
            if "VIEWER_INPUT" not in ipn and ip:
                ipn_orig = nuke.toNode(ipn)
                ipn_orig.setSelected(True)

        if ipn_orig:
            # copy selected to clipboard
            nuke.nodeCopy('%clipboard%')
            # reset selection
            anlib.reset_selection()
            # paste node and selection is on it only
            nuke.nodePaste('%clipboard%')
            # assign to variable
            ipn = nuke.selectedNode()

            return ipn

    def get_imageio_baking_profile(self):
        from . import lib as opnlib
        nuke_imageio = opnlib.get_nuke_imageio_settings()

        # TODO: this is only securing backward compatibility lets remove
        # this once all projects's anotomy are upated to newer config
        if "baking" in nuke_imageio.keys():
            return nuke_imageio["baking"]["viewerProcess"]
        else:
            return nuke_imageio["viewer"]["viewerProcess"]




class ExporterReviewLut(ExporterReview):
    """
    Generator object for review lut from Nuke

    Args:
        klass (pyblish.plugin): pyblish plugin parent
        instance (pyblish.instance): instance of pyblish context


    """
    _temp_nodes = []

    def __init__(self,
                 klass,
                 instance,
                 name=None,
                 ext=None,
                 cube_size=None,
                 lut_size=None,
                 lut_style=None):
        # initialize parent class
        super(ExporterReviewLut, self).__init__(klass, instance)

        # deal with now lut defined in viewer lut
        if hasattr(klass, "viewer_lut_raw"):
            self.viewer_lut_raw = klass.viewer_lut_raw
        else:
            self.viewer_lut_raw = False

        self.name = name or "baked_lut"
        self.ext = ext or "cube"
        self.cube_size = cube_size or 32
        self.lut_size = lut_size or 1024
        self.lut_style = lut_style or "linear"

        # set frame start / end and file name to self
        self.get_file_info()

        self.log.info("File info was set...")

        self.file = self.fhead + self.name + ".{}".format(self.ext)
        self.path = os.path.join(
            self.staging_dir, self.file).replace("\\", "/")

    def clean_nodes(self):
        for node in self._temp_nodes:
            nuke.delete(node)
        self._temp_nodes = []
        self.log.info("Deleted nodes...")

    def generate_lut(self):
        bake_viewer_process = kwargs["bake_viewer_process"]
        bake_viewer_input_process_node = kwargs[
            "bake_viewer_input_process"]

        # ---------- start nodes creation

        # CMSTestPattern
        cms_node = nuke.createNode("CMSTestPattern")
        cms_node["cube_size"].setValue(self.cube_size)
        # connect
        self._temp_nodes.append(cms_node)
        self.previous_node = cms_node
        self.log.debug("CMSTestPattern...   `{}`".format(self._temp_nodes))

        if bake_viewer_process:
            # Node View Process
            if bake_viewer_input_process_node:
                ipn = self.get_view_input_process_node()
                if ipn is not None:
                    # connect
                    ipn.setInput(0, self.previous_node)
                    self._temp_nodes.append(ipn)
                    self.previous_node = ipn
                    self.log.debug(
                        "ViewProcess...   `{}`".format(self._temp_nodes))

            if not self.viewer_lut_raw:
                # OCIODisplay
                dag_node = nuke.createNode("OCIODisplay")
                # connect
                dag_node.setInput(0, self.previous_node)
                self._temp_nodes.append(dag_node)
                self.previous_node = dag_node
                self.log.debug("OCIODisplay...   `{}`".format(self._temp_nodes))

        # GenerateLUT
        gen_lut_node = nuke.createNode("GenerateLUT")
        gen_lut_node["file"].setValue(self.path)
        gen_lut_node["file_type"].setValue(".{}".format(self.ext))
        gen_lut_node["lut1d"].setValue(self.lut_size)
        gen_lut_node["style1d"].setValue(self.lut_style)
        # connect
        gen_lut_node.setInput(0, self.previous_node)
        self._temp_nodes.append(gen_lut_node)
        self.log.debug("GenerateLUT...   `{}`".format(self._temp_nodes))

        # ---------- end nodes creation

        # Export lut file
        nuke.execute(
            gen_lut_node.name(),
            int(self.first_frame),
            int(self.first_frame))

        self.log.info("Exported...")

        # ---------- generate representation data
        self.get_representation_data()

        self.log.debug("Representation...   `{}`".format(self.data))

        # ---------- Clean up
        self.clean_nodes()

        return self.data


class ExporterReviewMov(ExporterReview):
    """
    Metaclass for generating review mov files

    Args:
        klass (pyblish.plugin): pyblish plugin parent
        instance (pyblish.instance): instance of pyblish context

    """
    _temp_nodes = {}

    def __init__(self,
                 klass,
                 instance,
                 name=None,
                 ext=None,
                 ):
        # initialize parent class
        super(ExporterReviewMov, self).__init__(klass, instance)
        # passing presets for nodes to self
        self.nodes = klass.nodes if hasattr(klass, "nodes") else {}

        # deal with now lut defined in viewer lut
        self.viewer_lut_raw = klass.viewer_lut_raw
        self.write_colorspace = instance.data["colorspace"]

        self.name = name or "baked"
        self.ext = ext or "mov"

        # set frame start / end and file name to self
        self.get_file_info()

        self.log.info("File info was set...")

        self.file = self.fhead + self.name + ".{}".format(self.ext)
        self.path = os.path.join(
            self.staging_dir, self.file).replace("\\", "/")

    def clean_nodes(self, node_name):
        for node in self._temp_nodes[node_name]:
            nuke.delete(node)
        self._temp_nodes[node_name] = []
        self.log.info("Deleted nodes...")

    def render(self, render_node_name):
        self.log.info("Rendering...  ")
        # Render Write node
        nuke.execute(
            render_node_name,
            int(self.first_frame),
            int(self.last_frame))

        self.log.info("Rendered...")

    def save_file(self):
        import shutil
        with anlib.maintained_selection():
            self.log.info("Saving nodes as file...  ")
            # create nk path
            path = os.path.splitext(self.path)[0] + ".nk"
            # save file to the path
            shutil.copyfile(self.instance.context.data["currentFile"], path)

        self.log.info("Nodes exported...")
        return path

    def generate_mov(self, farm=False, **kwargs):
        bake_viewer_process = kwargs["bake_viewer_process"]
        bake_viewer_input_process_node = kwargs[
            "bake_viewer_input_process"]
        viewer_process_override = kwargs[
            "viewer_process_override"]

        baking_view_profile = (
            viewer_process_override or self.get_imageio_baking_profile())

        fps = self.instance.context.data["fps"]

        self.log.debug(">> baking_view_profile   `{}`".format(
            baking_view_profile))

        add_tags = kwargs.get("add_tags", [])

        self.log.info(
            "__ add_tags: `{0}`".format(add_tags))

        subset = self.instance.data["subset"]
        self._temp_nodes[subset] = []
        # ---------- start nodes creation

        # Read node
        r_node = nuke.createNode("Read")
        r_node["file"].setValue(self.path_in)
        r_node["first"].setValue(self.first_frame)
        r_node["origfirst"].setValue(self.first_frame)
        r_node["last"].setValue(self.last_frame)
        r_node["origlast"].setValue(self.last_frame)
        r_node["colorspace"].setValue(self.write_colorspace)

        # connect
        self._temp_nodes[subset].append(r_node)
        self.previous_node = r_node
        self.log.debug("Read...   `{}`".format(self._temp_nodes[subset]))

        # only create colorspace baking if toggled on
        if bake_viewer_process:
            if bake_viewer_input_process_node:
                # View Process node
                ipn = self.get_view_input_process_node()
                if ipn is not None:
                    # connect
                    ipn.setInput(0, self.previous_node)
                    self._temp_nodes[subset].append(ipn)
                    self.previous_node = ipn
                    self.log.debug(
                        "ViewProcess...   `{}`".format(
                            self._temp_nodes[subset]))

            if not self.viewer_lut_raw:
                # OCIODisplay
                dag_node = nuke.createNode("OCIODisplay")
                dag_node["view"].setValue(str(baking_view_profile))

                # connect
                dag_node.setInput(0, self.previous_node)
                self._temp_nodes[subset].append(dag_node)
                self.previous_node = dag_node
                self.log.debug("OCIODisplay...   `{}`".format(
                    self._temp_nodes[subset]))

        # Write node
        write_node = nuke.createNode("Write")
        self.log.debug("Path: {}".format(self.path))
        write_node["file"].setValue(str(self.path))
        write_node["file_type"].setValue(str(self.ext))

        # Knobs `meta_codec` and `mov64_codec` are not available on centos.
        # TODO should't this come from settings on outputs?
        try:
            write_node["meta_codec"].setValue("ap4h")
        except Exception:
            self.log.info("`meta_codec` knob was not found")

        try:
            write_node["mov64_codec"].setValue("ap4h")
            write_node["mov64_fps"].setValue(float(fps))
        except Exception:
            self.log.info("`mov64_codec` knob was not found")

        write_node["mov64_write_timecode"].setValue(1)
        write_node["raw"].setValue(1)
        # connect
        write_node.setInput(0, self.previous_node)
        self._temp_nodes[subset].append(write_node)
        self.log.debug("Write...   `{}`".format(self._temp_nodes[subset]))
        # ---------- end nodes creation

        # ---------- render or save to nk
        if farm:
            nuke.scriptSave()
            path_nk = self.save_file()
            self.data.update({
                "bakeScriptPath": path_nk,
                "bakeWriteNodeName": write_node.name(),
                "bakeRenderPath": self.path
            })
        else:
            self.render(write_node.name())
            # ---------- generate representation data
            self.get_representation_data(
                tags=["review", "delete"] + add_tags,
                range=True
            )

        self.log.debug("Representation...   `{}`".format(self.data))

        self.clean_nodes(subset)
        nuke.scriptSave()

        return self.data
