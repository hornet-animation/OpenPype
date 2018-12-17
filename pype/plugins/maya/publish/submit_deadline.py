import os
import json
import getpass

from maya import cmds

from avalon import api
from avalon.vendor import requests

import pyblish.api

import pype.maya.lib as lib


def get_renderer_variables(renderlayer=None):
    """Retrieve the extension which has been set in the VRay settings

    Will return None if the current renderer is not VRay
    For Maya 2016.5 and up the renderSetup creates renderSetupLayer node which
    start with `rs`. Use the actual node name, do NOT use the `nice name`

    Args:
        renderlayer (str): the node name of the renderlayer.

    Returns:
        dict
    """

    renderer = lib.get_renderer(renderlayer or lib.get_current_renderlayer())
    render_attrs = lib.RENDER_ATTRS.get(renderer, lib.RENDER_ATTRS["default"])

    padding = cmds.getAttr("{}.{}".format(render_attrs["node"],
                                          render_attrs["padding"]))

    filename_0 = cmds.renderSettings(fullPath=True, firstImageName=True)[0]

    if renderer == "vray":
        # Maya's renderSettings function does not return V-Ray file extension
        # so we get the extension from vraySettings
        extension = cmds.getAttr("vraySettings.imageFormatStr")

        # When V-Ray image format has not been switched once from default .png
        # the getAttr command above returns None. As such we explicitly set
        # it to `.png`
        if extension is None:
            extension = "png"

        filename_prefix = "<Scene>/<Scene>_<Layer>/<Layer>"
    else:
        # Get the extension, getAttr defaultRenderGlobals.imageFormat
        # returns an index number.
        filename_base = os.path.basename(filename_0)
        extension = os.path.splitext(filename_base)[-1].strip(".")
        filename_prefix = "<Scene>/<Scene>_<RenderLayer>/<RenderLayer>"

    return {"ext": extension,
            "filename_prefix": filename_prefix,
            "padding": padding,
            "filename_0": filename_0}


def preview_fname(folder, scene, layer, padding, ext):
    """Return output file path with #### for padding.

    Deadline requires the path to be formatted with # in place of numbers.
    For example `/path/to/render.####.png`

    Args:
        folder (str): The root output folder (image path)
        scene (str): The scene name
        layer (str): The layer name to be rendered
        padding (int): The padding length
        ext(str): The output file extension

    Returns:
        str

    """

    # Following hardcoded "<Scene>/<Scene>_<Layer>/<Layer>"
    output = "{scene}/{scene}_{layer}/{layer}.{number}.{ext}".format(
        scene=scene,
        layer=layer,
        number="#" * padding,
        ext=ext
    )

    return os.path.join(folder, output)


