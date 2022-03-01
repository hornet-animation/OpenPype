import os
import logging

from avalon import api as avalon
from pyblish import api as pyblish
import openpype.hosts.unreal
from .plugin import(
    Loader,
    Creator
)
from .pipeline import (
    install,
    uninstall,
    ls,
    publish,
    containerise,
    show_creator,
    show_loader,
    show_publisher,
    show_manager,
    show_experimental_tools,
    show_tools_dialog,
    show_tools_popup,
    instantiate,
)


logger = logging.getLogger("openpype.hosts.unreal")

HOST_DIR = os.path.dirname(os.path.abspath(openpype.hosts.unreal.__file__))
PLUGINS_DIR = os.path.join(HOST_DIR, "plugins")
PUBLISH_PATH = os.path.join(PLUGINS_DIR, "publish")
LOAD_PATH = os.path.join(PLUGINS_DIR, "load")
CREATE_PATH = os.path.join(PLUGINS_DIR, "create")
INVENTORY_PATH = os.path.join(PLUGINS_DIR, "inventory")


__all__ = [
    "install",
    "uninstall",
    "Creator",
    "Loader",
    "ls",
    "publish",
    "containerise",
    "show_creator",
    "show_loader",
    "show_publisher",
    "show_manager",
    "show_experimental_tools",
    "show_tools_dialog",
    "show_tools_popup",
    "instantiate"
]



def install():
    """Install Unreal configuration for OpenPype."""
    print("-=" * 40)
    logo = '''.
.
     ____________
   / \\      __   \\
   \\  \\     \\/_\\  \\
    \\  \\     _____/ ______
     \\  \\    \\___// \\     \\
      \\  \\____\\   \\  \\_____\\
       \\/_____/    \\/______/  PYPE Club .
.
'''
    print(logo)
    print("installing OpenPype for Unreal ...")
    print("-=" * 40)
    logger.info("installing OpenPype for Unreal")
    pyblish.register_plugin_path(str(PUBLISH_PATH))
    avalon.register_plugin_path(avalon.Loader, str(LOAD_PATH))
    avalon.register_plugin_path(avalon.Creator, str(CREATE_PATH))


def uninstall():
    """Uninstall Unreal configuration for Avalon."""
    pyblish.deregister_plugin_path(str(PUBLISH_PATH))
    avalon.deregister_plugin_path(avalon.Loader, str(LOAD_PATH))
    avalon.deregister_plugin_path(avalon.Creator, str(CREATE_PATH))
