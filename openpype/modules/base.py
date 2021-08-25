# -*- coding: utf-8 -*-
"""Base class for Pype Modules."""
import os
import sys
import time
import inspect
import logging
import threading
import collections
from uuid import uuid4
from abc import ABCMeta, abstractmethod
import six

import openpype
from openpype.settings import get_system_settings
from openpype.lib import PypeLogger


# Inherit from `object` for Python 2 hosts
class _ModuleClass(object):
    """Fake module class for storing OpenPype modules.

    Object of this class can be stored to `sys.modules` and used for storing
    dynamically imported modules.
    """
    def __init__(self, name):
        # Call setattr on super class
        super(_ModuleClass, self).__setattr__("name", name)

        # Where modules and interfaces are stored
        super(_ModuleClass, self).__setattr__("__attributes__", dict())
        super(_ModuleClass, self).__setattr__("__defaults__", set())

        super(_ModuleClass, self).__setattr__("_log", None)

    def __getattr__(self, attr_name):
        if attr_name not in self.__attributes__:
            if attr_name in ("__path__"):
                return None
            raise ImportError("No module named {}.{}".format(
                self.name, attr_name
            ))
        return self.__attributes__[attr_name]

    def __iter__(self):
        for module in self.values():
            yield module

    def __setattr__(self, attr_name, value):
        if attr_name in self.__attributes__:
            self.log.warning(
                "Duplicated name \"{}\" in {}. Overriding.".format(
                    self.name, attr_name
                )
            )
        self.__attributes__[attr_name] = value

    def __setitem__(self, key, value):
        self.__setattr__(key, value)

    def __getitem__(self, key):
        return getattr(self, key)

    @property
    def log(self):
        if self._log is None:
            super(_ModuleClass, self).__setattr__(
                "_log", PypeLogger.get_logger(self.name)
            )
        return self._log

    def get(self, key, default=None):
        return self.__attributes__.get(key, default)

    def keys(self):
        return self.__attributes__.keys()

    def values(self):
        return self.__attributes__.values()

    def items(self):
        return self.__attributes__.items()


class _InterfacesClass(_ModuleClass):
    """Fake module class for storing OpenPype interfaces.

    MissingInterface object is returned if interfaces does not exists.
    - this is because interfaces must be available even if are missing
        implementation
    """
    def __getattr__(self, attr_name):
        if attr_name not in self.__attributes__:
            # Fake Interface if is not missing
            self.__attributes__[attr_name] = type(
                attr_name,
                (MissingInteface, ),
                {}
            )

        return self.__attributes__[attr_name]


class _LoadCache:
    interfaces_lock = threading.Lock()
    modules_lock = threading.Lock()
    interfaces_loaded = False
    modules_loaded = False


def get_default_modules_dir():
    """Path to default OpenPype modules."""
    current_dir = os.path.abspath(os.path.dirname(__file__))

    return os.path.join(current_dir, "default_modules")


def get_module_dirs():
    """List of paths where OpenPype modules can be found."""
    dirpaths = [
        get_default_modules_dir()
    ]
    return dirpaths


def load_interfaces(force=False):
    """Load interfaces from modules into `openpype_interfaces`.

    Only classes which inherit from `OpenPypeInterface` are loaded and stored.

    Args:
        force(bool): Force to load interfaces even if are already loaded.
            This won't update already loaded and used (cached) interfaces.
    """

    if _LoadCache.interfaces_loaded and not force:
        return

    if not _LoadCache.interfaces_lock.locked():
        with _LoadCache.interfaces_lock:
            _load_interfaces()
            _LoadCache.interfaces_loaded = True
    else:
        # If lock is locked wait until is finished
        while _LoadCache.interfaces_lock.locked():
            time.sleep(0.1)


