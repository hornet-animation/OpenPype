import os
import logging

from avalon import api as avalon
from pyblish import api as pyblish

logger = logging.getLogger("pype.unreal")

PARENT_DIR = os.path.dirname(__file__)
PACKAGE_DIR = os.path.dirname(PARENT_DIR)
PLUGINS_DIR = os.path.join(PACKAGE_DIR, "plugins")

PUBLISH_PATH = os.path.join(PLUGINS_DIR, "unreal", "publish")
LOAD_PATH = os.path.join(PLUGINS_DIR, "unreal", "load")
CREATE_PATH = os.path.join(PLUGINS_DIR, "unreal", "create")


def install():
    """Install Unreal configuration for Avalon."""
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
    print("installing Pype for Unreal ...")
    print("-=" * 40)
    logger.info("installing Pype for Unreal")
    pyblish.register_plugin_path(str(PUBLISH_PATH))
    avalon.register_plugin_path(avalon.Loader, str(LOAD_PATH))
    avalon.register_plugin_path(avalon.Creator, str(CREATE_PATH))


def uninstall():
    """Uninstall Unreal configuration for Avalon."""
    pyblish.deregister_plugin_path(str(PUBLISH_PATH))
    avalon.deregister_plugin_path(avalon.Loader, str(LOAD_PATH))
    avalon.deregister_plugin_path(avalon.Creator, str(CREATE_PATH))
