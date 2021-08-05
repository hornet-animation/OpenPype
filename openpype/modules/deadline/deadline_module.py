import os
from openpype.modules import (
    PypeModule, IPluginPaths)


class DeadlineModule(PypeModule, IPluginPaths):
    name = "deadline"

    def initialize(self, modules_settings):
        # This module is always enabled
        deadline_settings = modules_settings[self.name]
        self.enabled = deadline_settings["enabled"]
        deadline_url = deadline_settings.get("DEADLINE_REST_URL")
        if not deadline_url:
            deadline_url = deadline_settings.get("deadline_urls", {}).get("default")  # noqa: E501
        if not deadline_url:
            self.enabled = False
            self.log.warning(("default Deadline Webservice URL "
                              "not specified. Disabling module."))
            return
        self.deadline_url = deadline_url

    def get_global_environments(self):
        """Deadline global environments for OpenPype implementation."""
        return {
            "DEADLINE_REST_URL": self.deadline_url
        }

    def connect_with_modules(self, *_a, **_kw):
        return

    def get_plugin_paths(self):
        """Deadline plugin paths."""
        current_dir = os.path.dirname(os.path.abspath(__file__))
        return {
            "publish": [os.path.join(current_dir, "plugins", "publish")]
        }