def _load_interfaces():
    # Key under which will be modules imported in `sys.modules`
    from openpype.lib import import_filepath

    modules_key = "openpype_interfaces"

    sys.modules[modules_key] = openpype_interfaces = (
        _InterfacesClass(modules_key)
    )

    log = PypeLogger.get_logger("InterfacesLoader")

    dirpaths = get_module_dirs()

    interface_paths = []
    interface_paths.append(
        os.path.join(get_default_modules_dir(), "interfaces.py")
    )
    for dirpath in dirpaths:
        for filename in os.listdir(dirpath):
            if filename in ("__pycache__", ):
                continue

            full_path = os.path.join(dirpath, filename)
            if not os.path.isdir(full_path):
                continue

            interfaces_path = os.path.join(full_path, "interfaces.py")
            if os.path.exists(interfaces_path):
                interface_paths.append(interfaces_path)

    for full_path in interface_paths:
        if not os.path.exists(full_path):
            continue

        try:
            # Prepare module object where content of file will be parsed
            module = import_filepath(full_path)

        except Exception:
            log.warning(
                "Failed to load path: \"{0}\"".format(full_path),
                exc_info=True
            )
            continue

        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if (
                not inspect.isclass(attr)
                or attr is OpenPypeInterface
                or not issubclass(attr, OpenPypeInterface)
            ):
                continue
            setattr(openpype_interfaces, attr_name, attr)


def load_modules(force=False):
    """Load OpenPype modules as python modules.

    Modules does not load only classes (like in Interfaces) because there must
    be ability to use inner code of module and be able to import it from one
    defined place.

    With this it is possible to import module's content from predefined module.

    Function makes sure that `load_interfaces` was triggered. Modules import
    has specific order which can't be changed.

    Args:
        force(bool): Force to load modules even if are already loaded.
            This won't update already loaded and used (cached) modules.
    """

    if _LoadCache.modules_loaded and not force:
        return

    # First load interfaces
    # - modules must not be imported before interfaces
    load_interfaces(force)

    if not _LoadCache.modules_lock.locked():
        with _LoadCache.modules_lock:
            _load_modules()
            _LoadCache.modules_loaded = True
    else:
        # If lock is locked wait until is finished
        while _LoadCache.modules_lock.locked():
            time.sleep(0.1)


def _load_modules():
    # Import helper functions from lib
    from openpype.lib import (
        import_filepath,
        import_module_from_dirpath
    )

    # Key under which will be modules imported in `sys.modules`
    modules_key = "openpype_modules"

    # Change `sys.modules`
    sys.modules[modules_key] = openpype_modules = _ModuleClass(modules_key)

    log = PypeLogger.get_logger("ModulesLoader")

    # Look for OpenPype modules in paths defined with `get_module_dirs`
    dirpaths = get_module_dirs()

    for dirpath in dirpaths:
        if not os.path.exists(dirpath):
            log.warning((
                "Could not find path when loading OpenPype modules \"{}\""
            ).format(dirpath))
            continue

        for filename in os.listdir(dirpath):
            # Ignore filenames
            if filename in ("__pycache__", ):
                continue

            fullpath = os.path.join(dirpath, filename)
            basename, ext = os.path.splitext(filename)

            # TODO add more logic how to define if folder is module or not
            # - check manifest and content of manifest
            if os.path.isdir(fullpath):
                import_module_from_dirpath(dirpath, filename, modules_key)

            elif ext in (".py", ):
                module = import_filepath(fullpath)
                setattr(openpype_modules, basename, module)


class _OpenPypeInterfaceMeta(ABCMeta):
    """OpenPypeInterface meta class to print proper string."""
    def __str__(self):
        return "<'OpenPypeInterface.{}'>".format(self.__name__)

    def __repr__(self):
        return str(self)


@six.add_metaclass(_OpenPypeInterfaceMeta)
class OpenPypeInterface:
    """Base class of Interface that can be used as Mixin with abstract parts.

    This is way how OpenPype module or addon can tell that has implementation
    for specific part or for other module/addon.

    Child classes of OpenPypeInterface may be used as mixin in different
    OpenPype modules which means they have to have implemented methods defined
    in the interface. By default interface does not have any abstract parts.
    """
    pass


class MissingInteface(OpenPypeInterface):
    """Class representing missing interface class.

    Used when interface is not available from currently registered paths.
    """
    pass


@six.add_metaclass(ABCMeta)
class OpenPypeModule:
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

        self.log = PypeLogger.get_logger(self.name)

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


class OpenPypeAddOn(OpenPypeModule):
    pass