class MayaSubmitDeadline(pyblish.api.InstancePlugin):
    """Submit available render layers to Deadline

    Renders are submitted to a Deadline Web Service as
    supplied via the environment variable DEADLINE_REST_URL

    """

    label = "Submit to Deadline"
    order = pyblish.api.IntegratorOrder + 0.1
    hosts = ["maya"]
    families = ["renderlayer"]

    def process(self, instance):

        self.log.debug('Starting deadline submitter')

        try:
            deadline_url = os.environ["DEADLINE_REST_URL"]
        except KeyError:
            self.log.error("Deadline REST API url not found.")

        # AVALON_DEADLINE = api.Session.get("AVALON_DEADLINE",
        #                                  "http://localhost:8082")
        # assert AVALON_DEADLINE, "Requires AVALON_DEADLINE

        context = instance.context

        filepath = None

        allInstances = []
        for result in context.data["results"]:
            if (result["instance"] is not None and
               result["instance"] not in allInstances):
                allInstances.append(result["instance"])

        for inst in allInstances:
            print(inst)
            if inst.data['family'] == 'scene':
                filepath = inst.data['destination_list'][0]

        if not filepath:
            filepath = context.data["currentFile"]

        self.log.debug(filepath)

        workspace = context.data["workspaceDir"]
        filename = os.path.basename(filepath)
        comment = context.data.get("comment", "")
        scene = os.path.splitext(filename)[0]
        dirname = os.path.join(workspace, "renders")
        renderlayer = instance.data['setMembers']       # rs_beauty
        renderlayer_name = instance.data['subset']      # beauty
        renderlayer_globals = instance.data["renderGlobals"]
        legacy_layers = renderlayer_globals["UseLegacyRenderLayers"]
        deadline_user = context.data.get("deadlineUser", getpass.getuser())
        jobname = "%s - %s" % (filename, instance.name)

        # Get the variables depending on the renderer
        render_variables = get_renderer_variables(renderlayer)
        output_filename_0 = preview_fname(folder=dirname,
                                          scene=scene,
                                          layer=renderlayer_name,
                                          padding=render_variables["padding"],
                                          ext=render_variables["ext"])

        try:
            # Ensure render folder exists
            os.makedirs(dirname)
        except OSError:
            pass

        # Documentation for keys available at:
        # https://docs.thinkboxsoftware.com
        #    /products/deadline/8.0/1_User%20Manual/manual
        #    /manual-submission.html#job-info-file-options
        payload = {
            "JobInfo": {
                # Top-level group name
                "BatchName": filename,

                # Job name, as seen in Monitor
                "Name": jobname,

                # Arbitrary username, for visualisation in Monitor
                "UserName": deadline_user,

                "Plugin": instance.data.get("mayaRenderPlugin", "MayaBatch"),
                "Frames": "{start}-{end}x{step}".format(
                    start=int(instance.data["startFrame"]),
                    end=int(instance.data["endFrame"]),
                    step=int(instance.data["byFrameStep"]),
                ),

                "Comment": comment,

                # Optional, enable double-click to preview rendered
                # frames from Deadline Monitor
                "OutputFilename0": output_filename_0.replace("\\", "/"),
            },
            "PluginInfo": {
                # Input
                "SceneFile": filepath,

                # Output directory and filename
                "OutputFilePath": dirname.replace("\\", "/"),
                "OutputFilePrefix": render_variables["filename_prefix"],

                # Mandatory for Deadline
                "Version": cmds.about(version=True),

                # Only render layers are considered renderable in this pipeline
                "UsingRenderLayers": True,

                # Use legacy Render Layer system
                "UseLegacyRenderLayers": legacy_layers,

                # Render only this layer
                "RenderLayer": renderlayer,

                # Determine which renderer to use from the file itself
                "Renderer": instance.data["renderer"],

                # Resolve relative references
                "ProjectPath": workspace,
            },

            # Mandatory for Deadline, may be empty
            "AuxFiles": []
        }

        # Include critical environment variables with submission
        keys = [
            # This will trigger `userSetup.py` on the slave
            # such that proper initialisation happens the same
            # way as it does on a local machine.
            # TODO(marcus): This won't work if the slaves don't
            # have accesss to these paths, such as if slaves are
            # running Linux and the submitter is on Windows.
            "PYTHONPATH",

            "MTOA_EXTENSIONS_PATH",
            "MTOA_EXTENSIONS",
            "DYLD_LIBRARY_PATH",
            "MAYA_RENDER_DESC_PATH",
            "MAYA_MODULE_PATH",
            "ARNOLD_PLUGIN_PATH",
            "AVALON_SCHEMA",

            # todo: This is a temporary fix for yeti variables
            "PEREGRINEL_LICENSE",
            "REDSHIFT_MAYAEXTENSIONSPATH",
            "REDSHIFT_DISABLEOUTPUTLOCKFILES"
            "VRAY_FOR_MAYA2018_PLUGINS_X64",
            "VRAY_PLUGINS_X64",
            "VRAY_USE_THREAD_AFFINITY",
            "MAYA_MODULE_PATH",
            "TOOL_ENV"
        ]
        environment = dict({key: os.environ[key] for key in keys
                            if key in os.environ}, **api.Session)

        for path in os.environ:
            if path.lower().startswith('pype_'):
                environment[path] = os.environ[path]

        PATHS = os.environ["PATH"].split(";")
        environment["PATH"] = ";".join([p for p in PATHS
                                        if p.startswith("P:")])
        clean_pythonpath = ''
        for path in environment['PYTHONPATH'].split(os.pathsep):
            # self.log.debug('checking path for UTF: {}'.format(path))
            try:
                path.decode('UTF-8', 'strict')
                # path = path.lower().replace("k:/", r"\\kre-c01\\share\\").replace("p:/", r"\\kre-p01\\share\\")
                clean_pythonpath += path + os.pathsep
            except UnicodeDecodeError:
                self.log.debug('path contains non UTF characters')
        environment['PYTHONPATH'] = clean_pythonpath

        for key in environment:
            remapped_key = ''
            list_paths = environment[key].split(os.pathsep)
            if len(list_paths) > 1:
                for path in list_paths:
                    path = path.replace("K:/", "\\\\kre-c01\\share\\").replace("P:/", "\\\\kre-p01\\share\\")
                    path = path.replace("K:\\", "\\\\kre-c01\\share\\").replace("P:\\", "\\\\kre-p01\\share\\")
                    remapped_key += path + os.pathsep
            else:
                path = list_paths[0].replace("K:/", "\\\\kre-c01\\share\\").replace("P:/", "\\\\kre-p01\\share\\")
                path = path.replace("K:\\", "\\\\kre-c01\\share\\").replace("P:\\", "\\\\kre-p01\\share\\")
                remapped_key = path
            environment[key] = remapped_key

        payload["JobInfo"].update({
            "EnvironmentKeyValue%d" % index: "{key}={value}".format(
                key=key,
                value=environment[key]
            ) for index, key in enumerate(environment)
        })

        # Include optional render globals
        render_globals = instance.data.get("renderGlobals", {})
        payload["JobInfo"].update(render_globals)

        plugin = payload["JobInfo"]["Plugin"]
        self.log.info("using render plugin : {}".format(plugin))

        self.preflight_check(instance)

        self.log.info("Submitting..")
        self.log.info(json.dumps(payload, indent=4, sort_keys=True))

        # E.g. http://192.168.0.1:8082/api/jobs
        url = "{}/api/jobs".format(deadline_url)
        response = requests.post(url, json=payload)
        if not response.ok:
            raise Exception(response.text)

        # Store output dir for unified publisher (filesequence)
        instance.data["outputDir"] = os.path.dirname(output_filename_0)
        instance.data["deadlineSubmissionJob"] = response.json()

    def preflight_check(self, instance):
        """Ensure the startFrame, endFrame and byFrameStep are integers"""

        for key in ("startFrame", "endFrame", "byFrameStep"):
            value = instance.data[key]

            if int(value) == value:
                continue

            self.log.warning(
                "%f=%d was rounded off to nearest integer"
                % (value, int(value))
            )
