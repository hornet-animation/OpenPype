import pymel.core as pc
import maya.cmds as cmds

from avalon import api, io
from avalon.maya.pipeline import containerise
from avalon.maya import lib
from Qt import QtWidgets, QtCore


class CameraWindow(QtWidgets.QDialog):

    def __init__(self, cameras):
        super(CameraWindow, self).__init__()
        self.setWindowFlags(self.windowFlags() | QtCore.Qt.FramelessWindowHint)

        self.camera = None

        self.widgets = {
            "label": QtWidgets.QLabel("Select camera for image plane."),
            "list": QtWidgets.QListWidget(),
            "warning": QtWidgets.QLabel("No cameras selected!"),
            "buttons": QtWidgets.QWidget(),
            "okButton": QtWidgets.QPushButton("Ok"),
            "cancelButton": QtWidgets.QPushButton("Cancel")
        }

        # Build warning.
        self.widgets["warning"].setVisible(False)
        self.widgets["warning"].setStyleSheet("color: red")

        # Build list.
        for camera in cameras:
            self.widgets["list"].addItem(camera)

        # Build buttons.
        layout = QtWidgets.QHBoxLayout(self.widgets["buttons"])
        layout.addWidget(self.widgets["okButton"])
        layout.addWidget(self.widgets["cancelButton"])

        # Build layout.
        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(self.widgets["label"])
        layout.addWidget(self.widgets["list"])
        layout.addWidget(self.widgets["buttons"])
        layout.addWidget(self.widgets["warning"])

        self.widgets["okButton"].pressed.connect(self.on_ok_pressed)
        self.widgets["cancelButton"].pressed.connect(self.on_cancel_pressed)
        self.widgets["list"].itemPressed.connect(self.on_list_itemPressed)

    def on_list_itemPressed(self, item):
        self.camera = item.text()

    def on_ok_pressed(self):
        if self.camera is None:
            self.widgets["warning"].setVisible(True)
            return

        self.close()

    def on_cancel_pressed(self):
        self.camera = None
        self.close()


class ImagePlaneLoader(api.Loader):
    """Specific loader of plate for image planes on selected camera."""

    families = ["plate", "render"]
    label = "Load imagePlane."
    representations = ["mov", "exr", "preview", "png"]
    icon = "image"
    color = "orange"

    def load(self, context, name, namespace, data):
        new_nodes = []
        image_plane_depth = 1000
        asset = context['asset']['name']
        namespace = namespace or lib.unique_namespace(
            asset + "_",
            prefix="_" if asset[0].isdigit() else "",
            suffix="_",
        )

        # Get camera from user selection.
        camera = None
        default_cameras = [
            "frontShape", "perspShape", "sideShape", "topShape"
        ]
        cameras = [
            x for x in pc.ls(type="camera") if x.name() not in default_cameras
        ]
        camera_names = {x.getParent().name(): x for x in cameras}
        camera_names["Create new camera."] = "create_camera"
        window = CameraWindow(camera_names.keys())
        window.exec_()
        camera = camera_names[window.camera]

        if camera == "create_camera":
            camera = pc.createNode("camera")

        if camera is None:
                return

        try:
            camera.displayResolution.set(1)
            camera.farClipPlane.set(image_plane_depth * 10)
        except RuntimeError:
            pass

        # Create image plane
        image_plane_transform, image_plane_shape = pc.imagePlane(
            camera=camera, showInAllViews=False
        )
        image_plane_shape.depth.set(image_plane_depth)

        image_plane_shape.imageName.set(
            context["representation"]["data"]["path"]
        )

        start_frame = pc.playbackOptions(q=True, min=True)
        end_frame = pc.playbackOptions(q=True, max=True)

        image_plane_shape.frameOffset.set(1 - start_frame)
        image_plane_shape.frameIn.set(start_frame)
        image_plane_shape.frameOut.set(end_frame)
        image_plane_shape.frameCache.set(end_frame)
        image_plane_shape.useFrameExtension.set(1)

        movie_representations = ["mov", "preview"]
        if context["representation"]["name"] in movie_representations:
            # Need to get "type" by string, because its a method as well.
            pc.Attribute(image_plane_shape + ".type").set(2)

        # Ask user whether to use sequence or still image.
        if context["representation"]["name"] == "exr":
            # Ensure OpenEXRLoader plugin is loaded.
            pc.loadPlugin("OpenEXRLoader.mll", quiet=True)

            message = (
                "Hold image sequence on first frame?"
                "\n{} files available.".format(
                    len(context["representation"]["files"])
                )
            )
            reply = QtWidgets.QMessageBox.information(
                None,
                "Frame Hold.",
                message,
                QtWidgets.QMessageBox.Ok,
                QtWidgets.QMessageBox.Cancel
            )
            if reply == QtWidgets.QMessageBox.Ok:
                pc.delete(
                    image_plane_shape.listConnections(type="expression")[0]
                )
                image_plane_shape.frameExtension.set(start_frame)

        new_nodes.extend(
            [
                image_plane_transform.longName().split("|")[-1],
                image_plane_shape.longName().split("|")[-1]
            ]
        )

        for node in new_nodes:
            pc.rename(node, "{}:{}".format(namespace, node))

        return containerise(
            name=name,
            namespace=namespace,
            nodes=new_nodes,
            context=context,
            loader=self.__class__.__name__
        )

    def update(self, container, representation):
        image_plane_shape = None
        for node in pc.PyNode(container["objectName"]).members():
            if node.nodeType() == "imagePlane":
                image_plane_shape = node

        assert image_plane_shape is not None, "Image plane not found."

        path = api.get_representation_path(representation)
        image_plane_shape.imageName.set(path)
        cmds.setAttr(
            container["objectName"] + ".representation",
            str(representation["_id"]),
            type="string"
        )

        # Set frame range.
        version = io.find_one({"_id": representation["parent"]})
        subset = io.find_one({"_id": version["parent"]})
        asset = io.find_one({"_id": subset["parent"]})
        start_frame = asset["data"]["frameStart"]
        end_frame = asset["data"]["frameEnd"]
        image_plane_shape.frameOffset.set(1 - start_frame)
        image_plane_shape.frameIn.set(start_frame)
        image_plane_shape.frameOut.set(end_frame)
        image_plane_shape.frameCache.set(end_frame)

    def switch(self, container, representation):
        self.update(container, representation)

    def remove(self, container):
        members = cmds.sets(container['objectName'], query=True)
        cmds.lockNode(members, lock=False)
        cmds.delete([container['objectName']] + members)

        # Clean up the namespace
        try:
            cmds.namespace(removeNamespace=container['namespace'],
                           deleteNamespaceContent=True)
        except RuntimeError:
            pass
