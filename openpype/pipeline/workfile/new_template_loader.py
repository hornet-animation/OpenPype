import os
import collections
from abc import ABCMeta, abstractmethod

import six

from openpype.client import get_asset_by_name
from openpype.settings import get_project_settings
from openpype.host import HostBase
from openpype.lib import Logger, StringTemplate, filter_profiles
from openpype.pipeline import legacy_io, Anatomy
from openpype.pipeline.load import get_loaders_by_name
from openpype.pipeline.create import get_legacy_creator_by_name

from .build_template_exceptions import (
    TemplateProfileNotFound,
    TemplateLoadingFailed,
    TemplateNotFound,
)


@six.add_metaclass(ABCMeta)
class AbstractTemplateLoader:
    """Abstraction of Template Loader.

    Args:
        host (Union[HostBase, ModuleType]): Implementation of host.
    """

    _log = None

    def __init__(self, host):
        # Store host
        self._host = host
        if isinstance(host, HostBase):
            host_name = host.name
        else:
            host_name = os.environ.get("AVALON_APP")
        self._host_name = host_name

        # Shared data across placeholder plugins
        self._shared_data = {}

        # Where created objects of placeholder plugins will be stored
        self._placeholder_plugins = None

        project_name = legacy_io.active_project()
        asset_name = legacy_io.Session["AVALON_ASSET"]

        self.current_asset = asset_name
        self.project_name = project_name
        self.task_name = legacy_io.Session["AVALON_TASK"]
        self.current_asset_doc = get_asset_by_name(project_name, asset_name)
        self.task_type = (
            self.current_asset_doc
            .get("data", {})
            .get("tasks", {})
            .get(self.task_name, {})
            .get("type")
        )

    @abstractmethod
    def get_placeholder_plugin_classes(self):
        """Get placeholder plugin classes that can be used to build template.

        Returns:
            List[PlaceholderPlugin]: Plugin classes available for host.
        """

        return []

    @property
    def host(self):
        """Access to host implementation.

        Returns:
            Union[HostBase, ModuleType]: Implementation of host.
        """

        return self._host

    @property
    def host_name(self):
        """Name of 'host' implementation.

        Returns:
            str: Host's name.
        """

        return self._host_name

    @property
    def log(self):
        """Dynamically created logger for the plugin."""

        if self._log is None:
            self._log = Logger.get_logger(repr(self))
        return self._log

    def refresh(self):
        """Reset cached data."""

        self._placeholder_plugins = None
        self._loaders_by_name = None
        self._creators_by_name = None
        self.clear_shared_data()

    def clear_shared_data(self):
        """Clear shared data.

        Method only clear shared data to default state.
        """

        self._shared_data = {}

    def get_loaders_by_name(self):
        if self._loaders_by_name is None:
            self._loaders_by_name = get_loaders_by_name()
        return self._loaders_by_name

    def get_creators_by_name(self):
        if self._creators_by_name is None:
            self._creators_by_name = get_legacy_creator_by_name()
        return self._creators_by_name

    def get_shared_data(self, key):
        """Receive shared data across plugins and placeholders.

        This can be used to scroll scene only once to look for placeholder
        items if the storing is unified but each placeholder plugin would have
        to call it again.

        Shared data are cleaned up on specific callbacks.

        Args:
            key (str): Key under which are shared data stored.

        Returns:
            Union[None, Any]: None if key was not set.
        """

        return self._shared_data.get(key)

    def set_shared_data(self, key, value):
        """Store share data across plugins and placeholders.

        Store data that can be afterwards accessed from any future call. It
        is good practice to check if the same value is not already stored under
        different key or if the key is not already used for something else.

        Key should be self explanatory to content.
        - wrong: 'asset'
        - good: 'asset_name'

        Shared data are cleaned up on specific callbacks.

        Args:
            key (str): Key under which is key stored.
            value (Any): Value that should be stored under the key.
        """

        self._shared_data[key] = value

    @property
    def placeholder_plugins(self):
        """Access to initialized placeholder plugins.

        Returns:
            List[PlaceholderPlugin]: Initialized plugins available for host.
        """

        if self._placeholder_plugins is None:
            placeholder_plugins = {}
            for cls in self.get_placeholder_plugin_classes():
                try:
                    plugin = cls(self)
                    placeholder_plugins[plugin.identifier] = plugin

                except Exception:
                    self.log.warning(
                        "Failed to initialize placeholder plugin {}".format(
                            cls.__name__
                        )
                    )

            self._placeholder_plugins = placeholder_plugins
        return self._placeholder_plugins

    def get_placeholders(self):
        """Collect placeholder items from scene.

        Each placeholder plugin can collect it's placeholders and return them.
        This method does not use cached values but always go through the scene.

        Returns:
            List[PlaceholderItem]: Sorted placeholder items.
        """

        placeholders = []
        for placeholder_plugin in self.placeholder_plugins:
            result = placeholder_plugin.collect_placeholders()
            if result:
                placeholders.extend(result)

        return list(sorted(
            placeholders,
            key=lambda i: i.order
        ))

    @abstractmethod
    def import_template(self, template_path):
        """
        Import template in current host.

        Should load the content of template into scene so
        'process_scene_placeholders' can be started.

        Args:
            template_path (str): Fullpath for current task and
                host's template file.
        """

        pass

    # def template_already_imported(self, err_msg):
    #     pass
    #
    # def template_loading_failed(self, err_msg):
    #     pass

    def _prepare_placeholders(self, placeholders):
        """Run preparation part for placeholders on plugins.

        Args:
            placeholders (List[PlaceholderItem]): Placeholder items that will
                be processed.
        """

        # Prepare placeholder items by plugin
        plugins_by_identifier = {}
        placeholders_by_plugin_id = collections.defaultdict(list)
        for placeholder in placeholders:
            plugin = placeholder.plugin
            identifier = plugin.identifier
            plugins_by_identifier[identifier] = plugin
            placeholders_by_plugin_id[identifier].append(placeholder)

        # Plugin should prepare data for passed placeholders
        for identifier, placeholders in placeholders_by_plugin_id.items():
            plugin = plugins_by_identifier[identifier]
            plugin.prepare_placeholders(placeholders)

    def process_scene_placeholders(self, level_limit=None):
        """Find placeholders in scene using plugins and process them.

        This should happen after 'import_template'.

        Collect available placeholders from scene. All of them are processed
        after that shared data are cleared. Placeholder items are collected
        again and if there are any new the loop happens again. This is possible
        to change with defying 'level_limit'.

        Placeholders are marked as processed so they're not re-processed. To
        identify which placeholders were already processed is used
        placeholder's 'scene_identifier'.

        Args:
            level_limit (int): Level of loops that can happen. By default
                if is possible to have infinite nested placeholder processing.
        """

        if not self.placeholder_plugins:
            self.log.warning("There are no placeholder plugins available.")
            return

        placeholders = self.get_placeholders()
        if not placeholders:
            self.log.warning("No placeholders were found.")
            return

        placeholder_by_scene_id = {
            placeholder.identifier: placeholder
            for placeholder in placeholders
        }
        all_processed = len(placeholders) == 0
        iter_counter = 0
        while not all_processed:
            filtered_placeholders = []
            for placeholder in placeholders:
                if placeholder.finished:
                    continue

                if placeholder.in_progress:
                    self.log.warning((
                        "Placeholder that should be processed"
                        " is already in progress."
                    ))
                    continue
                filtered_placeholders.append(placeholder)

            self._prepare_placeholders(filtered_placeholders)

            for placeholder in filtered_placeholders:
                placeholder.set_in_progress()
                placeholder_plugin = placeholder.plugin
                try:
                    placeholder_plugin.process_placeholder(placeholder)

                except Exception as exc:
                    placeholder.set_error(exc)

                else:
                    placeholder.set_finished()

            # Clear shared data before getting new placeholders
            self.clear_shared_data()

            if level_limit:
                iter_counter += 1
                if iter_counter >= level_limit:
                    break

            all_processed = True
            collected_placeholders = self.get_placeholders()
            for placeholder in collected_placeholders:
                if placeholder.identifier in placeholder_by_scene_id:
                    continue

                all_processed = False
                identifier = placeholder.identifier
                placeholder_by_scene_id[identifier] = placeholder
                placeholders.append(placeholder)

    def _get_build_profiles(self):
        project_settings = get_project_settings(self.project_name)
        return (
            project_settings
            [self.host_name]
            ["templated_workfile_build"]
            ["profiles"]
        )

    def get_template_path(self):
        project_name = self.project_name
        host_name = self.host_name
        task_name = self.task_name
        task_type = self.task_type

        build_profiles = self._get_build_profiles()
        profile = filter_profiles(
            build_profiles,
            {
                "task_types": task_type,
                "task_names": task_name
            }
        )

        if not profile:
            raise TemplateProfileNotFound((
                "No matching profile found for task '{}' of type '{}' "
                "with host '{}'"
            ).format(task_name, task_type, host_name))

        path = profile["path"]
        if not path:
            raise TemplateLoadingFailed((
                "Template path is not set.\n"
                "Path need to be set in {}\\Template Workfile Build "
                "Settings\\Profiles"
            ).format(host_name.title()))

        # Try fill path with environments and anatomy roots
        anatomy = Anatomy(project_name)
        fill_data = {
            key: value
            for key, value in os.environ.items()
        }
        fill_data["root"] = anatomy.roots
        result = StringTemplate.format_template(path, fill_data)
        if result.solved:
            path = result.normalized()

        if path and os.path.exists(path):
            self.log.info("Found template at: '{}'".format(path))
            return path

        solved_path = None
        while True:
            try:
                solved_path = anatomy.path_remapper(path)
            except KeyError as missing_key:
                raise KeyError(
                    "Could not solve key '{}' in template path '{}'".format(
                        missing_key, path))

            if solved_path is None:
                solved_path = path
            if solved_path == path:
                break
            path = solved_path

        solved_path = os.path.normpath(solved_path)
        if not os.path.exists(solved_path):
            raise TemplateNotFound(
                "Template found in openPype settings for task '{}' with host "
                "'{}' does not exists. (Not found : {})".format(
                    task_name, host_name, solved_path))

        self.log.info("Found template at: '{}'".format(solved_path))

        return solved_path


