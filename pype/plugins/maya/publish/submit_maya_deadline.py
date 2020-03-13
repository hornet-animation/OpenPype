import os
import json
import getpass
import clique

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
        filename_prefix = cmds.getAttr("defaultRenderGlobals.imageFilePrefix")

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

    fileprefix = cmds.getAttr("defaultRenderGlobals.imageFilePrefix")
    output = fileprefix + ".{number}.{ext}"
    # RenderPass is currently hardcoded to "beauty" because its not important
    # for the deadline submission, but we will need something to replace
    # "<RenderPass>".
    mapping = {
        "<Scene>": "{scene}",
        "<RenderLayer>": "{layer}",
        "RenderPass": "beauty"
    }
    for key, value in mapping.items():
        output = output.replace(key, value)
    output = output.format(
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
    if not os.environ.get("DEADLINE_REST_URL"):
        optional = False
        active = False
    else:
        optional = True

    use_published = True

    def process(self, instance):

        DEADLINE_REST_URL = os.environ.get("DEADLINE_REST_URL",
                                           "http://localhost:8082")
        assert DEADLINE_REST_URL, "Requires DEADLINE_REST_URL"

        context = instance.context
        workspace = context.data["workspaceDir"]
        anatomy = context.data['anatomy']

        filepath = None

        if self.use_published:
            for i in context:
                if "workfile" in i.data["families"]:
                    assert i.data["publish"] is True, (
                        "Workfile (scene) must be published along")
                    template_data = i.data.get("anatomyData")
                    rep = i.data.get("representations")[0].get("name")
                    template_data["representation"] = rep
                    template_data["ext"] = rep
                    template_data["comment"] = None
                    anatomy_filled = anatomy.format(template_data)
                    template_filled = anatomy_filled["publish"]["path"]
                    filepath = os.path.normpath(template_filled)
                    self.log.info("Using published scene for render {}".format(
                        filepath))

                    # now we need to switch scene in expected files
                    # because <scene> token will now point to published
                    # scene file and that might differ from current one
                    new_scene = os.path.splitext(
                        os.path.basename(filepath))[0]
                    orig_scene = os.path.splitext(
                        os.path.basename(context.data["currentFile"]))[0]
                    exp = instance.data.get("expectedFiles")

                    if isinstance(exp[0], dict):
                        # we have aovs and we need to iterate over them
                        new_exp = {}
                        for aov, files in exp[0].items():
                            replaced_files = []
                            for f in files:
                                replaced_files.append(
                                    f.replace(orig_scene, new_scene)
                                )
                            new_exp[aov] = replaced_files
                        instance.data["expectedFiles"] = [new_exp]
                    else:
                        new_exp = []
                        for f in exp:
                            new_exp.append(
                                f.replace(orig_scene, new_scene)
                            )
                        instance.data["expectedFiles"] = [new_exp]
                    self.log.info("Scene name was switched {} -> {}".format(
                        orig_scene, new_scene
                    ))

        allInstances = []
        for result in context.data["results"]:
            if (result["instance"] is not None and
               result["instance"] not in allInstances):
                allInstances.append(result["instance"])

        # fallback if nothing was set
        if not filepath:
            self.log.warning("Falling back to workfile")
            filepath = context.data["currentFile"]

        self.log.debug(filepath)

        filename = os.path.basename(filepath)
        comment = context.data.get("comment", "")
        scene = os.path.splitext(filename)[0]
        dirname = os.path.join(workspace, "renders")
        renderlayer = instance.data['setMembers']       # rs_beauty
        renderlayer_name = instance.data['subset']      # beauty
        # renderlayer_globals = instance.data["renderGlobals"]
        # legacy_layers = renderlayer_globals["UseLegacyRenderLayers"]
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
                    start=int(instance.data["frameStart"]),
                    end=int(instance.data["frameEnd"]),
                    step=int(instance.data["byFrameStep"]),
                ),

                "Comment": comment,

                # Optional, enable double-click to preview rendered
                # frames from Deadline Monitor
                "OutputDirectory0": os.path.dirname(output_filename_0),
                "OutputFilename0": output_filename_0.replace("\\", "/")
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

        exp = instance.data.get("expectedFiles")

        OutputFilenames = {}
        expIndex = 0

        if isinstance(exp[0], dict):
            # we have aovs and we need to iterate over them
            for aov, files in exp[0].items():
                col = clique.assemble(files)[0][0]
                outputFile = col.format('{head}{padding}{tail}')
                payload['JobInfo']['OutputFilename' + str(expIndex)] = outputFile
                OutputFilenames[expIndex] = outputFile
                expIndex += 1
        else:
            col = clique.assemble(files)[0][0]
            outputFile = col.format('{head}{padding}{tail}')
            payload['JobInfo']['OutputFilename' + str(expIndex)] = outputFile
            # OutputFilenames[expIndex] = outputFile


        # We need those to pass them to pype for it to set correct context
        keys = [
            "FTRACK_API_KEY",
            "FTRACK_API_USER",
            "FTRACK_SERVER",
            "AVALON_PROJECT",
            "AVALON_ASSET",
            "AVALON_TASK",
            "PYPE_USERNAME"
        ]

        environment = dict({key: os.environ[key] for key in keys
                            if key in os.environ}, **api.Session)

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

        self.log.info("Submitting ...")
        self.log.info(json.dumps(payload, indent=4, sort_keys=True))

        # E.g. http://192.168.0.1:8082/api/jobs
        url = "{}/api/jobs".format(DEADLINE_REST_URL)
        response = self._requests_post(url, json=payload)
        if not response.ok:
            raise Exception(response.text)

        # Store output dir for unified publisher (filesequence)
        instance.data["outputDir"] = os.path.dirname(output_filename_0)
        instance.data["deadlineSubmissionJob"] = response.json()

    def preflight_check(self, instance):
        """Ensure the startFrame, endFrame and byFrameStep are integers"""

        for key in ("frameStart", "frameEnd", "byFrameStep"):
            value = instance.data[key]

            if int(value) == value:
                continue

            self.log.warning(
                "%f=%d was rounded off to nearest integer"
                % (value, int(value))
            )

    def _requests_post(self, *args, **kwargs):
        """ Wrapper for requests, disabling SSL certificate validation if
            DONT_VERIFY_SSL environment variable is found. This is useful when
            Deadline or Muster server are running with self-signed certificates
            and their certificate is not added to trusted certificates on
            client machines.

            WARNING: disabling SSL certificate validation is defeating one line
            of defense SSL is providing and it is not recommended.
        """
        if 'verify' not in kwargs:
            kwargs['verify'] = False if os.getenv("PYPE_DONT_VERIFY_SSL", True) else True  # noqa
        return requests.post(*args, **kwargs)

    def _requests_get(self, *args, **kwargs):
        """ Wrapper for requests, disabling SSL certificate validation if
            DONT_VERIFY_SSL environment variable is found. This is useful when
            Deadline or Muster server are running with self-signed certificates
            and their certificate is not added to trusted certificates on
            client machines.

            WARNING: disabling SSL certificate validation is defeating one line
            of defense SSL is providing and it is not recommended.
        """
        if 'verify' not in kwargs:
            kwargs['verify'] = False if os.getenv("PYPE_DONT_VERIFY_SSL", True) else True  # noqa
        return requests.get(*args, **kwargs)
