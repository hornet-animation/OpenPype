import os
from pype.api import project_settings
import pype.hosts.maya.lib as mlib
from maya import cmds


print("starting PYPE usersetup")

# build a shelf
settings = project_settings(os.environ['AVALON_PROJECT'])
shelf_preset = settings['maya'].get('project_shelf')


if shelf_preset:
    project = os.environ["AVALON_PROJECT"]

    icon_path = os.path.join(os.environ['PYPE_PROJECT_SCRIPTS'], project, "icons")
    icon_path = os.path.abspath(icon_path)

    for i in shelf_preset['imports']:
        import_string = "from {} import {}".format(project, i)
        print(import_string)
        exec(import_string)

cmds.evalDeferred("mlib.shelf(name=shelf_preset['name'], iconPath=icon_path, preset=shelf_preset)")


print("finished PYPE usersetup")
