# -*- coding: utf-8 -*-
"""Base class for Pype Modules."""
import inspect
import logging
from uuid import uuid4
from abc import ABCMeta, abstractmethod
import six

import pype
from pype.settings import get_system_settings
from pype.lib import PypeLogger
from pype import resources


@six.add_metaclass(ABCMeta)
class PypeModule:
    """Base class of pype module.

    Attributes:
        id (UUID): Module's id.
        enabled (bool): Is module enabled.
        name (str): Module name.
        manager (ModulesManager): Manager that created the module.
    """

    # Disable by default
    enabled = False
    _id = None

    @property
    @abstractmethod
    def name(self):
        """Module's name."""
        pass

    def __init__(self, manager, settings):
        self.manager = manager

        self.log = PypeLogger().get_logger(self.name)

        self.initialize(settings)

    @property
    def id(self):
        if self._id is None:
            self._id = uuid4()
        return self._id

    @abstractmethod
    def initialize(self, module_settings):
        """Initialization of module attributes.

        It is not recommended to override __init__ that's why specific method
        was implemented.
        """
        pass

    @abstractmethod
    def connect_with_modules(self, enabled_modules):
        """Connect with other enabled modules."""
        pass

    def get_global_environments(self):
        """Get global environments values of module.

        Environment variables that can be get only from system settings.
        """
        return {}


@six.add_metaclass(ABCMeta)
class IPluginPaths:
    """Module has plugin paths to return.

    Expected result is dictionary with keys "publish", "create", "load" or
    "actions" and values as list or string.
    {
        "publish": ["path/to/publish_plugins"]
    }
    """
    # TODO validation of an output
    @abstractmethod
    def get_plugin_paths(self):
        pass


@six.add_metaclass(ABCMeta)
class ITrayModule:
    """Module has special procedures when used in Pype Tray.

    IMPORTANT:
    The module still must be usable if is not used in tray even if
    would do nothing.
    """
    tray_initialized = False

    @abstractmethod
    def tray_init(self):
        """Initialization part of tray implementation.

        Triggered between `initialization` and `connect_with_modules`.

        This is where GUIs should be loaded or tray specific parts should be
        prepared.
        """
        pass

    @abstractmethod
    def tray_menu(self, tray_menu):
        """Add module's action to tray menu."""
        pass

    @abstractmethod
    def tray_start(self):
        """Start procedure in Pype tray."""
        pass

    @abstractmethod
    def tray_exit(self):
        """Cleanup method which is executed on tray shutdown.

        This is place where all threads should be shut.
        """
        pass


class ITrayService(ITrayModule):
    # Module's property
    menu_action = None

    # Class properties
    _services_submenu = None
    _icon_failed = None
    _icon_running = None
    _icon_idle = None

    @property
    @abstractmethod
    def label(self):
        """Service label showed in menu."""
        pass

    # TODO be able to get any sort of information to show/print
    # @abstractmethod
    # def get_service_info(self):
    #     pass

    @staticmethod
    def services_submenu(tray_menu):
        if ITrayService._services_submenu is None:
            from Qt import QtWidgets
            services_submenu = QtWidgets.QMenu("Services", tray_menu)
            services_submenu.setVisible(False)
            ITrayService._services_submenu = services_submenu
        return ITrayService._services_submenu

    @staticmethod
    def add_service_action(action):
        ITrayService._services_submenu.addAction(action)
        if not ITrayService._services_submenu.isVisible():
            ITrayService._services_submenu.setVisible(True)

    @staticmethod
    def _load_service_icons():
        from Qt import QtGui
        ITrayService._failed_icon = QtGui.QIcon(
            resources.get_resource("icons", "circle_red.png")
        )
        ITrayService._icon_running = QtGui.QIcon(
            resources.get_resource("icons", "circle_green.png")
        )
        ITrayService._icon_idle = QtGui.QIcon(
            resources.get_resource("icons", "circle_orange.png")
        )

    @staticmethod
    def get_icon_running():
        if ITrayService._icon_running is None:
            ITrayService._load_service_icons()
        return ITrayService._icon_running

    @staticmethod
    def get_icon_idle():
        if ITrayService._icon_idle is None:
            ITrayService._load_service_icons()
        return ITrayService._icon_idle

    @staticmethod
    def get_icon_failed():
        if ITrayService._failed_icon is None:
            ITrayService._load_service_icons()
        return ITrayService._failed_icon

    def tray_menu(self, tray_menu):
        from Qt import QtWidgets
        action = QtWidgets.QAction(
            self.label,
            self.services_submenu(tray_menu)
        )
        self.menu_action = action

        self.add_service_action(action)

        self.set_service_running_icon()

    def set_service_running_icon(self):
        """Change icon of an QAction to green circle."""
        if self.menu_action:
            self.menu_action.setIcon(self.get_icon_running())

    def set_service_failed_icon(self):
        """Change icon of an QAction to red circle."""
        if self.menu_action:
            self.menu_action.setIcon(self.get_icon_failed())

    def set_service_idle_icon(self):
        """Change icon of an QAction to orange circle."""
        if self.menu_action:
            self.menu_action.setIcon(self.get_icon_idle())


