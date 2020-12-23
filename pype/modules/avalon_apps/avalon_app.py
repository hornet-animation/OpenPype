import os
import pype
from pype import resources
from .. import (
    PypeModule,
    ITrayModule,
    IRestApi
)


class AvalonModule(PypeModule, ITrayModule, IRestApi):
    name = "avalon"

    def initialize(self, modules_settings):
        # This module is always enabled
        self.enabled = True

        avalon_settings = modules_settings[self.name]

        # Check if environment is already set
        avalon_mongo_url = os.environ.get("AVALON_MONGO")
        if not avalon_mongo_url:
            avalon_mongo_url = avalon_settings["AVALON_MONGO"]
        # Use pype mongo if Avalon's mongo not defined
        if not avalon_mongo_url:
            avalon_mongo_url = os.environ["PYPE_MONGO"]

        thumbnail_root = os.environ.get("AVALON_THUMBNAIL_ROOT")
        if not thumbnail_root:
            thumbnail_root = avalon_settings["AVALON_THUMBNAIL_ROOT"]

        # Mongo timeout
        avalon_mongo_timeout = os.environ.get("AVALON_TIMEOUT")
        if not avalon_mongo_timeout:
            avalon_mongo_timeout = avalon_settings["AVALON_TIMEOUT"]

        self.thumbnail_root = thumbnail_root
        self.avalon_mongo_url = avalon_mongo_url
        self.avalon_mongo_timeout = avalon_mongo_timeout

        self.schema_path = os.path.join(
            os.path.dirname(pype.PACKAGE_DIR),
            "schema"
        )

        # Tray attributes
        self.libraryloader = None
        self.rest_api_obj = None

    def get_global_environments(self):
        """Avalon global environments for pype implementation."""
        mongodb_data_dir = os.environ.get("AVALON_DB_DATA")
        if not mongodb_data_dir:
            mongodb_data_dir = os.path.join(
                os.path.dirname(os.environ["PYPE_ROOT"]),
                "mongo_db_data"
            )
        return {
            # 100% hardcoded
            "AVALON_SCHEMA": self.schema_path,
            "AVALON_CONFIG": "pype",
            "AVALON_LABEL": "Pype",

            # Modifiable by settings
            # - mongo ulr for avalon projects
            "AVALON_MONGO": self.avalon_mongo_url,
            # TODO thumbnails root should be multiplafrom
            # - thumbnails root
            "AVALON_THUMBNAIL_ROOT": self.thumbnail_root,
            # - mongo timeout in ms
            "AVALON_TIMEOUT": str(self.avalon_mongo_timeout),

            # May be modifiable?
            # - mongo database name where projects are stored
            "AVALON_DB": "avalon",

            # Not even connected to Avalon
            # TODO remove - pype's variable for local mongo
            "AVALON_DB_DATA": mongodb_data_dir
        }

    def tray_init(self):
        # Add library tool
        try:
            from avalon.tools.libraryloader import app
            from avalon import style
            from Qt import QtGui

            self.libraryloader = app.Window(
                icon=QtGui.QIcon(resources.pype_icon_filepath()),
                show_projects=True,
                show_libraries=True
            )
            self.libraryloader.setStyleSheet(style.load_stylesheet())
        except Exception:
            self.log.warning(
                "Couldn't load Library loader tool for tray.",
                exc_info=True
            )

    def connect_with_modules(self, _enabled_modules):
        return

    def rest_api_initialization(self, rest_api_module):
        if self.tray_initialized:
            from .rest_api import AvalonRestApi
            self.rest_api_obj = AvalonRestApi()

    # Definition of Tray menu
    def tray_menu(self, tray_menu):
        from Qt import QtWidgets
        # Actions
        action_library_loader = QtWidgets.QAction(
            "Library loader", tray_menu
        )

        action_library_loader.triggered.connect(self.show_library_loader)

        tray_menu.addAction(action_library_loader)

    def tray_start(self, *_a, **_kw):
        return

    def tray_exit(self, *_a, **_kw):
        return

    def show_library_loader(self):
        self.libraryloader.show()

        # Raise and activate the window
        # for MacOS
        self.libraryloader.raise_()
        # for Windows
        self.libraryloader.activateWindow()
        self.libraryloader.refresh()
