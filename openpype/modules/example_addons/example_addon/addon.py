"""Addon definition is located here.

Import of python packages that may not be available should not be imported
in global space here until are required or used.
- Qt related imports
- imports of Python 3 packages
    - we still support Python 2 hosts where addon definition should available
"""

import os

from openpype.modules import (
    JsonFilesSettingsDef,
    OpenPypeAddOn
)
# Import interface defined by this addon to be able find other addons using it
from openpype_interfaces import (
    IExampleInterface,
    IPluginPaths,
    ITrayAction
)


# Settings definiton of this addon using `JsonFilesSettingsDef`
# - JsonFilesSettingsDef is prepared settings definiton using json files
#   to define settings and store defaul values
class AddonSettingsDef(JsonFilesSettingsDef):
    # This will add prefix to every schema and template from `schemas`
    #   subfolder.
    # - it is not required to fill the prefix but it is highly
    #   recommended as schemas and templates may have name clashes across
    #   multiple addons
    # - it is also recommended that prefix has addon name in it
    schema_prefix = "addon_with_settings"

    def get_settings_root_path(self):
        """Implemented abstract class of JsonFilesSettingsDef.

        Return directory path where json files defying addon settings are
        located.
        """
        return os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "settings"
        )


class ExampleAddon(OpenPypeAddOn, IPluginPaths, ITrayAction):
    """This Addon has defined it's settings and interface.

    This example has system settings with enabled option. And use
    few other interfaces:
    - `IPluginPaths` to define custom plugin paths
    - `ITrayAction` to be shown in tray tool
    """
    label = "Example Addon"
    name = "example_addon"

    def initialize(self, settings):
        """Initialization of addon."""
        module_settings = settings[self.name]
        # Enabled by settings
        self.enabled = module_settings.get("enabled", False)

        # Prepare variables that can be used or set afterwards
        self._connected_modules = None
        # UI which must not be created at this time
        self._dialog = None

    def connect_with_modules(self, enabled_modules):
        """Method where you should find connected modules.

        It is triggered by OpenPype modules manager at the best possible time.
        Some addons and modules may required to connect with other modules
        before their main logic is executed so changes would require to restart
        whole process.
        """
        self._connected_modules = []
        for module in enabled_modules:
            if isinstance(module, IExampleInterface):
                self._connected_modules.append(module)

    def _create_dialog(self):
        # Don't recreate dialog if already exists
        if self._dialog is not None:
            return

        from .widgets import MyExampleDialog

        self._dialog = MyExampleDialog()

    def show_dialog(self):
        """Show dialog with connected modules.

        This can be called from anywhere but can also crash in headless mode.
        There is not way how to prevent addon to do invalid operations if he's
        not handling them.
        """
        # Make sure dialog is created
        self._create_dialog()
        # Change value of dialog by current state
        self._dialog.set_connected_modules(self.get_connected_modules())
        # Show dialog
        self._dialog.open()

    def get_connected_modules(self):
        """Custom implementation of addon."""
        names = set()
        if self._connected_modules is not None:
            for module in self._connected_modules:
                names.add(module.name)
        return names

    def on_action_trigger(self):
        """Implementation of abstract method for `ITrayAction`."""
        self.show_dialog()

    def get_plugin_paths(self):
        """Implementation of abstract method for `IPluginPaths`."""
        current_dir = os.path.dirname(os.path.abspath(__file__))

        return {
            "publish": [os.path.join(current_dir, "plugins", "publish")]
        }
