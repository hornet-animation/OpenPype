import tempfile
import os
import pyblish.api
import avalon.api
from pype.api import get_project_settings
from pype.lib import filter_profiles

ValidatePipelineOrder = pyblish.api.ValidatorOrder + 0.05
ValidateContentsOrder = pyblish.api.ValidatorOrder + 0.1
ValidateSceneOrder = pyblish.api.ValidatorOrder + 0.2
ValidateMeshOrder = pyblish.api.ValidatorOrder + 0.3


class TaskNotSetError(KeyError):
    def __init__(self, msg=None):
        if not msg:
            msg = "Creator's subset name template requires task name."
        super(TaskNotSetError, self).__init__(msg)


class PypeCreatorMixin:
    """Helper to override avalon's default class methods.

    Mixin class must be used as first in inheritance order to override methods.
    """
    default_tempate = "{family}{user_input}"

    @classmethod
    def get_subset_name(
        cls, variant, task_name, asset_id, project_name, host_name=None
    ):
        if not cls.family:
            return ""

        if not host_name:
            host_name = os.environ["AVALON_APP"]

        # Use only last part of class family value split by dot (`.`)
        family = cls.family.rsplit(".", 1)[-1]

        # Get settings
        tools_settings = get_project_settings(project_name)["global"]["tools"]
        profiles = tools_settings["creator"]["subset_name_profiles"]
        filtering_criteria = {
            "families": family,
            "hosts": host_name,
            "tasks": task_name
        }

        matching_profile = filter_profiles(profiles, filtering_criteria)
        template = None
        if matching_profile:
            template = matching_profile["template"]

        # Make sure template is set (matching may have empty string)
        if not template:
            template = cls.default_tempate

        # Simple check of task name existence for template with {task} in
        #   - missing task should be possible only in Standalone publisher
        if not task_name and "{task}" in template:
            raise TaskNotSetError()

        fill_data = {
            "variant": variant,
            "Variant": variant.capitalize(),
            "VARIANT": variant.upper(),
            "family": family,
            "Family": family.capitalize(),
            "FAMILY": family.upper(),
            "task": task_name,
            "Task": task_name.capitalize(),
            "TASK": task_name.upper()
        }
        return template.format(**fill_data)


class Creator(PypeCreatorMixin, avalon.api.Creator):
    pass


class ContextPlugin(pyblish.api.ContextPlugin):
    def process(cls, *args, **kwargs):
        super(ContextPlugin, cls).process(cls, *args, **kwargs)


class InstancePlugin(pyblish.api.InstancePlugin):
    def process(cls, *args, **kwargs):
        super(InstancePlugin, cls).process(cls, *args, **kwargs)


class Extractor(InstancePlugin):
    """Extractor base class.

    The extractor base class implements a "staging_dir" function used to
    generate a temporary directory for an instance to extract to.

    This temporary directory is generated through `tempfile.mkdtemp()`

    """

    order = 2.0

    def staging_dir(self, instance):
        """Provide a temporary directory in which to store extracted files

        Upon calling this method the staging directory is stored inside
        the instance.data['stagingDir']
        """
        staging_dir = instance.data.get('stagingDir', None)

        if not staging_dir:
            staging_dir = os.path.normpath(
                tempfile.mkdtemp(prefix="pyblish_tmp_")
            )
            instance.data['stagingDir'] = staging_dir

        return staging_dir


def contextplugin_should_run(plugin, context):
    """Return whether the ContextPlugin should run on the given context.

    This is a helper function to work around a bug pyblish-base#250
    Whenever a ContextPlugin sets specific families it will still trigger even
    when no instances are present that have those families.

    This actually checks it correctly and returns whether it should run.

    """
    required = set(plugin.families)

    # When no filter always run
    if "*" in required:
        return True

    for instance in context:

        # Ignore inactive instances
        if (not instance.data.get("publish", True) or
                not instance.data.get("active", True)):
            continue

        families = instance.data.get("families", [])
        if any(f in required for f in families):
            return True

        family = instance.data.get("family")
        if family and family in required:
            return True

    return False


class ValidationException(Exception):
    pass