class ModulesManager:
    """Manager of Pype modules helps to load and prepare them to work.

    Args:
        modules_settings(dict): To be able create module manager with specified
            data. For settings changes callbacks and testing purposes.
    """
    # Helper attributes for report
    _report_total_key = "Total"

    def __init__(self, _system_settings=None):
        self.log = logging.getLogger(self.__class__.__name__)

        self._system_settings = _system_settings

        self.modules = []
        self.modules_by_id = {}
        self.modules_by_name = {}
        # For report of time consumption
        self._report = {}

        self.initialize_modules()
        self.connect_modules()

    def initialize_modules(self):
        """Import and initialize modules."""
        # Make sure modules are loaded
        load_modules()

        import openpype_modules

        self.log.debug("*** Pype modules initialization.")
        # Prepare settings for modules
        system_settings = getattr(self, "_system_settings", None)
        if system_settings is None:
            system_settings = get_system_settings()
        modules_settings = system_settings["modules"]

        report = {}
        time_start = time.time()
        prev_start_time = time_start

        module_classes = []
        for module in openpype_modules:
            # Go through globals in `pype.modules`
            for name in dir(module):
                modules_item = getattr(module, name, None)
                # Filter globals that are not classes which inherit from
                #   OpenPypeModule
                if (
                    not inspect.isclass(modules_item)
                    or modules_item is OpenPypeModule
                    or not issubclass(modules_item, OpenPypeModule)
                ):
                    continue

                # Check if class is abstract (Developing purpose)
                if inspect.isabstract(modules_item):
                    # Find missing implementations by convetion on `abc` module
                    not_implemented = []
                    for attr_name in dir(modules_item):
                        attr = getattr(modules_item, attr_name, None)
                        abs_method = getattr(
                            attr, "__isabstractmethod__", None
                        )
                        if attr and abs_method:
                            not_implemented.append(attr_name)

                    # Log missing implementations
                    self.log.warning((
                        "Skipping abstract Class: {}."
                        " Missing implementations: {}"
                    ).format(name, ", ".join(not_implemented)))
                    continue
                module_classes.append(modules_item)

        for modules_item in module_classes:
            try:
                name = modules_item.__name__
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

                now = time.time()
                report[module.__class__.__name__] = now - prev_start_time
                prev_start_time = now

            except Exception:
                self.log.warning(
                    "Initialization of module {} failed.".format(name),
                    exc_info=True
                )

        if self._report is not None:
            report[self._report_total_key] = time.time() - time_start
            self._report["Initialization"] = report

    def connect_modules(self):
        """Trigger connection with other enabled modules.

        Modules should handle their interfaces in `connect_with_modules`.
        """
        report = {}
        time_start = time.time()
        prev_start_time = time_start
        enabled_modules = self.get_enabled_modules()
        self.log.debug("Has {} enabled modules.".format(len(enabled_modules)))
        for module in enabled_modules:
            try:
                module.connect_with_modules(enabled_modules)
            except Exception:
                self.log.error(
                    "BUG: Module failed on connection with other modules.",
                    exc_info=True
                )

            now = time.time()
            report[module.__class__.__name__] = now - prev_start_time
            prev_start_time = now

        if self._report is not None:
            report[self._report_total_key] = time.time() - time_start
            self._report["Connect modules"] = report

    def get_enabled_modules(self):
        """Enabled modules initialized by the manager.

        Returns:
            list: Initialized and enabled modules.
        """
        return [
            module
            for module in self.modules
            if module.enabled
        ]

    def collect_global_environments(self):
        """Helper to collect global enviornment variabled from modules.

        Returns:
            dict: Global environment variables from enabled modules.

        Raises:
            AssertionError: Gobal environment variables must be unique for
                all modules.
        """
        module_envs = {}
        for module in self.get_enabled_modules():
            # Collect global module's global environments
            _envs = module.get_global_environments()
            for key, value in _envs.items():
                if key in module_envs:
                    # TODO better error message
                    raise AssertionError(
                        "Duplicated environment key {}".format(key)
                    )
                module_envs[key] = value
        return module_envs

    def collect_plugin_paths(self):
        """Helper to collect all plugins from modules inherited IPluginPaths.

        Unknown keys are logged out.

        Returns:
            dict: Output is dictionary with keys "publish", "create", "load"
                and "actions" each containing list of paths.
        """
        # Output structure
        from openpype_interfaces import IPluginPaths

        output = {
            "publish": [],
            "create": [],
            "load": [],
            "actions": []
        }
        unknown_keys_by_module = {}
        for module in self.get_enabled_modules():
            # Skip module that do not inherit from `IPluginPaths`
            if not isinstance(module, IPluginPaths):
                continue
            plugin_paths = module.get_plugin_paths()
            for key, value in plugin_paths.items():
                # Filter unknown keys
                if key not in output:
                    if module.name not in unknown_keys_by_module:
                        unknown_keys_by_module[module.name] = []
                    unknown_keys_by_module[module.name].append(key)
                    continue

                # Skip if value is empty
                if not value:
                    continue

                # Convert to list if value is not list
                if not isinstance(value, (list, tuple, set)):
                    value = [value]
                output[key].extend(value)

        # Report unknown keys (Developing purposes)
        if unknown_keys_by_module:
            expected_keys = ", ".join([
                "\"{}\"".format(key) for key in output.keys()
            ])
            msg_template = "Module: \"{}\" - got key {}"
            msg_items = []
            for module_name, keys in unknown_keys_by_module.items():
                joined_keys = ", ".join([
                    "\"{}\"".format(key) for key in keys
                ])
                msg_items.append(msg_template.format(module_name, joined_keys))
            self.log.warning((
                "Expected keys from `get_plugin_paths` are {}. {}"
            ).format(expected_keys, " | ".join(msg_items)))
        return output

    def collect_launch_hook_paths(self):
        """Helper to collect hooks from modules inherited ILaunchHookPaths.

        Returns:
            list: Paths to launch hook directories.
        """
        from openpype_interfaces import ILaunchHookPaths

        str_type = type("")
        expected_types = (list, tuple, set)

        output = []
        for module in self.get_enabled_modules():
            # Skip module that do not inherit from `ILaunchHookPaths`
            if not isinstance(module, ILaunchHookPaths):
                continue

            hook_paths = module.get_launch_hook_paths()
            if not hook_paths:
                continue

            # Convert string to list
            if isinstance(hook_paths, str_type):
                hook_paths = [hook_paths]

            # Skip invalid types
            if not isinstance(hook_paths, expected_types):
                self.log.warning((
                    "Result of `get_launch_hook_paths`"
                    " has invalid type {}. Expected {}"
                ).format(type(hook_paths), expected_types))
                continue

            output.extend(hook_paths)
        return output

    def print_report(self):
        """Print out report of time spent on modules initialization parts.

        Reporting is not automated must be implemented for each initialization
        part separatelly. Reports must be stored to `_report` attribute.
        Print is skipped if `_report` is empty.

        Attribute `_report` is dictionary where key is "label" describing
        the processed part and value is dictionary where key is module's
        class name and value is time delta of it's processing.

        It is good idea to add total time delta on processed part under key
        which is defined in attribute `_report_total_key`. By default has value
        `"Total"` but use the attribute please.

        ```javascript
        {
            "Initialization": {
                "FtrackModule": 0.003,
                ...
                "Total": 1.003,
            },
            ...
        }
        ```
        """
        if not self._report:
            return

        available_col_names = set()
        for module_names in self._report.values():
            available_col_names |= set(module_names.keys())

        # Prepare ordered dictionary for columns
        cols = collections.OrderedDict()
        # Add module names to first columnt
        cols["Module name"] = list(sorted(
            module.__class__.__name__
            for module in self.modules
            if module.__class__.__name__ in available_col_names
        ))
        # Add total key (as last module)
        cols["Module name"].append(self._report_total_key)

        # Add columns from report
        for label in self._report.keys():
            cols[label] = []

        total_module_times = {}
        for module_name in cols["Module name"]:
            total_module_times[module_name] = 0

        for label, reported in self._report.items():
            for module_name in cols["Module name"]:
                col_time = reported.get(module_name)
                if col_time is None:
                    cols[label].append("N/A")
                    continue
                cols[label].append("{:.3f}".format(col_time))
                total_module_times[module_name] += col_time

        # Add to also total column that should sum the row
        cols[self._report_total_key] = []
        for module_name in cols["Module name"]:
            cols[self._report_total_key].append(
                "{:.3f}".format(total_module_times[module_name])
            )

        # Prepare column widths and total row count
        # - column width is by
        col_widths = {}
        total_rows = None
        for key, values in cols.items():
            if total_rows is None:
                total_rows = 1 + len(values)
            max_width = len(key)
            for value in values:
                value_length = len(value)
                if value_length > max_width:
                    max_width = value_length
            col_widths[key] = max_width

        rows = []
        for _idx in range(total_rows):
            rows.append([])

        for key, values in cols.items():
            width = col_widths[key]
            idx = 0
            rows[idx].append(key.ljust(width))
            for value in values:
                idx += 1
                rows[idx].append(value.ljust(width))

        filler_parts = []
        for width in col_widths.values():
            filler_parts.append(width * "-")
        filler = "+".join(filler_parts)

        formatted_rows = [filler]
        last_row_idx = len(rows) - 1
        for idx, row in enumerate(rows):
            # Add filler before last row
            if idx == last_row_idx:
                formatted_rows.append(filler)

            formatted_rows.append("|".join(row))

            # Add filler after first row
            if idx == 0:
                formatted_rows.append(filler)

        # Join rows with newline char and add new line at the end
        output = "\n".join(formatted_rows) + "\n"
        print(output)