@six.add_metaclass(ABCMeta)
class PlaceholderPlugin(object):
    label = None
    placeholder_options = []
    _log = None

    def __init__(self, builder):
        self._builder = builder

    @property
    def builder(self):
        """Access to builder which initialized the plugin.

        Returns:
            AbstractTemplateLoader: Loader of template build.
        """

        return self._builder

    @property
    def log(self):
        """Dynamically created logger for the plugin."""

        if self._log is None:
            self._log = Logger.get_logger(repr(self))
        return self._log

    @property
    def identifier(self):
        """Identifier which will be stored to placeholder.

        Default implementation uses class name.

        Returns:
            str: Unique identifier of placeholder plugin.
        """

        return self.__class__.__name__

    @abstractmethod
    def collect_placeholders(self):
        """Collect placeholders from scene.

        Returns:
            List[PlaceholderItem]: Placeholder objects.
        """

        pass

    def get_placeholder_options(self):
        """Placeholder options for data showed.

        Returns:
            List[AbtractAttrDef]: Attribute definitions of placeholder options.
        """

        return self.placeholder_options

    def prepare_placeholders(self, placeholders):
        """Preparation part of placeholders.

        Args:
            placeholders (List[PlaceholderItem]): List of placeholders that
                will be processed.
        """

        pass

    @abstractmethod
    def process_placeholder(self, placeholder):
        """Process single placeholder item.

        Processing of placeholders is defined by their order thus can't be
        processed in batch.

        Args:
            placeholder (PlaceholderItem): Placeholder that should be
                processed.
        """

        pass

    def cleanup_placeholders(self, placeholders):
        """Cleanup of placeholders after processing.

        Not:
            Passed placeholders can be failed.

        Args:
            placeholders (List[PlaceholderItem]): List of placeholders that
                were be processed.
        """

        pass

    def get_plugin_shared_data(self, key):
        """Receive shared data across plugin and placeholders.

        Using shared data from builder but stored under plugin identifier.

        Shared data are cleaned up on specific callbacks.

        Args:
            key (str): Key under which are shared data stored.

        Returns:
            Union[None, Any]: None if key was not set.
        """

        plugin_data = self.builder.get_shared_data(self.identifier)
        if plugin_data is None:
            return None
        return plugin_data.get(key)

    def set_plugin_shared_data(self, key, value):
        """Store share data across plugin and placeholders.

        Using shared data from builder but stored under plugin identifier.

        Key should be self explanatory to content.
        - wrong: 'asset'
        - good: 'asset_name'

        Shared data are cleaned up on specific callbacks.

        Args:
            key (str): Key under which is key stored.
            value (Any): Value that should be stored under the key.
        """

        plugin_data = self.builder.get_shared_data(self.identifier)
        if plugin_data is None:
            plugin_data = {}
        plugin_data[key] = value
        self.builder.set_shared_data(self.identifier, plugin_data)


