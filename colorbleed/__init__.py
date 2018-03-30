import os
from pyblish import api as pyblish

from .config_actions import register_actions

PACKAGE_DIR = os.path.dirname(__file__)
PLUGINS_DIR = os.path.join(PACKAGE_DIR, "plugins")
PUBLISH_PATH = os.path.join(PLUGINS_DIR, "publish")


def install():
    publish_path = os.path.join(PLUGINS_DIR, "publish")
    print("Registering global plug-ins..")

    pyblish.register_plugin_path(publish_path)


def uninstall():
    pyblish.deregister_plugin_path(PUBLISH_PATH)


def register_launcher_actions():
    """Convenience function to register the actions"""
    register_actions()
