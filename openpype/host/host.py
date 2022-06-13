import logging
import contextlib
from abc import ABCMeta, abstractproperty, abstractmethod
import six


class MissingMethodsError(ValueError):
    def __init__(self, host, missing_methods):
        joined_missing = ", ".join(
            ['"{}"'.format(item) for item in missing_methods]
        )
        message = (
            "Host \"{}\" miss methods {}".format(host.name, joined_missing)
        )
        super(MissingMethodsError, self).__init__(message)


@six.add_metaclass(ABCMeta)
class HostImplementation(object):
    """Base of host implementation class.

    Host is pipeline implementation of DCC application. This class should help
    to identify what must/should/can be implemented for specific functionality.

    Compared to 'avalon' concept:
    What was before considered as functions in host implementation folder. The
    host implementation should primarily care about adding ability of creation
    (mark subsets to be published) and optionaly about referencing published
    representations as containers.

    Host may need extend some functionality like working with workfiles
    or loading. Not all host implementations may allow that for those purposes
    can be logic extended with implementing functions for the purpose. There
    are prepared interfaces to be able identify what must be implemented to
    be able use that functionality.
    - current statement is that it is not required to inherit from interfaces
        but all of the methods are validated (only their existence!)

    # Installation of host before (avalon concept):
    ```python
    from openpype.pipeline import install_host
    import openpype.hosts.maya.api as host

    install_host(host)
    ```

    # Installation of host now:
    ```python
    from openpype.pipeline import install_host
    from openpype.hosts.maya.api import MayaHost

    host = MayaHost()
    install_host(host)
    ```

    # TODOs
    - move content of 'install_host' as method of this class
        - register host object
        - install legacy_io
        - install global plugin paths
    - store registered plugin paths to this object
    - handle current context (project, asset, task)
        - this must be done in many separated steps
    - have it's object of host tools instead of using globals

    This implementation will probably change over time when more
        functionality and responsibility will be added.
    """

    _log = None

    def __init__(self):
        """Initialization of host.

        Register DCC callbacks, host specific plugin paths, targets etc.
        (Part of what 'install' did in 'avalon' concept.)

        NOTE:
            At this moment global "installation" must happen before host
            installation. Because of this current limitation it is recommended
            to implement 'install' method which is triggered after global
            'install'.
        """

        pass

    @property
    def log(self):
        if self._log is None:
            self._log = logging.getLogger(self.__class__.__name__)
        return self._log

    @abstractproperty
    def name(self):
        """Host implementation name."""

        pass

    def get_current_context(self):
        """Get current context information.

        This method should be used to get current context of host. Usage of
        this method can be crutial for host implementations in DCCs where
        can be opened multiple workfiles at one moment and change of context
        can't be catched properly.

        Default implementation returns values from 'legacy_io.Session'.

        Returns:
            dict: Context with 3 keys 'project_name', 'asset_name' and
                'task_name'. All of them can be 'None'.
        """

        from openpype.pipeline import legacy_io

        if legacy_io.is_installed():
            legacy_io.install()

        return {
            "project_name": legacy_io.Session["AVALON_PROJECT"],
            "asset_name": legacy_io.Session["AVALON_ASSET"],
            "task_name": legacy_io.Session["AVALON_TASK"]
        }

    def get_context_title(self):
        """Context title shown for UI purposes.

        Should return current context title if possible.

        NOTE: This method is used only for UI purposes so it is possible to
            return some logical title for contextless cases.

        Is not meant for "Context menu" label.

        Returns:
            str: Context title.
            None: Default title is used based on UI implementation.
        """

        # Use current context to fill the context title
        current_context = self.get_current_context()
        project_name = current_context["project_name"]
        asset_name = current_context["asset_name"]
        task_name = current_context["task_name"]
        items = []
        if project_name:
            items.append(project_name)
            if asset_name:
                items.append(asset_name)
                if task_name:
                    items.append(task_name)
        if items:
            return "/".join(items)
        return None

    @contextlib.contextmanager
    def maintained_selection(self):
        """Some functionlity will happen but selection should stay same.

        This is DCC specific. Some may not allow to implement this ability
        that is reason why default implementation is empty context manager.
        """

        try:
            yield
        finally:
            pass


class ILoadHost:
    """Implementation requirements to be able use reference of representations.

    The load plugins can do referencing even without implementation of methods
    here, but switch and removement of containers would not be possible.

    QUESTIONS
    - Is list container dependency of host or load plugins?
    - Should this be directly in HostImplementation?
        - how to find out if referencing is available?
        - do we need to know that?
    """

    @staticmethod
    def get_missing_load_methods(host):
        """Look for missing methods on host implementation.

        Method is used for validation of implemented functions related to
        loading. Checks only existence of methods.

        Args:
            list[str]: Missing method implementations for loading workflow.
        """

        required = ["ls"]
        missing = []
        for name in required:
            if not hasattr(host, name):
                missing.append(name)
        return missing

    @staticmethod
    def validate_load_methods(host):
        """Validate implemented methods of host for load workflow.

        Raises:
            MissingMethodsError: If there are missing methods on host
                implementation.
        """
        missing = ILoadHost.get_missing_load_methods(host)
        if missing:
            raise MissingMethodsError(host, missing)

    @abstractmethod
    def ls(self):
        """Retreive referenced containers from scene.

        This can be implemented in hosts where referencing can be used.

        TODO:
            Rename function to something more self explanatory.
                Suggestion: 'get_referenced_containers'

        Returns:
            list[dict]: Information about loaded containers.
        """
        return []