class PlaceholderItem(object):
    """Item representing single item in scene that is a placeholder to process.

    Scene identifier is used to avoid processing of the palceholder item
    multiple times.

    Args:
        scene_identifier (str): Unique scene identifier. If placeholder is
            created from the same "node" it must have same identifier.
        data (Dict[str, Any]): Data related to placeholder. They're defined
            by plugin.
        plugin (PlaceholderPlugin): Plugin which created the placeholder item.
    """

    default_order = 100

    def __init__(self, scene_identifier, data, plugin):
        self._log = None
        self._scene_identifier = scene_identifier
        self._data = data
        self._plugin = plugin

        # Keep track about state of Placeholder process
        self._state = 0

        # Exception which happened during processing
        self._error = None

    @property
    def plugin(self):
        """Access to plugin which created placeholder.

        Returns:
            PlaceholderPlugin: Plugin object.
        """

        return self._plugin

    @property
    def builder(self):
        """Access to builder.

        Returns:
            AbstractTemplateLoader: Builder which is the top part of
                placeholder.
        """

        return self.plugin.builder

    @property
    def data(self):
        """Placeholder data which can modify how placeholder is processed.

        Possible general keys
        - order: Can define the order in which is palceholder processed.
                    Lower == earlier.

        Other keys are defined by placeholder and should validate them on item
        creation.

        Returns:
            Dict[str, Any]: Placeholder item data.
        """

        return self._data

    @property
    def log(self):
        if self._log is None:
            self._log = Logger.get_logger(repr(self))
        return self._log

    def __repr__(self):
        return "< {} {} >".format(self.__class__.__name__, self.name)

    @property
    def order(self):
        order = self._data.get("order")
        if order is None:
            return self.default_order
        return order

    @property
    def scene_identifier(self):
        return self._scene_identifier

    @property
    def finished(self):
        """Item was already processed."""

        return self._state == 2

    @property
    def in_progress(self):
        """Processing is in progress."""

        return self._state == 1

    @property
    def failed(self):
        """Processing of placeholder failed."""

        return self._error is not None

    @property
    def error(self):
        """Exception with which the placeholder process failed.

        Gives ability to access the exception.
        """

        return self._error

    def set_in_progress(self):
        """Change to in progress state."""

        self._state = 1

    def set_finished(self):
        """Change to finished state."""

        self._state = 2

    def set_error(self, error):
        """Set placeholder item as failed and mark it as finished."""

        self._error = error
        self.set_finished()
