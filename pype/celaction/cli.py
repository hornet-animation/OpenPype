import os
import sys
import copy
import argparse
import importlib

from avalon import io
import avalon.api
from avalon.tools import publish

import pyblish.api
import pyblish.util

from pypeapp import execute, Logger
import pype
import pype.celaction



log = Logger().get_logger("Celaction_cli_publisher")

publish_host = "celaction"

CURRENT_DIR = os.path.dirname(__file__)
PACKAGE_DIR = os.path.dirname(CURRENT_DIR)
PLUGINS_DIR = os.path.join(PACKAGE_DIR, "plugins")
PUBLISH_PATH = os.path.join(PLUGINS_DIR, publish_host, "publish")

PUBLISH_PATHS = [
    PUBLISH_PATH,
    os.path.join(PLUGINS_DIR, "ftrack", "publish")
]


def cli():
    parser = argparse.ArgumentParser(prog="celaction_publish")

    parser.add_argument("--currentFile",
                        help="Pass file to Context as `currentFile`")

    parser.add_argument("--chunk",
                        help=("Render chanks on farm"))

    parser.add_argument("--frameStart",
                        help=("Start of frame range"))

    parser.add_argument("--frameEnd",
                        help=("End of frame range"))

    parser.add_argument("--resolutionWidth",
                        help=("Width of resolution"))

    parser.add_argument("--resolutionHeight",
                        help=("Height of resolution"))

    parser.add_argument("--programDir",
                        help=("Directory with celaction program installation"))



    pype.celaction.kwargs = parser.parse_args(sys.argv[1:]).__dict__


def _prepare_publish_environments():
    """Prepares environments based on request data."""
    env = copy.deepcopy(os.environ)

    project_name = os.getenv("AVALON_PROJECT")
    asset_name = os.getenv("AVALON_ASSET")

    io.install()
    project_doc = io.find_one({
        "type": "project"
    })
    av_asset = io.find_one({
        "type": "asset",
        "name": asset_name
    })
    parents = av_asset["data"]["parents"]
    hierarchy = ""
    if parents:
        hierarchy = "/".join(parents)

    env["AVALON_PROJECT"] = project_name
    env["AVALON_ASSET"] = asset_name
    env["AVALON_TASK"] = os.getenv("AVALON_TASK")
    env["AVALON_WORKDIR"] = os.getenv("AVALON_WORKDIR")
    env["AVALON_HIERARCHY"] = hierarchy
    env["AVALON_PROJECTCODE"] = project_doc["data"].get("code", "")
    env["AVALON_APP"] = publish_host
    env["AVALON_APP_NAME"] = publish_host

    env["PYBLISH_HOSTS"] = publish_host

    os.environ.update(env)

def _main():
    # Registers pype's Global pyblish plugins
    pype.install()

    host_import_str = f"pype.{publish_host}"

    try:
        host_module = importlib.import_module(host_import_str)
    except ModuleNotFoundError:
        log.error((
            f"Host \"{publish_host}\" can't be imported."
            f" Import string \"{host_import_str}\" failed."
        ))
        return False

    avalon.api.install(host_module)

    for path in PUBLISH_PATH:
        path = os.path.normpath(path)
        if not os.path.exists(path):
            continue

        pyblish.api.register_plugin_path(path)

    # Register project specific plugins
    project_name = os.environ["AVALON_PROJECT"]
    project_plugins_paths =  os.getenv("PYPE_PROJECT_PLUGINS", "")
    for path in project_plugins_paths.split(os.pathsep):
        plugin_path = os.path.join(path, project_name, "plugins")
        if os.path.exists(plugin_path):
            pyblish.api.register_plugin_path(plugin_path)

    return publish.show()


if __name__ == "__main__":
    cli()
    _prepare_publish_environments()
    result = _main()
    sys.exit(not bool(result))
