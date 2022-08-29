import os
from abc import ABCMeta, abstractmethod

import six

from openpype.lib import Logger
from openpype.modules import ModulesManager
from openpype.settings import get_project_settings
from openpype.settings.lib import get_site_local_overrides


@six.add_metaclass(ABCMeta)
class HostDirmap(object):
    """Abstract class for running dirmap on a workfile in a host.

    Dirmap is used to translate paths inside of host workfile from one
    OS to another. (Eg. arstist created workfile on Win, different artists
    opens same file on Linux.)

    Expects methods to be implemented inside of host:
        on_dirmap_enabled: run host code for enabling dirmap
        do_dirmap: run host code to do actual remapping
    """

    def __init__(
        self, host_name, project_name, project_settings=None, sync_module=None
    ):
        self.host_name = host_name
        self.project_name = project_name
        self._project_settings = project_settings
        self._sync_module = sync_module  # to limit reinit of Modules
        self._log = None
        self._mapping = None  # cache mapping

    @property
    def sync_module(self):
        if self._sync_module is None:
            manager = ModulesManager()
            self._sync_module = manager["sync_server"]
        return self._sync_module

    @property
    def project_settings(self):
        if self._project_settings is None:
            self._project_settings = get_project_settings(self.project_name)
        return self._project_settings

    @property
    def log(self):
        if self._log is None:
            self._log = Logger.get_logger(self.__class__.__name__)
        return self._log

    @abstractmethod
    def on_enable_dirmap(self):
        """Run host dependent operation for enabling dirmap if necessary."""
        pass

    @abstractmethod
    def dirmap_routine(self, source_path, destination_path):
        """Run host dependent remapping from source_path to destination_path"""
        pass

    def process_dirmap(self):
        # type: (dict) -> None
        """Go through all paths in Settings and set them using `dirmap`.

            If artists has Site Sync enabled, take dirmap mapping directly from
            Local Settings when artist is syncing workfile locally.

        Args:
            project_settings (dict): Settings for current project.
        """

        if not self._mapping:
            self._mapping = self.get_mappings(self.project_settings)
        if not self._mapping:
            return

        self.log.info("Processing directory mapping ...")
        self.on_enable_dirmap()
        self.log.info("mapping:: {}".format(self._mapping))

        for k, sp in enumerate(self._mapping["source-path"]):
            dst = self._mapping["destination-path"][k]
            try:
                print("{} -> {}".format(sp, dst))
                self.dirmap_routine(sp, dst)
            except IndexError:
                # missing corresponding destination path
                self.log.error((
                    "invalid dirmap mapping, missing corresponding"
                    " destination directory."
                ))
                break
            except RuntimeError:
                self.log.error(
                    "invalid path {} -> {}, mapping not registered".format(
                        sp, dst
                    )
                )
                continue

    def get_mappings(self, project_settings):
        """Get translation from source-path to destination-path.

            It checks if Site Sync is enabled and user chose to use local
            site, in that case configuration in Local Settings takes precedence
        """

        local_mapping = self._get_local_sync_dirmap(project_settings)
        dirmap_label = "{}-dirmap".format(self.host_name)
        if (
            not self.project_settings[self.host_name].get(dirmap_label)
            and not local_mapping
        ):
            return {}
        mapping_settings = self.project_settings[self.host_name][dirmap_label]
        mapping_enabled = mapping_settings["enabled"] or bool(local_mapping)
        if not mapping_enabled:
            return {}

        mapping = (
            local_mapping
            or mapping_settings["paths"]
            or {}
        )

        if (
            not mapping
            or not mapping.get("destination-path")
            or not mapping.get("source-path")
        ):
            return {}
        return mapping

    def _get_local_sync_dirmap(self, project_settings):
        """
            Returns dirmap if synch to local project is enabled.

            Only valid mapping is from roots of remote site to local site set
            in Local Settings.

            Args:
                project_settings (dict)
            Returns:
                dict : { "source-path": [XXX], "destination-path": [YYYY]}
        """

        mapping = {}

        if not project_settings["global"]["sync_server"]["enabled"]:
            return mapping

        project_name = os.getenv("AVALON_PROJECT")

        active_site = self.sync_module.get_local_normalized_site(
            self.sync_module.get_active_site(project_name))
        remote_site = self.sync_module.get_local_normalized_site(
            self.sync_module.get_remote_site(project_name))
        self.log.debug(
            "active {} - remote {}".format(active_site, remote_site)
        )

        if (
            active_site == "local"
            and project_name in self.sync_module.get_enabled_projects()
            and active_site != remote_site
        ):
            sync_settings = self.sync_module.get_sync_project_setting(
                project_name,
                exclude_locals=False,
                cached=False)

            active_overrides = get_site_local_overrides(
                project_name, active_site)
            remote_overrides = get_site_local_overrides(
                project_name, remote_site)

            self.log.debug("local overrides {}".format(active_overrides))
            self.log.debug("remote overrides {}".format(remote_overrides))
            for root_name, active_site_dir in active_overrides.items():
                remote_site_dir = (
                    remote_overrides.get(root_name)
                    or sync_settings["sites"][remote_site]["root"][root_name]
                )
                if os.path.isdir(active_site_dir):
                    if "destination-path" not in mapping:
                        mapping["destination-path"] = []
                    mapping["destination-path"].append(active_site_dir)

                    if "source-path" not in mapping:
                        mapping["source-path"] = []
                    mapping["source-path"].append(remote_site_dir)

            self.log.debug("local sync mapping:: {}".format(mapping))
        return mapping
