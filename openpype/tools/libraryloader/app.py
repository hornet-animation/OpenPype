import sys

from Qt import QtWidgets, QtCore, QtGui

from avalon.api import AvalonMongoDB
from openpype import style
from openpype.tools.utils import lib as tools_lib
from openpype.tools.loader.widgets import (
    ThumbnailWidget,
    VersionWidget,
    FamilyListView,
    RepresentationWidget
)
from openpype.tools.utils.widgets import AssetWidget

from openpype.modules import ModulesManager

from . import lib
from .widgets import LibrarySubsetWidget

module = sys.modules[__name__]
module.window = None


class LibraryLoaderWindow(QtWidgets.QDialog):
    """Asset library loader interface"""

    tool_title = "Library Loader 0.5"
    tool_name = "library_loader"

    message_timeout = 5000

    def __init__(
        self, parent=None, icon=None, show_projects=False, show_libraries=True
    ):
        super(LibraryLoaderWindow, self).__init__(parent)

        # Window modifications
        self.setWindowTitle(self.tool_title)
        window_flags = QtCore.Qt.Window
        if not parent:
            window_flags |= QtCore.Qt.WindowStaysOnTopHint
        self.setWindowFlags(window_flags)
        self.setFocusPolicy(QtCore.Qt.StrongFocus)

        icon = QtGui.QIcon(style.app_icon_path())
        self.setWindowIcon(icon)

        self._first_show = True
        self._initial_refresh = False
        self._ignore_project_change = False

        dbcon = AvalonMongoDB()
        dbcon.install()
        dbcon.Session["AVALON_PROJECT"] = None

        self.dbcon = dbcon

        self.show_projects = show_projects
        self.show_libraries = show_libraries

        # Groups config
        self.groups_config = tools_lib.GroupsConfig(dbcon)
        self.family_config_cache = tools_lib.FamilyConfigCache(dbcon)

        # UI initialization
        main_splitter = QtWidgets.QSplitter(self)

        # --- Left part ---
        left_side_splitter = QtWidgets.QSplitter(main_splitter)
        left_side_splitter.setOrientation(QtCore.Qt.Vertical)

        # Project combobox
        projects_combobox = QtWidgets.QComboBox(left_side_splitter)
        combobox_delegate = QtWidgets.QStyledItemDelegate(self)
        projects_combobox.setItemDelegate(combobox_delegate)

        # Assets widget
        assets_widget = AssetWidget(
            dbcon, multiselection=True, parent=left_side_splitter
        )

        # Families widget
        families_filter_view = FamilyListView(
            dbcon, self.family_config_cache, left_side_splitter
        )
        left_side_splitter.addWidget(projects_combobox)
        left_side_splitter.addWidget(assets_widget)
        left_side_splitter.addWidget(families_filter_view)
        left_side_splitter.setStretchFactor(1, 65)
        left_side_splitter.setStretchFactor(2, 35)

        # --- Middle part ---
        # Subsets widget
        subsets_widget = LibrarySubsetWidget(
            dbcon,
            self.groups_config,
            self.family_config_cache,
            tool_name=self.tool_name,
            parent=self
        )

        # --- Right part ---
        thumb_ver_splitter = QtWidgets.QSplitter(main_splitter)
        thumb_ver_splitter.setOrientation(QtCore.Qt.Vertical)

        thumbnail_widget = ThumbnailWidget(dbcon, parent=thumb_ver_splitter)
        version_info_widget = VersionWidget(dbcon, parent=thumb_ver_splitter)

        thumb_ver_splitter.addWidget(thumbnail_widget)
        thumb_ver_splitter.addWidget(version_info_widget)

        thumb_ver_splitter.setStretchFactor(0, 30)
        thumb_ver_splitter.setStretchFactor(1, 35)

        manager = ModulesManager()
        sync_server = manager.modules_by_name.get("sync_server")
        sync_server_enabled = False
        if sync_server is not None:
            sync_server_enabled = sync_server.enabled

        repres_widget = None
        if sync_server_enabled:
            repres_widget = RepresentationWidget(
                dbcon, self.tool_name, parent=thumb_ver_splitter
            )
            thumb_ver_splitter.addWidget(repres_widget)

        main_splitter.addWidget(left_side_splitter)
        main_splitter.addWidget(subsets_widget)
        main_splitter.addWidget(thumb_ver_splitter)

        # --- Footer ---
        footer_widget = QtWidgets.QWidget(self)
        footer_widget.setFixedHeight(20)

        message_label = QtWidgets.QLabel(footer_widget)

        footer_layout = QtWidgets.QVBoxLayout(footer_widget)
        footer_layout.setContentsMargins(0, 0, 0, 0)
        footer_layout.addWidget(message_label)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(main_splitter)
        layout.addWidget(footer_widget)

        self.data = {
            "state": {
                "assetIds": None
            }
        }

        message_timer = QtCore.QTimer()
        message_timer.setInterval(self.message_timeout)
        message_timer.setSingleShot(True)

        message_timer.timeout.connect(self._on_message_timeout)

        families_filter_view.active_changed.connect(
            self._on_family_filter_change
        )
        assets_widget.selection_changed.connect(self.on_assetschanged)
        assets_widget.refresh_triggered.connect(self.on_assetschanged)
        assets_widget.view.clicked.connect(self.on_assetview_click)
        subsets_widget.active_changed.connect(self.on_subsetschanged)
        subsets_widget.version_changed.connect(self.on_versionschanged)
        subsets_widget.refreshed.connect(self._on_subset_refresh)
        projects_combobox.currentTextChanged.connect(self.on_project_change)

        self.sync_server = sync_server

        self._combobox_delegate = combobox_delegate
        self._projects_combobox = projects_combobox
        self._assets_widget = assets_widget
        self._families_filter_view = families_filter_view

        self._subsets_widget = subsets_widget

        self._version_info_widget = version_info_widget
        self._thumbnail_widget = thumbnail_widget
        self._repres_widget = repres_widget

        self._message_label = message_label
        self._message_timer = message_timer

        # Set default thumbnail on start
        thumbnail_widget.set_thumbnail(None)

        # Defaults
        if sync_server_enabled:
            main_splitter.setSizes([250, 1000, 550])
            self.resize(1800, 900)
        else:
            main_splitter.setSizes([250, 850, 200])
            self.resize(1300, 700)

    def showEvent(self, event):
        super(LibraryLoaderWindow, self).showEvent(event)
        if self._first_show:
            self._first_show = False
            self.setStyleSheet(style.load_stylesheet())

        if not self._initial_refresh:
            self._initial_refresh = True
            self.refresh()

    def on_assetview_click(self, *args):
        selection_model = self._subsets_widget.view.selectionModel()
        if selection_model.selectedIndexes():
            selection_model.clearSelection()

    def _set_projects(self):
        # Store current project
        old_project_name = self.current_project

        self._ignore_project_change = True

        # Cleanup
        self._projects_combobox.clear()

        # Fill combobox with projects
        select_project_item = QtGui.QStandardItem("< Select project >")
        select_project_item.setData(None, QtCore.Qt.UserRole + 1)

        combobox_items = [select_project_item]

        project_names = self.get_filtered_projects()

        for project_name in sorted(project_names):
            item = QtGui.QStandardItem(project_name)
            item.setData(project_name, QtCore.Qt.UserRole + 1)
            combobox_items.append(item)

        root_item = self._projects_combobox.model().invisibleRootItem()
        root_item.appendRows(combobox_items)

        index = 0
        self._ignore_project_change = False

        if old_project_name:
            index = self._projects_combobox.findText(
                old_project_name, QtCore.Qt.MatchFixedString
            )

        self._projects_combobox.setCurrentIndex(index)

    def get_filtered_projects(self):
        projects = list()
        for project in self.dbcon.projects():
            is_library = project.get("data", {}).get("library_project", False)
            if (
                (is_library and self.show_libraries) or
                (not is_library and self.show_projects)
            ):
                projects.append(project["name"])

        return projects

    def on_project_change(self):
        if self._ignore_project_change:
            return

        row = self._projects_combobox.currentIndex()
        index = self._projects_combobox.model().index(row, 0)
        project_name = index.data(QtCore.Qt.UserRole + 1)

        self.dbcon.Session["AVALON_PROJECT"] = project_name

        _config = lib.find_config()
        if hasattr(_config, "install"):
            _config.install()
        else:
            print(
                "Config `%s` has no function `install`" % _config.__name__
            )

        self._subsets_widget.on_project_change(project_name)
        if self._repres_widget:
            self._repres_widget.on_project_change(project_name)

        self.family_config_cache.refresh()
        self.groups_config.refresh()

        self._refresh_assets()
        self._assetschanged()

        project_name = self.dbcon.active_project() or "No project selected"
        title = "{} - {}".format(self.tool_title, project_name)
        self.setWindowTitle(title)

    @property
    def current_project(self):
        return self.dbcon.active_project() or None

    # -------------------------------
    # Delay calling blocking methods
    # -------------------------------

    def refresh(self):
        self.echo("Fetching results..")
        tools_lib.schedule(self._refresh, 50, channel="mongo")

    def on_assetschanged(self, *args):
        self.echo("Fetching asset..")
        tools_lib.schedule(self._assetschanged, 50, channel="mongo")

    def on_subsetschanged(self, *args):
        self.echo("Fetching subset..")
        tools_lib.schedule(self._subsetschanged, 50, channel="mongo")

    def on_versionschanged(self, *args):
        self.echo("Fetching version..")
        tools_lib.schedule(self._versionschanged, 150, channel="mongo")

    def _on_subset_refresh(self, has_item):
        self._subsets_widget.set_loading_state(
            loading=False, empty=not has_item
        )
        families = self._subsets_widget.get_subsets_families()
        self._families_filter_view.set_enabled_families(families)

    def set_context(self, context, refresh=True):
        self.echo("Setting context: {}".format(context))
        lib.schedule(
            lambda: self._set_context(context, refresh=refresh),
            50, channel="mongo"
        )

    # ------------------------------
    def _on_family_filter_change(self, families):
        self._subsets_widget.set_family_filters(families)

    def _refresh(self):
        if not self._initial_refresh:
            self._initial_refresh = True
        self._set_projects()

    def _refresh_assets(self):
        """Load assets from database"""
        if self.current_project is not None:
            # Ensure a project is loaded
            project_doc = self.dbcon.find_one(
                {"type": "project"},
                {"type": 1}
            )
            assert project_doc, "This is a bug"

        self._families_filter_view.set_enabled_families(set())
        self._families_filter_view.refresh()

        self._assets_widget.model.stop_fetch_thread()
        self._assets_widget.refresh()
        self._assets_widget.setFocus()

    def clear_assets_underlines(self):
        last_asset_ids = self.data["state"]["assetIds"]
        if not last_asset_ids:
            return

        assets_model = self._assets_widget.model
        id_role = assets_model.ObjectIdRole

        for index in tools_lib.iter_model_rows(assets_model, 0):
            if index.data(id_role) not in last_asset_ids:
                continue

            assets_model.setData(
                index, [], assets_model.subsetColorsRole
            )

    def _assetschanged(self):
        """Selected assets have changed"""
        subsets_model = self._subsets_widget.model

        subsets_model.clear()
        self.clear_assets_underlines()

        if not self.dbcon.Session.get("AVALON_PROJECT"):
            self._subsets_widget.set_loading_state(
                loading=False,
                empty=True
            )
            return

        # filter None docs they are silo
        asset_docs = self._assets_widget.get_selected_assets()
        if len(asset_docs) == 0:
            return

        asset_ids = [asset_doc["_id"] for asset_doc in asset_docs]
        # Start loading
        self._subsets_widget.set_loading_state(
            loading=bool(asset_ids),
            empty=True
        )

        subsets_model.set_assets(asset_ids)
        self._subsets_widget.view.setColumnHidden(
            subsets_model.Columns.index("asset"),
            len(asset_ids) < 2
        )

        # Clear the version information on asset change
        self._version_info_widget.set_version(None)
        self._thumbnail_widget.set_thumbnail(asset_docs)

        self.data["state"]["assetIds"] = asset_ids

        # reset repre list
        self._repres_widget.set_version_ids([])

    def _subsetschanged(self):
        asset_ids = self.data["state"]["assetIds"]
        # Skip setting colors if not asset multiselection
        if not asset_ids or len(asset_ids) < 2:
            self._versionschanged()
            return

        selected_subsets = self._subsets_widget.selected_subsets(
            _merged=True, _other=False
        )

        asset_models = {}
        asset_ids = []
        for subset_node in selected_subsets:
            asset_ids.extend(subset_node.get("assetIds", []))
        asset_ids = set(asset_ids)

        for subset_node in selected_subsets:
            for asset_id in asset_ids:
                if asset_id not in asset_models:
                    asset_models[asset_id] = []

                color = None
                if asset_id in subset_node.get("assetIds", []):
                    color = subset_node["subsetColor"]

                asset_models[asset_id].append(color)

        self.clear_assets_underlines()

        indexes = self._assets_widget.view.selectionModel().selectedRows()

        assets_model = self._assets_widget.model
        for index in indexes:
            id = index.data(assets_model.ObjectIdRole)
            if id not in asset_models:
                continue

            assets_model.setData(
                index, asset_models[id], assets_model.subsetColorsRole
            )
        # Trigger repaint
        self._assets_widget.view.updateGeometries()
        # Set version in Version Widget
        self._versionschanged()

    def _versionschanged(self):
        selection = self._subsets_widget.view.selectionModel()

        # Active must be in the selected rows otherwise we
        # assume it's not actually an "active" current index.
        version_docs = None
        version_doc = None
        active = selection.currentIndex()
        rows = selection.selectedRows(column=active.column())
        if active and active in rows:
            item = active.data(self._subsets_widget.model.ItemRole)
            if (
                item is not None
                and not (item.get("isGroup") or item.get("isMerged"))
            ):
                version_doc = item["version_document"]

        if rows:
            version_docs = []
            for index in rows:
                if not index or not index.isValid():
                    continue
                item = index.data(self._subsets_widget.model.ItemRole)
                if (
                    item is None
                    or item.get("isGroup")
                    or item.get("isMerged")
                ):
                    continue
                version_docs.append(item["version_document"])

        self._version_info_widget.set_version(version_doc)

        thumbnail_docs = version_docs
        if not thumbnail_docs:
            asset_docs = self._assets_widget.get_selected_assets()
            if len(asset_docs) > 0:
                thumbnail_docs = asset_docs

        self._thumbnail_widget.set_thumbnail(thumbnail_docs)

        version_ids = [doc["_id"] for doc in version_docs or []]
        self._repres_widget.set_version_ids(version_ids)

    def _set_context(self, context, refresh=True):
        """Set the selection in the interface using a context.
        The context must contain `asset` data by name.
        Note: Prior to setting context ensure `refresh` is triggered so that
              the "silos" are listed correctly, aside from that setting the
              context will force a refresh further down because it changes
              the active silo and asset.
        Args:
            context (dict): The context to apply.
        Returns:
            None
        """

        asset = context.get("asset", None)
        if asset is None:
            return

        if refresh:
            # Workaround:
            # Force a direct (non-scheduled) refresh prior to setting the
            # asset widget's silo and asset selection to ensure it's correctly
            # displaying the silo tabs. Calling `window.refresh()` and directly
            # `window.set_context()` the `set_context()` seems to override the
            # scheduled refresh and the silo tabs are not shown.
            self._refresh_assets()

        self._assets_widget.select_assets(asset)

    def _on_message_timeout(self):
        self._message_label.setText("")

    def echo(self, message):
        self._message_label.setText(str(message))
        print(message)
        self._message_timer.start()

    def closeEvent(self, event):
        # Kill on holding SHIFT
        modifiers = QtWidgets.QApplication.queryKeyboardModifiers()
        shift_pressed = QtCore.Qt.ShiftModifier & modifiers

        if shift_pressed:
            print("Force quitted..")
            self.setAttribute(QtCore.Qt.WA_DeleteOnClose)

        print("Good bye")
        return super(LibraryLoaderWindow, self).closeEvent(event)


def show(
    debug=False, parent=None, icon=None,
    show_projects=False, show_libraries=True
):
    """Display Loader GUI

    Arguments:
        debug (bool, optional): Run loader in debug-mode,
            defaults to False
        parent (QtCore.QObject, optional): The Qt object to parent to.
        use_context (bool): Whether to apply the current context upon launch

    """
    # Remember window
    if module.window is not None:
        try:
            module.window.show()

            # If the window is minimized then unminimize it.
            if module.window.windowState() & QtCore.Qt.WindowMinimized:
                module.window.setWindowState(QtCore.Qt.WindowActive)

            # Raise and activate the window
            module.window.raise_()             # for MacOS
            module.window.activateWindow()     # for Windows
            module.window.refresh()
            return
        except RuntimeError as e:
            if not e.message.rstrip().endswith("already deleted."):
                raise

            # Garbage collected
            module.window = None

    if debug:
        import traceback
        sys.excepthook = lambda typ, val, tb: traceback.print_last()

    with tools_lib.application():
        window = LibraryLoaderWindow(
            parent, icon, show_projects, show_libraries
        )
        window.show()

        module.window = window


def cli(args):

    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("project")

    show(show_projects=True, show_libraries=True)
