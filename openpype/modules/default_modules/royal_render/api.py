# -*- coding: utf-8 -*-
"""Wrapper around Royal Render API."""
import sys
import os

from openpype.settings import get_project_settings
from openpype.lib.local_settings import OpenPypeSettingsRegistry
from openpype.lib import PypeLogger
from .rr_job import RRJob, SubmitFile, SubmitterParameter


log = PypeLogger.get_logger("RoyalRender")


class Api:

    _settings = None
    RR_SUBMIT_CONSOLE = 1
    RR_SUBMIT_API = 2

    def __init__(self, settings):
        self._settings = settings

    def initialize_rr_modules(self, project=None):
        # type: (str) -> None

        is_64bit_python = sys.maxsize > 2 ** 32
        if project:
            project_settings = get_project_settings(project)
            rr_path = (
                project_settings
                ["royalrender"]
                ["rr_paths"]
            )
        else:
            rr_path = (
                self._settings
                ["modules"]
                ["royalrender"]
                ["rr_path"]
                ["default"]
            )

        # default for linux
        rr_module_path = "/bin/lx64/lib"

        if sys.platform.lower() == "win32":
            rr_module_path = "/bin/win64"
            if not is_64bit_python:
                # we are using 64bit python
                rr_module_path = "/bin/win"
            rr_module_path = rr_module_path.replace(
                "/", os.path.sep
            )

        if sys.platform.lower() == "darwin":
            rr_module_path = "/bin/mac64/lib/python/27"
            if not is_64bit_python:
                rr_module_path = "/bin/mac/lib/python/27"

        sys.path.append(os.path.join(rr_path, rr_module_path))
        os.environ["RR_ROOT"] = rr_path

    def create_submission(self, jobs, submitter_attributes, file_name=None):
        # type: (list[RRJob], list[SubmitterParameter], str) -> SubmitFile
        """Create jobs submission file.

        Args:
            jobs (list): List of :class:`RRJob`
            submitter_attributes (list): List of submitter attributes
                :class:`SubmitterParameter` for whole submission batch.
            file_name (str), optional): File path to write data to.

        Returns:
            str: XML data of job submission files.

        """
        raise NotImplementedError

    def submit_file(self, file, mode=RR_SUBMIT_CONSOLE):
        # type: (SubmitFile, int) -> None
        if mode == self.RR_SUBMIT_CONSOLE:
            self._submit_using_console(file)

        # RR v7 supports only Python 2.7 so we bail out in fear
        # until there is support for Python 3 😰
        raise NotImplementedError(
            "Submission via RoyalRender API is not supported yet")
        # self._submit_using_api(file)

    def _submit_using_console(self, file):
        # type: (SubmitFile) -> bool
        ...

    def _submit_using_api(self, file):
        # type: (SubmitFile) -> None
        """Use RR API to submit jobs.

        Args:
            file (SubmitFile): Submit jobs definition.

        Throws:
            RoyalRenderException: When something fails.

        """
        self.initialize_rr_modules()

        import libpyRR2 as rrLib
        from rrJob import getClass_JobBasics
        import libpyRR2 as _RenderAppBasic

        tcp = rrLib._rrTCP("")
        rr_server = tcp.getRRServer()

        if len(rr_server) == 0:
            log.info("Got RR IP address {}".format(rr_server))

        # TODO: Port is hardcoded in RR? If not, move it to Settings
        if not tcp.setServer(rr_server, 7773):
            log.error(
                "Can not set RR server: {}".format(tcp.errorMessage()))
            raise RoyalRenderException(tcp.errorMessage())

        # TODO: This need UI and better handling of username/password.
        # We can't store password in keychain as it is pulled multiple
        # times and users on linux must enter keychain password every time.
        # Probably best way until we setup our own user management would be
        # to encrypt password and save it to json locally. Not bulletproof
        # but at least it is not stored in plaintext.
        reg = OpenPypeSettingsRegistry()
        try:
            rr_user = reg.get_item("rr_username")
            rr_password = reg.get_item("rr_password")
        except ValueError:
            # user has no rr credentials set
            pass
        else:
            # login to RR
            tcp.setLogin(rr_user, rr_password)

        job = getClass_JobBasics()
        renderer = _RenderAppBasic()

        # iterate over SubmitFile, set _JobBasic (job) and renderer
        # and feed it to jobSubmitNew()
        # not implemented yet

        job.renderer = renderer

        tcp.jobSubmitNew(job)


class RoyalRenderException(Exception):
    """Exception used in various error states coming from RR."""
    pass