class TrayModulesManager(ModulesManager):
    # Define order of modules in menu
    modules_menu_order = (
        "user",
        "ftrack",
        "muster",
        "launcher_tool",
        "avalon",
        "clockify",
        "standalonepublish_tool",
        "log_viewer",
        "local_settings",
        "settings"
    )

    def __init__(self):
        self.log = PypeLogger.get_logger(self.__class__.__name__)

        self.modules = []
        self.modules_by_id = {}
        self.modules_by_name = {}
        self._report = {}

        self.tray_manager = None

        self.doubleclick_callbacks = {}
        self.doubleclick_callback = None

    def add_doubleclick_callback(self, module, callback):
        """Register doubleclick callbacks on tray icon.

        Currently there is no way how to determine which is launched. Name of
        callback can be defined with `doubleclick_callback` attribute.

        Missing feature how to define default callback.
        """
        callback_name = "_".join([module.name, callback.__name__])
        if callback_name not in self.doubleclick_callbacks:
            self.doubleclick_callbacks[callback_name] = callback
            if self.doubleclick_callback is None:
                self.doubleclick_callback = callback_name
            return

        self.log.warning((
            "Callback with name \"{}\" is already registered."
        ).format(callback_name))

    def initialize(self, tray_manager, tray_menu):
        self.tray_manager = tray_manager
        self.initialize_modules()
        self.tray_init()
        self.connect_modules()
        self.tray_menu(tray_menu)

    def get_enabled_tray_modules(self):
        from openpype_interfaces import ITrayModule

        output = []
        for module in self.modules:
            if module.enabled and isinstance(module, ITrayModule):
                output.append(module)
        return output

    def restart_tray(self):
        if self.tray_manager:
            self.tray_manager.restart()

    def tray_init(self):
        report = {}
        time_start = time.time()
        prev_start_time = time_start
        for module in self.get_enabled_tray_modules():
            try:
                module._tray_manager = self.tray_manager
                module.tray_init()
                module.tray_initialized = True
            except Exception:
                self.log.warning(
                    "Module \"{}\" crashed on `tray_init`.".format(
                        module.name
                    ),
                    exc_info=True
                )

            now = time.time()
            report[module.__class__.__name__] = now - prev_start_time
            prev_start_time = now

        if self._report is not None:
            report[self._report_total_key] = time.time() - time_start
            self._report["Tray init"] = report

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

        report = {}
        time_start = time.time()
        prev_start_time = time_start
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
            now = time.time()
            report[module.__class__.__name__] = now - prev_start_time
            prev_start_time = now

        if self._report is not None:
            report[self._report_total_key] = time.time() - time_start
            self._report["Tray menu"] = report

    def start_modules(self):
        from openpype_interfaces import ITrayService

        report = {}
        time_start = time.time()
        prev_start_time = time_start
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
            now = time.time()
            report[module.__class__.__name__] = now - prev_start_time
            prev_start_time = now

        if self._report is not None:
            report[self._report_total_key] = time.time() - time_start
            self._report["Modules start"] = report

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
