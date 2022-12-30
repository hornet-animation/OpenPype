from copy import deepcopy
import re
import os
import json
import platform
import contextlib
import tempfile
from openpype import PACKAGE_DIR
from openpype.settings import get_project_settings
from openpype.lib import (
    StringTemplate,
    run_openpype_process,
    Logger
)
from openpype.pipeline import Anatomy

log = Logger.get_logger(__name__)


@contextlib.contextmanager
def _make_temp_json_file():
    try:
        # Store dumped json to temporary file
        temporary_json_file = tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        )
        temporary_json_file.close()
        temporary_json_filepath = temporary_json_file.name.replace(
            "\\", "/"
        )

        yield temporary_json_filepath

    except IOError as _error:
        raise IOError(
            "Not able to create temp json file: {}".format(
                _error
            )
        )

    finally:
        # Remove the temporary json
        os.remove(temporary_json_filepath)


def get_ocio_config_script_path():
    return os.path.normpath(
        os.path.join(
            PACKAGE_DIR,
            "scripts",
            "ocio_config_op.py"
        )
    )


def get_imageio_colorspace_from_filepath(
    path, host_name, project_name,
    config_data=None, file_rules=None,
    project_settings=None,
    validate=True
):
    if not any([config_data, file_rules]):
        project_settings = project_settings or get_project_settings(
            project_name
        )
        config_data = get_imageio_config(
            project_name, host_name, project_settings)
        file_rules = get_imageio_file_rules(
            project_name, host_name, project_settings)

    # match file rule from path
    colorspace_name = None
    for _frule_name, file_rule in file_rules.items():
        pattern = file_rule["pattern"]
        extension = file_rule["ext"]
        ext_match = re.match(
            r".*(?=.{})".format(extension), path
        )
        file_match = re.search(
            pattern, path
        )

        if ext_match and file_match:
            colorspace_name = file_rule["colorspace"]

    if not colorspace_name:
        log.info("No imageio file rule matched input path: '{}'".format(
            path
        ))
        return None

    # validate matching colorspace with config
    if validate and config_data:
        validate_imageio_colorspace_in_config(
            config_data["path"], colorspace_name)

    return colorspace_name


def parse_colorspace_from_filepath(
    path, host_name, project_name,
    config_data=None,
    project_settings=None
):
    if not config_data:
        project_settings = project_settings or get_project_settings(
            project_name
        )
        config_data = get_imageio_config(
            project_name, host_name, project_settings)

    config_path = config_data["path"]

    # match file rule from path
    colorspace_name = None
    colorspaces = get_ocio_config_colorspaces(config_path)
    for colorspace_key in colorspaces:
        if colorspace_key.replace(" ", "_") in path:
            colorspace_name = colorspace_key
            break

    if not colorspace_name:
        log.info("No matching colorspace in config '{}' for path: '{}'".format(
            config_path, path
        ))
        return None

    return colorspace_name


def validate_imageio_colorspace_in_config(config_path, colorspace_name):
    colorspaces = get_ocio_config_colorspaces(config_path)
    if colorspace_name not in colorspaces:
        raise KeyError(
            "Missing colorspace '{}' in config file '{}'".format(
                colorspace_name, config_path)
        )
    return True


def get_ocio_config_colorspaces(config_path):
    with _make_temp_json_file() as tmp_json_path:
        # Prepare subprocess arguments
        args = [
            "run", get_ocio_config_script_path(),
            "config", "get_colorspace",
            "--in_path", config_path,
            "--out_path", tmp_json_path

        ]
        log.info("Executing: {}".format(" ".join(args)))

        process_kwargs = {
            "logger": log,
            "env": {}
        }

        run_openpype_process(*args, **process_kwargs)

        # return all colorspaces
        return_json_data = open(tmp_json_path).read()
        return json.loads(return_json_data)


def get_imageio_config(
    project_name, host_name,
    project_settings=None,
    anatomy_data=None,
    anatomy=None
):
    project_settings = project_settings or get_project_settings(project_name)
    anatomy = anatomy or Anatomy(project_name)
    current_platform = platform.system().lower()

    if not anatomy_data:
        from openpype.pipeline.context_tools import (
            get_template_data_from_session)
        anatomy_data = get_template_data_from_session()

    # add project roots to anatomy data
    anatomy_data["root"] = anatomy.roots

    # get colorspace settings
    imageio_global, imageio_host = _get_imageio_settings(
        project_settings, host_name)

    # get config path from either global or host_name
    config_global = imageio_global["ocio_config"]
    config_host = imageio_host["ocio_config"]

    # set config path
    config_path = None
    if config_global["enabled"]:
        config_path = config_global["filepath"][current_platform]
    if config_host["enabled"]:
        config_path = config_host["filepath"][current_platform]

    if not config_path:
        return

    formating_data = deepcopy(anatomy_data)

    # format the path for potential env vars
    formating_data.update(dict(**os.environ))

    # format path for anatomy keys
    formated_path = StringTemplate(config_path).format(
        formating_data)

    abs_path = os.path.abspath(formated_path)
    return {
        "path": os.path.normpath(abs_path),
        "template": config_path
    }


def get_imageio_file_rules(project_name, host_name, project_settings=None):

    project_settings = project_settings or get_project_settings(project_name)

    imageio_global, imageio_host = _get_imageio_settings(
        project_settings, host_name)

    # get file rules from global and host_name
    frules_global = imageio_global["file_rules"]
    frules_host = imageio_host["file_rules"]

    # compile file rules dictionary
    file_rules = {}
    if frules_global["enabled"]:
        file_rules.update(frules_global["rules"])
    if frules_host["enabled"]:
        file_rules.update(frules_host["rules"])

    return file_rules


def _get_imageio_settings(project_settings, host_name):

    # get image io from global and host_name
    imageio_global = project_settings["global"]["imageio"]
    imageio_host = project_settings[host_name]["imageio"]

    return imageio_global, imageio_host