class ModulesManager:
    def __init__(self):
        self.log = logging.getLogger(self.__class__.__name__)

        self.modules = []
        self.modules_by_id = {}
        self.modules_by_name = {}

        self.initialize_modules()
        self.connect_modules()

    def initialize_modules(self):
        """Import and initialize modules."""
        self.log.debug("*** Pype modules initialization.")
        # Prepare settings for modules
        modules_settings = get_system_settings()["modules"]
        # Go through globals in `pype.modules`
        for name in dir(pype.modules):
            modules_item = getattr(pype.modules, name, None)
            # Filter globals that are not classes which inherit from PypeModule
            if (
                not inspect.isclass(modules_item)
                or modules_item is pype.modules.PypeModule
                or not issubclass(modules_item, pype.modules.PypeModule)
            ):
                continue

            # Check if class is abstract (Developing purpose)
            if inspect.isabstract(modules_item):
                # Find missing implementations by convetion on `abc` module
                not_implemented = []
                for attr_name in dir(modules_item):
                    attr = getattr(modules_item, attr_name, None)
                    if attr and getattr(attr, "__isabstractmethod__", None):
                        not_implemented.append(attr_name)

                # Log missing implementations
                self.log.warning((
                    "Skipping abstract Class: {}. Missing implementations: {}"
                ).format(name, ", ".join(not_implemented)))
                continue

            try:
                # Try initialize module
                module = modules_item(self, modules_settings)
                # Store initialized object
                self.modules.append(module)
                self.modules_by_id[module.id] = module
                self.modules_by_name[module.name] = module
                enabled_str = "X"
                if not module.enabled:
                    enabled_str = " "
                self.log.debug("[{}] {}".format(enabled_str, name))

            except Exception:
                self.log.warning(
                    "Initialization of module {} failed.".format(name),
                    exc_info=True
                )

    def connect_modules(self):
        """Trigger connection with other enabled modules.

        Modules should handle their interfaces in `connect_with_modules`.
        """
        enabled_modules = self.get_enabled_modules()
        self.log.debug("Has {} enabled modules.".format(len(enabled_modules)))
        for module in enabled_modules:
            module.connect_with_modules(enabled_modules)

    def get_enabled_modules(self):
        """Enabled modules initialized by the manager."""
        return [
            module
            for module in self.modules
            if module.enabled
        ]


class TrayModulesManager(ModulesManager):
    # Define order of modules in menu
    modules_menu_order = (
        "User setting",
        "Ftrack",
        "muster",
        "Avalon",
        "Clockify",
        "Standalone Publish",
        "Logging"
    )

    def __init__(self):
        self.log = PypeLogger().get_logger(self.__class__.__name__)

        self.modules = []
        self.modules_by_id = {}
        self.modules_by_name = {}

    def initialize(self, tray_menu):
        self.initialize_modules()
        self.tray_init()
        self.connect_modules()
        self.tray_menu(tray_menu)

    def get_enabled_tray_modules(self):
        output = []
        for module in self.modules:
            if module.enabled and isinstance(module, ITrayModule):
                output.append(module)
        return output

    def tray_init(self):
        for module in self.get_enabled_tray_modules():
            try:
                module.tray_init()
                module.tray_initialized = True
            except Exception:
                self.log.warning(
                    "Module \"{}\" crashed on `tray_init`.".format(
                        module.name
                    ),
                    exc_info=True
                )

    def tray_menu(self, tray_menu):
        ordered_modules = []
        enabled_by_name = {
            module.name: module
            for module in self.get_enabled_tray_modules()
        }

        for name in self.modules_menu_order:
            module_by_name = enabled_by_name.pop(name, None)
            if module_by_name:
                ordered_modules.append(module_by_name)
        ordered_modules.extend(enabled_by_name.values())

        for module in ordered_modules:
            if not module.tray_initialized:
                continue

            try:
                module.tray_menu(tray_menu)
            except Exception:
                # Unset initialized mark
                module.tray_initialized = False
                self.log.warning(
                    "Module \"{}\" crashed on `tray_menu`.".format(
                        module.name
                    ),
                    exc_info=True
                )

    def start_modules(self):
        for module in self.get_enabled_tray_modules():
            if not module.tray_initialized:
                if isinstance(module, ITrayService):
                    module.set_service_failed_icon()
                continue

            try:
                module.tray_start()
            except Exception:
                self.log.warning(
                    "Module \"{}\" crashed on `tray_start`.".format(
                        module.name
                    ),
                    exc_info=True
                )

    def on_exit(self):
        for module in self.get_enabled_tray_modules():
            if module.tray_initialized:
                try:
                    module.tray_exit()
                except Exception:
                    self.log.warning(
                        "Module \"{}\" crashed on `tray_exit`.".format(
                            module.name
                        ),
                        exc_info=True
                    )
