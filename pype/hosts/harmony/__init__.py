import os
import sys
from uuid import uuid4

from avalon import api, io, harmony
from avalon.vendor import Qt
import avalon.tools.sceneinventory
import pyblish.api
from pype import lib
from pype.api import config


signature = str(uuid4())


def set_scene_settings(settings):

    signature = harmony.signature("set_scene_settings")
    func = """function %s(args)
    {
        if (args[0]["fps"])
        {
            scene.setFrameRate(args[0]["fps"]);
        }
        if (args[0]["frameStart"] && args[0]["frameEnd"])
        {
            var duration = args[0]["frameEnd"] - args[0]["frameStart"] + 1

            if (frame.numberOf() < duration)
            {
                frame.insert(
                    duration, duration - frame.numberOf()
                );
            }

            scene.setStartFrame(1);
            scene.setStopFrame(duration);
        }
        if (args[0]["resolutionWidth"] && args[0]["resolutionHeight"])
        {
            scene.setDefaultResolution(
                args[0]["resolutionWidth"], args[0]["resolutionHeight"], 41.112
            )
        }
    }
    %s
    """ % (signature, signature)
    harmony.send({"function": func, "args": [settings]})


def get_asset_settings():
    asset_data = lib.get_asset()["data"]
    fps = asset_data.get("fps")
    frame_start = asset_data.get("frameStart")
    frame_end = asset_data.get("frameEnd")
    resolution_width = asset_data.get("resolutionWidth")
    resolution_height = asset_data.get("resolutionHeight")

    scene_data = {
        "fps": fps,
        "frameStart": frame_start,
        "frameEnd": frame_end,
        "resolutionWidth": resolution_width,
        "resolutionHeight": resolution_height
    }

    harmony_config = config.get_presets()["harmony"]["general"]

    skip_resolution_check = harmony_config.get(["skip_resolution_check"], [])
    if os.getenv('AVALON_TASK') in skip_resolution_check:
        scene_data.pop("resolutionWidth")
        scene_data.pop("resolutionHeight")

    return scene_data


def ensure_scene_settings():
    settings = get_asset_settings()

    invalid_settings = []
    valid_settings = {}
    for key, value in settings.items():
        if value is None:
            invalid_settings.append(key)
        else:
            valid_settings[key] = value

    # Warn about missing attributes.
    print("Starting new QApplication..")
    app = Qt.QtWidgets.QApplication(sys.argv)

    message_box = Qt.QtWidgets.QMessageBox()
    message_box.setIcon(Qt.QtWidgets.QMessageBox.Warning)
    msg = "Missing attributes:"
    if invalid_settings:
        for item in invalid_settings:
            msg += f"\n{item}"
        message_box.setText(msg)
        message_box.exec_()

    # Garbage collect QApplication.
    del app

    set_scene_settings(valid_settings)


def check_inventory():
    if not lib.any_outdated():
        return

    host = avalon.api.registered_host()
    outdated_containers = []
    for container in host.ls():
        representation = container['representation']
        representation_doc = io.find_one(
            {
                "_id": io.ObjectId(representation),
                "type": "representation"
            },
            projection={"parent": True}
        )
        if representation_doc and not lib.is_latest(representation_doc):
            outdated_containers.append(container)

    # Colour nodes.
    sig = harmony.signature("set_color")
    func = """function %s(args){

        for( var i =0; i <= args[0].length - 1; ++i)
        {
            var red_color = new ColorRGBA(255, 0, 0, 255);
            node.setColor(args[0][i], red_color);
        }
    }
    %s
    """ % (sig, sig)
    outdated_nodes = []
    for container in outdated_containers:
        if container["loader"] == "ImageSequenceLoader":
            outdated_nodes.append(
                harmony.find_node_by_name(container["name"], "READ")
            )
    harmony.send({"function": func, "args": [outdated_nodes]})

    # Warn about outdated containers.
    print("Starting new QApplication..")
    app = Qt.QtWidgets.QApplication(sys.argv)

    message_box = Qt.QtWidgets.QMessageBox()
    message_box.setIcon(Qt.QtWidgets.QMessageBox.Warning)
    msg = "There are outdated containers in the scene."
    message_box.setText(msg)
    message_box.exec_()

    # Garbage collect QApplication.
    del app


def application_launch():
    ensure_scene_settings()
    check_inventory()


def export_template(backdrops, nodes, filepath):

    sig = harmony.signature("set_color")
    func = """function %s(args)
    {

        var temp_node = node.add("Top", "temp_note", "NOTE", 0, 0, 0);
        var template_group = node.createGroup(temp_node, "temp_group");
        node.deleteNode( template_group + "/temp_note" );

        selection.clearSelection();
        for (var f = 0; f < args[1].length; f++)
        {
            selection.addNodeToSelection(args[1][f]);
        }

        Action.perform("copy()", "Node View");

        selection.clearSelection();
        selection.addNodeToSelection(template_group);
        Action.perform("onActionEnterGroup()", "Node View");
        Action.perform("paste()", "Node View");

        // Recreate backdrops in group.
        for (var i = 0 ; i < args[0].length; i++)
        {
            MessageLog.trace(args[0][i]);
            Backdrop.addBackdrop(template_group, args[0][i]);
        };

        Action.perform( "selectAll()", "Node View" );
        copyPaste.createTemplateFromSelection(args[2], args[3]);

        // Unfocus the group in Node view, delete all nodes and backdrops
        // created during the process.
        Action.perform("onActionUpToParent()", "Node View");
        node.deleteNode(template_group, true, true);
    }
    %s
    """ % (sig, sig)
    harmony.send({
        "function": func,
        "args": [
            backdrops,
            nodes,
            os.path.basename(filepath),
            os.path.dirname(filepath)
        ]
    })


def install():
    print("Installing Pype config...")

    plugins_directory = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        "plugins",
        "harmony"
    )

    pyblish.api.register_plugin_path(
        os.path.join(plugins_directory, "publish")
    )
    api.register_plugin_path(
        api.Loader, os.path.join(plugins_directory, "load")
    )
    api.register_plugin_path(
        api.Creator, os.path.join(plugins_directory, "create")
    )

    # Register callbacks.
    pyblish.api.register_callback(
        "instanceToggled", on_pyblish_instance_toggled
    )

    api.on("application.launched", application_launch)


def on_pyblish_instance_toggled(instance, old_value, new_value):
    """Toggle node enabling on instance toggles."""

    sig = harmony.signature("enable_node")
    func = """function %s(args)
    {
        node.setEnable(args[0], args[1])
    }
    %s
    """ % (sig, sig)
    try:
        harmony.send(
            {"function": func, "args": [instance[0], new_value]}
        )
    except IndexError:
        print(f"Instance '{instance}' is missing node")
