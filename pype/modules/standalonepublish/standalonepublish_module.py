import os
import pype


class StandAlonePublishModule:
    def __init__(self, main_parent=None, parent=None):
        self.main_parent = main_parent
        self.parent_widget = parent
        self.publish_paths = [
            os.path.join(
                pype.PLUGINS_DIR, "standalonepublisher", "publish"
            )
        ]

    def tray_menu(self, parent_menu):
        from Qt import QtWidgets
        self.run_action = QtWidgets.QAction(
            "Publish", parent_menu
        )
        self.run_action.triggered.connect(self.show)
        parent_menu.addAction(self.run_action)

    def process_modules(self, modules):
        if "FtrackModule" in modules:
            self.publish_paths.append(os.path.join(
                pype.PLUGINS_DIR, "ftrack", "publish"
            ))

    def show(self):
        print("Running")