@six.add_metaclass(ABCMeta)
class IWorkfileHost:
    """Implementation requirements to be able use workfile utils and tool.

    This interface just provides what is needed to implement in host
    implementation to support workfiles workflow, but does not have necessarily
    to inherit from this interface.
    """

    @staticmethod
    def get_missing_workfile_methods(host):
        """Look for missing methods on host implementation.

        Method is used for validation of implemented functions related to
        workfiles. Checks only existence of methods.

        Returns:
            list[str]: Missing method implementations for workfiles workflow.
        """

        required = [
            "open_file",
            "save_file",
            "current_file",
            "has_unsaved_changes",
            "file_extensions",
            "work_root",
        ]
        missing = []
        for name in required:
            if not hasattr(host, name):
                missing.append(name)
        return missing

    @staticmethod
    def validate_workfile_methods(host):
        """Validate implemented methods of host for workfiles workflow.

        Raises:
            MissingMethodsError: If there are missing methods on host
                implementation.
        """
        missing = IWorkfileHost.get_missing_workfile_methods(host)
        if missing:
            raise MissingMethodsError(host, missing)

    @abstractmethod
    def file_extensions(self):
        """Extensions that can be used as save.

        QUESTION: This could potentially use 'HostDefinition'.

        TODO:
            Rename to 'get_workfile_extensions'.
        """

        return []

    @abstractmethod
    def save_file(self, dst_path=None):
        """Save currently opened scene.

        TODO:
            Rename to 'save_current_workfile'.

        Args:
            dst_path (str): Where the current scene should be saved. Or use
                current path if 'None' is passed.
        """

        pass

    @abstractmethod
    def open_file(self, filepath):
        """Open passed filepath in the host.

        TODO:
            Rename to 'open_workfile'.

        Args:
            filepath (str): Path to workfile.
        """

        pass

    @abstractmethod
    def current_file(self):
        """Retreive path to current opened file.

        TODO:
            Rename to 'get_current_workfile'.

        Returns:
            str: Path to file which is currently opened.
            None: If nothing is opened.
        """

        return None

    def has_unsaved_changes(self):
        """Currently opened scene is saved.

        Not all hosts can know if current scene is saved because the API of
        DCC does not support it.

        Returns:
            bool: True if scene is saved and False if has unsaved
                modifications.
            None: Can't tell if workfiles has modifications.
        """

        return None

    def work_root(self, session):
        """Modify workdir per host.

        WARNING:
        We must handle this modification with more sofisticated way because
        this can't be called out of DCC so opening of last workfile
        (calculated before DCC is launched) is complicated. Also breaking
        defined work template is not a good idea.
        Only place where it's really used and can make sense is Maya. There
        workspace.mel can modify subfolders where to look for maya files.

        Default implementation keeps workdir untouched.

        Args:
            session (dict): Session context data.

        Returns:
            str: Path to new workdir.
        """

        return session["AVALON_WORKDIR"]


class INewPublisher:
    """Functions related to new creation system in new publisher.

    New publisher is not storing information only about each created instance
    but also some global data. At this moment are data related only to context
    publish plugins but that can extend in future.

    HostImplementation does not have to inherit from this interface just have
    to imlement mentioned all listed methods.
    """

    @staticmethod
    def get_missing_publish_methods(host):
        """Look for missing methods on host implementation.

        Method is used for validation of implemented functions related to
        new publish creation. Checks only existence of methods.

        Args:
            list[str]: Missing method implementations for new publsher
                workflow.
        """

        required = [
            "get_context_data",
            "update_context_data",
        ]
        missing = []
        for name in required:
            if not hasattr(host, name):
                missing.append(name)
        return missing

    @staticmethod
    def validate_publish_methods(host):
        """Validate implemented methods of host for create-publish workflow.

        Raises:
            MissingMethodsError: If there are missing methods on host
                implementation.
        """
        missing = INewPublisher.get_missing_publish_methods(host)
        if missing:
            raise MissingMethodsError(host, missing)

    @abstractmethod
    def get_context_data(self):
        """Get global data related to creation-publishing from workfile.

        These data are not related to any created instance but to whole
        publishing context. Not saving/returning them will cause that each
        reset of publishing resets all values to default ones.

        Context data can contain information about enabled/disabled publish
        plugins or other values that can be filled by artist.

        Returns:
            dict: Context data stored using 'update_context_data'.
        """

        pass

    @abstractmethod
    def update_context_data(self, data, changes):
        """Store global context data to workfile.

        Called when some values in context data has changed.

        Without storing the values in a way that 'get_context_data' would
        return them will each reset of publishing cause loose of filled values
        by artist. Best practice is to store values into workfile, if possible.

        Args:
            data (dict): New data as are.
            changes (dict): Only data that has been changed. Each value has
                tuple with '(<old>, <new>)' value.
        """

        pass
