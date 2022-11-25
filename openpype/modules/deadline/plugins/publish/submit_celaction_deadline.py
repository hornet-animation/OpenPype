import os
import re
import json
import getpass

import requests
import pyblish.api
from openpype.pipeline import legacy_io

class CelactionSubmitDeadline(pyblish.api.InstancePlugin):
    """Submit CelAction2D scene to Deadline

    Renders are submitted to a Deadline Web Service.

    """

    label = "Submit CelAction to Deadline"
    order = pyblish.api.IntegratorOrder + 0.1
    hosts = ["celaction"]
    families = ["render.farm"]

    deadline_department = ""
    deadline_priority = 50
    deadline_pool = ""
    deadline_pool_secondary = ""
    deadline_group = ""
    deadline_chunk_size = 1
    deadline_job_delay = "00:00:08:00"

    def process(self, instance):
        instance.data["toBeRenderedOn"] = "deadline"
        context = instance.context

        # get default deadline webservice url from deadline module
        deadline_url = instance.context.data["defaultDeadline"]
        # if custom one is set in instance, use that
        if instance.data.get("deadlineUrl"):
            deadline_url = instance.data.get("deadlineUrl")
        assert deadline_url, "Requires Deadline Webservice URL"

        self.deadline_url = "{}/api/jobs".format(deadline_url)
        self._comment = context.data.get("comment", "")
        self._deadline_user = context.data.get(
            "deadlineUser", getpass.getuser())
        self._frame_start = int(instance.data["frameStart"])
        self._frame_end = int(instance.data["frameEnd"])

        # get output path
        render_path = instance.data['path']
        script_path = context.data["currentFile"]

        response = self.payload_submit(instance,
                                       script_path,
                                       render_path
                                       )
        # Store output dir for unified publisher (filesequence)
        instance.data["deadlineSubmissionJob"] = response.json()

        instance.data["outputDir"] = os.path.dirname(
            render_path).replace("\\", "/")

        instance.data["publishJobState"] = "Suspended"
        instance.context.data['ftrackStatus'] = "Render"

        # adding 2d render specific family for version identification in Loader
        instance.data["families"] = ["render2d"]

    def payload_submit(self,
                       instance,
                       script_path,
                       render_path
                       ):
        resolution_width = instance.data["resolutionWidth"]
        resolution_height = instance.data["resolutionHeight"]
        render_dir = os.path.normpath(os.path.dirname(render_path))
        render_path = os.path.normpath(render_path)
        script_name = os.path.basename(script_path)

        for item in instance.context:
            if "workfile" in item.data["family"]:
                msg = "Workfile (scene) must be published along"
                assert item.data["publish"] is True, msg

                template_data = item.data.get("anatomyData")
                rep = item.data.get("representations")[0].get("name")
                template_data["representation"] = rep
                template_data["ext"] = rep
                template_data["comment"] = None
                anatomy_filled = instance.context.data["anatomy"].format(
                    template_data)
                template_filled = anatomy_filled["publish"]["path"]
                script_path = os.path.normpath(template_filled)

                self.log.info(
                    "Using published scene for render {}".format(script_path)
                )

        jobname = "%s - %s" % (script_name, instance.name)

        output_filename_0 = self.preview_fname(render_path)

        try:
            # Ensure render folder exists
            os.makedirs(render_dir)
        except OSError:
            pass

        # define chunk and priority
        chunk_size = instance.context.data.get("chunk")
        if chunk_size == 0:
            chunk_size = self.deadline_chunk_size

        # search for %02d pattern in name, and padding number
        search_results = re.search(r"(%0)(\d)(d)[._]", render_path).groups()
        split_patern = "".join(search_results)
        padding_number = int(search_results[1])

        args = [
            f"<QUOTE>{script_path}<QUOTE>",
            "-a",
            "-16",
            "-s <STARTFRAME>",
            "-e <ENDFRAME>",
            f"-d <QUOTE>{render_dir}<QUOTE>",
            f"-x {resolution_width}",
            f"-y {resolution_height}",
            f"-r <QUOTE>{render_path.replace(split_patern, '')}<QUOTE>",
            f"-= AbsoluteFrameNumber=on -= PadDigits={padding_number}",
            "-= ClearAttachment=on",
        ]

        payload = {
            "JobInfo": {
                # Job name, as seen in Monitor
                "Name": jobname,

                # plugin definition
                "Plugin": "CelAction",

                # Top-level group name
                "BatchName": script_name,

                # Arbitrary username, for visualisation in Monitor
                "UserName": self._deadline_user,

                "Department": self.deadline_department,
                "Priority": self.deadline_priority,

                "Group": self.deadline_group,
                "Pool": self.deadline_pool,
                "SecondaryPool": self.deadline_pool_secondary,
                "ChunkSize": chunk_size,

                "Frames": f"{self._frame_start}-{self._frame_end}",
                "Comment": self._comment,

                # Optional, enable double-click to preview rendered
                # frames from Deadline Monitor
                "OutputFilename0": output_filename_0.replace("\\", "/"),

                # # Asset dependency to wait for at least
                # the scene file to sync.
                # "AssetDependency0": script_path
                "ScheduledType": "Once",
                "JobDelay": self.deadline_job_delay
            },
            "PluginInfo": {
                # Input
                "SceneFile": script_path,

                # Output directory
                "OutputFilePath": render_dir.replace("\\", "/"),

                # Plugin attributes
                "StartupDirectory": "",
                "Arguments": " ".join(args),

                # Resolve relative references
                "ProjectPath": script_path,
                "AWSAssetFile0": render_path,
            },

            # Mandatory for Deadline, may be empty
            "AuxFiles": []
        }

        plugin = payload["JobInfo"]["Plugin"]
        self.log.info("using render plugin : {}".format(plugin))

        # Include critical environment variables with submission
        keys = [
            "PYTHONPATH",
            "PATH",
            "AVALON_PROJECT",
            "AVALON_ASSET",
            "AVALON_TASK",
            "AVALON_APP_NAME",
            "FTRACK_API_KEY",
            "FTRACK_API_USER",
            "FTRACK_SERVER",
            "PYBLISHPLUGINPATH",
            "NUKE_PATH",
            "TOOL_ENV",
            "FOUNDRY_LICENSE",
            "OPENPYPE_VERSION"
        ]
        # Add mongo url if it's enabled
        if instance.context.data.get("deadlinePassMongoUrl"):
            keys.append("OPENPYPE_MONGO")

        # add allowed keys from preset if any
        if self.env_allowed_keys:
            keys += self.env_allowed_keys

        environment = dict({
            key: os.environ[key] for key in keys
            if key in os.environ}, **legacy_io.Session
        )

        for _path in os.environ:
            if _path.lower().startswith('openpype_'):
                environment[_path] = os.environ[_path]

        # to recognize job from OPENPYPE for turning Event On/Off
        environment.update({
            "OPENPYPE_LOG_NO_COLORS": "1",
            "OPENPYPE_RENDER_JOB": "1"
        })

        # finally search replace in values of any key
        if self.env_search_replace_values:
            for key, value in environment.items():
                for _k, _v in self.env_search_replace_values.items():
                    environment[key] = value.replace(_k, _v)

        payload["JobInfo"].update({
            "EnvironmentKeyValue%d" % index: "{key}={value}".format(
                key=key,
                value=environment[key]
            ) for index, key in enumerate(environment)
        })

        self.log.info("Submitting..")
        self.log.info(json.dumps(payload, indent=4, sort_keys=True))

        # adding expectied files to instance.data
        self.expected_files(instance, render_path)
        self.log.debug("__ expectedFiles: `{}`".format(
            instance.data["expectedFiles"]))
        response = requests.post(self.deadline_url, json=payload)

        if not response.ok:
            raise Exception(response.text)

        return response

    def preflight_check(self, instance):
        """Ensure the startFrame, endFrame and byFrameStep are integers"""

        for key in ("frameStart", "frameEnd"):
            value = instance.data[key]

            if int(value) == value:
                continue

            self.log.warning(
                "%f=%d was rounded off to nearest integer"
                % (value, int(value))
            )

    def preview_fname(self, path):
        """Return output file path with #### for padding.

        Deadline requires the path to be formatted with # in place of numbers.
        For example `/path/to/render.####.png`

        Args:
            path (str): path to rendered images

        Returns:
            str

        """
        self.log.debug("_ path: `{}`".format(path))
        if "%" in path:
            search_results = re.search(r"[._](%0)(\d)(d)[._]", path).groups()
            split_patern = "".join(search_results)
            split_path = path.split(split_patern)
            hashes = "#" * int(search_results[1])
            return "".join([split_path[0], hashes, split_path[-1]])
        if "#" in path:
            self.log.debug("_ path: `{}`".format(path))
            return path
        else:
            return path

    def expected_files(self,
                       instance,
                       path):
        """ Create expected files in instance data
        """
        if not instance.data.get("expectedFiles"):
            instance.data["expectedFiles"] = list()

        dir = os.path.dirname(path)
        file = os.path.basename(path)

        if "#" in file:
            pparts = file.split("#")
            padding = "%0{}d".format(len(pparts) - 1)
            file = pparts[0] + padding + pparts[-1]

        if "%" not in file:
            instance.data["expectedFiles"].append(path)
            return

        for i in range(self._frame_start, (self._frame_end + 1)):
            instance.data["expectedFiles"].append(
                os.path.join(dir, (file % i)).replace("\\", "/"))
