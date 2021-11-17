import time
import collections

import Qt
from Qt import QtWidgets, QtCore, QtGui

from avalon import style
from avalon.vendor import qtawesome

from openpype.style import get_objected_colors
from openpype.tools.flickcharm import FlickCharm

from .views import (
    TreeViewSpinner,
    DeselectableTreeView
)
from .models import RecursiveSortFilterProxyModel
from .lib import DynamicQThread

if Qt.__binding__ == "PySide":
    from PySide.QtGui import QStyleOptionViewItemV4
elif Qt.__binding__ == "PyQt4":
    from PyQt4.QtGui import QStyleOptionViewItemV4

ASSET_ID_ROLE = QtCore.Qt.UserRole + 1
ASSET_NAME_ROLE = QtCore.Qt.UserRole + 2
ASSET_LABEL_ROLE = QtCore.Qt.UserRole + 3
ASSET_UNDERLINE_COLORS_ROLE = QtCore.Qt.UserRole + 4


class AssetsView(TreeViewSpinner, DeselectableTreeView):
    """Item view.
    This implements a context menu.
    """

    def __init__(self, parent=None):
        super(AssetsView, self).__init__(parent)
        self.setIndentation(15)
        self.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.setHeaderHidden(True)

        self._flick_charm_activated = False
        self._flick_charm = FlickCharm(parent=self)
        self._before_flick_scroll_mode = None

    def activate_flick_charm(self):
        if self._flick_charm_activated:
            return
        self._flick_charm_activated = True
        self._before_flick_scroll_mode = self.verticalScrollMode()
        self._flick_charm.activateOn(self)
        self.setVerticalScrollMode(self.ScrollPerPixel)

    def deactivate_flick_charm(self):
        if not self._flick_charm_activated:
            return
        self._flick_charm_activated = False
        self._flick_charm.deactivateFrom(self)
        if self._before_flick_scroll_mode is not None:
            self.setVerticalScrollMode(self._before_flick_scroll_mode)

    def mousePressEvent(self, event):
        index = self.indexAt(event.pos())
        if not index.isValid():
            modifiers = QtWidgets.QApplication.keyboardModifiers()
            if modifiers == QtCore.Qt.ShiftModifier:
                return
            elif modifiers == QtCore.Qt.ControlModifier:
                return

        super(AssetsView, self).mousePressEvent(event)

    def set_loading_state(self, loading, empty):
        if self.is_loading != loading:
            if loading:
                self.spinner.repaintNeeded.connect(
                    self.viewport().update
                )
            else:
                self.spinner.repaintNeeded.disconnect()
                self.viewport().update()

        self.is_loading = loading
        self.is_empty = empty


class UnderlinesAssetDelegate(QtWidgets.QItemDelegate):
    bar_height = 3

    def __init__(self, *args, **kwargs):
        super(UnderlinesAssetDelegate, self).__init__(*args, **kwargs)
        asset_view_colors = get_objected_colors()["loader"]["asset-view"]
        self._selected_color = (
            asset_view_colors["selected"].get_qcolor()
        )
        self._hover_color = (
            asset_view_colors["hover"].get_qcolor()
        )
        self._selected_hover_color = (
            asset_view_colors["selected-hover"].get_qcolor()
        )

    def sizeHint(self, option, index):
        result = super(UnderlinesAssetDelegate, self).sizeHint(option, index)
        height = result.height()
        result.setHeight(height + self.bar_height)

        return result

    def paint(self, painter, option, index):
        # Qt4 compat
        if Qt.__binding__ in ("PySide", "PyQt4"):
            option = QStyleOptionViewItemV4(option)

        painter.save()

        item_rect = QtCore.QRect(option.rect)
        item_rect.setHeight(option.rect.height() - self.bar_height)

        subset_colors = index.data(ASSET_UNDERLINE_COLORS_ROLE) or []
        subset_colors_width = 0
        if subset_colors:
            subset_colors_width = option.rect.width() / len(subset_colors)

        subset_rects = []
        counter = 0
        for subset_c in subset_colors:
            new_color = None
            new_rect = None
            if subset_c:
                new_color = QtGui.QColor(*subset_c)

                new_rect = QtCore.QRect(
                    option.rect.left() + (counter * subset_colors_width),
                    option.rect.top() + (
                        option.rect.height() - self.bar_height
                    ),
                    subset_colors_width,
                    self.bar_height
                )
            subset_rects.append((new_color, new_rect))
            counter += 1

        # Background
        if option.state & QtWidgets.QStyle.State_Selected:
            if len(subset_colors) == 0:
                item_rect.setTop(item_rect.top() + (self.bar_height / 2))

            if option.state & QtWidgets.QStyle.State_MouseOver:
                bg_color = self._selected_hover_color
            else:
                bg_color = self._selected_color
        else:
            item_rect.setTop(item_rect.top() + (self.bar_height / 2))
            if option.state & QtWidgets.QStyle.State_MouseOver:
                bg_color = self._hover_color
            else:
                bg_color = QtGui.QColor()
                bg_color.setAlpha(0)

        # When not needed to do a rounded corners (easier and without
        #   painter restore):
        # painter.fillRect(
        #     item_rect,
        #     QtGui.QBrush(bg_color)
        # )
        pen = painter.pen()
        pen.setStyle(QtCore.Qt.NoPen)
        pen.setWidth(0)
        painter.setPen(pen)
        painter.setBrush(QtGui.QBrush(bg_color))
        painter.drawRoundedRect(option.rect, 3, 3)

        if option.state & QtWidgets.QStyle.State_Selected:
            for color, subset_rect in subset_rects:
                if not color or not subset_rect:
                    continue
                painter.fillRect(subset_rect, QtGui.QBrush(color))

        painter.restore()
        painter.save()

        # Icon
        icon_index = index.model().index(
            index.row(), index.column(), index.parent()
        )
        # - Default icon_rect if not icon
        icon_rect = QtCore.QRect(
            item_rect.left(),
            item_rect.top(),
            # To make sure it's same size all the time
            option.rect.height() - self.bar_height,
            option.rect.height() - self.bar_height
        )
        icon = index.model().data(icon_index, QtCore.Qt.DecorationRole)

        if icon:
            mode = QtGui.QIcon.Normal
            if not (option.state & QtWidgets.QStyle.State_Enabled):
                mode = QtGui.QIcon.Disabled
            elif option.state & QtWidgets.QStyle.State_Selected:
                mode = QtGui.QIcon.Selected

            if isinstance(icon, QtGui.QPixmap):
                icon = QtGui.QIcon(icon)
                option.decorationSize = icon.size() / icon.devicePixelRatio()

            elif isinstance(icon, QtGui.QColor):
                pixmap = QtGui.QPixmap(option.decorationSize)
                pixmap.fill(icon)
                icon = QtGui.QIcon(pixmap)

            elif isinstance(icon, QtGui.QImage):
                icon = QtGui.QIcon(QtGui.QPixmap.fromImage(icon))
                option.decorationSize = icon.size() / icon.devicePixelRatio()

            elif isinstance(icon, QtGui.QIcon):
                state = QtGui.QIcon.Off
                if option.state & QtWidgets.QStyle.State_Open:
                    state = QtGui.QIcon.On
                actual_size = option.icon.actualSize(
                    option.decorationSize, mode, state
                )
                option.decorationSize = QtCore.QSize(
                    min(option.decorationSize.width(), actual_size.width()),
                    min(option.decorationSize.height(), actual_size.height())
                )

            state = QtGui.QIcon.Off
            if option.state & QtWidgets.QStyle.State_Open:
                state = QtGui.QIcon.On

            icon.paint(
                painter, icon_rect,
                QtCore.Qt.AlignLeft, mode, state
            )

        # Text
        text_rect = QtCore.QRect(
            icon_rect.left() + icon_rect.width() + 2,
            item_rect.top(),
            item_rect.width(),
            item_rect.height()
        )

        painter.drawText(
            text_rect, QtCore.Qt.AlignVCenter,
            index.data(QtCore.Qt.DisplayRole)
        )

        painter.restore()


class AssetModel(QtGui.QStandardItemModel):
    """A model listing assets in the silo in the active project.

    The assets are displayed in a treeview, they are visually parented by
    a `visualParent` field in the database containing an `_id` to a parent
    asset.

    """

    _doc_fetched = QtCore.Signal()
    refreshed = QtCore.Signal(bool)

    # Asset document projection
    _asset_projection = {
        "type": 1,
        "schema": 1,
        "name": 1,
        "parent": 1,
        "data.visualParent": 1,
        "data.label": 1,
        "data.tags": 1,
        "data.icon": 1,
        "data.color": 1,
        "data.deprecated": 1
    }

    def __init__(self, dbcon, parent=None):
        super(AssetModel, self).__init__(parent=parent)
        self.dbcon = dbcon

        self._refreshing = False
        self._doc_fetching_thread = None
        self._doc_fetching_stop = False
        self._doc_payload = []

        self._doc_fetched.connect(self._on_docs_fetched)

        self._items_with_color_by_id = {}
        self._items_by_asset_id = {}

    def get_index_by_asset_id(self, asset_id):
        item = self._items_by_asset_id.get(asset_id)
        if item is not None:
            return item.index()
        return QtCore.QModelIndex()

    def get_indexes_by_asset_ids(self, asset_ids):
        return [
            self.get_index_by_asset_id(asset_id)
            for asset_id in asset_ids
        ]

    def get_index_by_asset_name(self, asset_name):
        indexes = self.get_indexes_by_asset_names([asset_name])
        for index in indexes:
            if index.isValid():
                return index
        return indexes[0]

    def get_indexes_by_asset_names(self, asset_names):
        asset_ids_by_name = {
            asset_name: None
            for asset_name in asset_names
        }

        for asset_id, item in self._items_by_asset_id.items():
            asset_name = item.data(ASSET_NAME_ROLE)
            if asset_name in asset_ids_by_name:
                asset_ids_by_name[asset_name] = asset_id

        asset_ids = [
            asset_ids_by_name[asset_name]
            for asset_name in asset_names
        ]

        return self.get_indexes_by_asset_ids(asset_ids)

    def refresh(self, force=False):
        """Refresh the data for the model."""
        # Skip fetch if there is already other thread fetching documents
        if self._refreshing:
            if not force:
                return
            self.stop_refresh()

        # Fetch documents from mongo
        # Restart payload
        self._refreshing = True
        self._doc_payload = []
        self._doc_fetching_thread = DynamicQThread(self._threaded_fetch)
        self._doc_fetching_thread.start()

    def stop_refresh(self):
        self._stop_fetch_thread()

    def clear_underlines(self):
        for asset_id in tuple(self._items_with_color_by_id.keys()):
            item = self._items_with_color_by_id.pop(asset_id)
            item.setData(None, ASSET_UNDERLINE_COLORS_ROLE)

    def set_underline_colors(self, colors_by_asset_id):
        self.clear_underlines()

        for asset_id, colors in colors_by_asset_id.items():
            item = self._items_by_asset_id.get(asset_id)
            if item is None:
                continue
            item.setData(colors, ASSET_UNDERLINE_COLORS_ROLE)

    def _on_docs_fetched(self):
        if not self._refreshing:
            root_item = self.invisibleRootItem()
            root_item.removeRows(0, root_item.rowCount())
            self._items_by_asset_id = {}
            self._items_with_color_by_id = {}
            return

        asset_docs = self._doc_payload

        asset_ids = set()
        asset_docs_by_id = {}
        asset_ids_by_parents = collections.defaultdict(set)
        for asset_doc in asset_docs:
            asset_id = asset_doc["_id"]
            asset_data = asset_doc.get("data") or {}
            parent_id = asset_data.get("visualParent")
            asset_ids.add(asset_id)
            asset_docs_by_id[asset_id] = asset_doc
            asset_ids_by_parents[parent_id].add(asset_id)

        root_item = self.invisibleRootItem()
        asset_items_queue = collections.deque()
        asset_items_queue.append((None, root_item))

        removed_asset_ids = (
            set(self._items_by_asset_id.keys()) - set(asset_docs_by_id.keys())
        )
        while asset_items_queue:
            parent_id, parent_item = asset_items_queue.popleft()
            children_ids = asset_ids_by_parents[parent_id]
            if not children_ids:
                continue

            for row in reversed(range(parent_item.rowCount())):
                child_item = parent_item.child(row, 0)
                asset_id = child_item.data(ASSET_ID_ROLE)
                if asset_id not in children_ids:
                    parent_item.removeRow(row)
                    continue

                children_ids.remove(asset_id)
                asset_items_queue.append((asset_id, child_item))

            new_items = []
            for asset_id in children_ids:
                item = QtGui.QStandardItem()
                item.setEditable(False)
                item.setData(asset_id, ASSET_ID_ROLE)
                new_items.append(item)
                self._items_by_asset_id[asset_id] = item
                asset_items_queue.append((asset_id, item))

            if new_items:
                parent_item.appendRows(new_items)

        for asset_id in removed_asset_ids:
            self._items_by_asset_id.pop(asset_id)
            if asset_id in self._items_with_color_by_id:
                self._items_with_color_by_id.pop(asset_id)

        # Refresh data
        for asset_id, item in self._items_by_asset_id.items():
            asset_doc = asset_docs_by_id[asset_id]

            asset_name = asset_doc["name"]
            if item.data(ASSET_NAME_ROLE) != asset_name:
                item.setData(asset_name, ASSET_NAME_ROLE)

            asset_data = asset_doc.get("data") or {}
            asset_label = asset_data.get("label") or asset_name
            if item.data(ASSET_LABEL_ROLE) != asset_label:
                item.setData(asset_label, QtCore.Qt.DisplayRole)
                item.setData(asset_label, ASSET_LABEL_ROLE)

            icon_color = asset_data.get("color") or style.colors.default
            icon_name = asset_data.get("icon")
            if not icon_name:
                # Use default icons if no custom one is specified.
                # If it has children show a full folder, otherwise
                # show an open folder
                if item.rowCount() > 0:
                    icon_name = "folder"
                else:
                    icon_name = "folder-o"

            try:
                # font-awesome key
                full_icon_name = "fa.{0}".format(icon_name)
                icon = qtawesome.icon(full_icon_name, color=icon_color)
                item.setData(icon, QtCore.Qt.DecorationRole)

            except Exception as exception:
                pass

        self.refreshed.emit(bool(self._items_by_asset_id))

        self._stop_fetch_thread()

    def _threaded_fetch(self):
        asset_docs = self._fetch_asset_docs()
        if not self._refreshing:
            return

        self._doc_payload = asset_docs

        # Emit doc fetched only if was not stopped
        self._doc_fetched.emit()

    def _fetch_asset_docs(self):
        if not self.dbcon.Session.get("AVALON_PROJECT"):
            return []

        project_doc = self.dbcon.find_one(
            {"type": "project"},
            {"_id": True}
        )
        if not project_doc:
            return []

        # Get all assets sorted by name
        return list(self.dbcon.find(
            {"type": "asset"},
            self._asset_projection
        ))

    def _stop_fetch_thread(self):
        self._refreshing = False
        if self._doc_fetching_thread is not None:
            while self._doc_fetching_thread.isRunning():
                time.sleep(0.01)
            self._doc_fetching_thread = None


class AssetsWidget(QtWidgets.QWidget):
    """A Widget to display a tree of assets with filter

    To list the assets of the active project:
        >>> # widget = AssetsWidget()
        >>> # widget.refresh()
        >>> # widget.show()

    """

    # on model refresh
    refresh_triggered = QtCore.Signal()
    refreshed = QtCore.Signal()
    # on view selection change
    selection_changed = QtCore.Signal()

    def __init__(self, dbcon, parent=None):
        super(AssetsWidget, self).__init__(parent=parent)

        self.dbcon = dbcon

        # Tree View
        model = AssetModel(dbcon=self.dbcon, parent=self)
        proxy = RecursiveSortFilterProxyModel()
        proxy.setSourceModel(model)
        proxy.setFilterCaseSensitivity(QtCore.Qt.CaseInsensitive)
        proxy.setSortCaseSensitivity(QtCore.Qt.CaseInsensitive)

        view = AssetsView(self)
        view.setModel(proxy)

        current_asset_icon = qtawesome.icon(
            "fa.arrow-down", color=style.colors.light
        )
        current_asset_btn = QtWidgets.QPushButton(self)
        current_asset_btn.setIcon(current_asset_icon)
        current_asset_btn.setToolTip("Go to Asset from current Session")
        # Hide by default
        current_asset_btn.setVisible(False)

        refresh_icon = qtawesome.icon("fa.refresh", color=style.colors.light)
        refresh_btn = QtWidgets.QPushButton(self)
        refresh_btn.setIcon(refresh_icon)
        refresh_btn.setToolTip("Refresh items")

        filter_input = QtWidgets.QLineEdit(self)
        filter_input.setPlaceholderText("Filter assets..")

        # Header
        header_layout = QtWidgets.QHBoxLayout()
        header_layout.addWidget(filter_input)
        header_layout.addWidget(current_asset_btn)
        header_layout.addWidget(refresh_btn)

        # Layout
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.addLayout(header_layout)
        layout.addWidget(view)

        # Signals/Slots
        filter_input.textChanged.connect(self._on_filter_text_change)

        selection_model = view.selectionModel()
        selection_model.selectionChanged.connect(self._on_selection_change)
        refresh_btn.clicked.connect(self.refresh)
        current_asset_btn.clicked.connect(self.set_current_session_asset)
        model.refreshed.connect(self._on_model_refresh)

        self._current_asset_btn = current_asset_btn
        self._model = model
        self._proxy = proxy
        self._view = view

        self.model_selection = {}

    def refresh(self):
        self._refresh_model()

    def stop_refresh(self):
        self._model.stop_refresh()

    def set_current_session_asset(self):
        asset_name = self.dbcon.Session.get("AVALON_ASSET")
        if asset_name:
            self.select_asset_by_name(asset_name)

    def set_current_asset_btn_visibility(self, visible=None):
        """Hide set current asset button.

        Not all tools support using of current context asset.
        """
        if visible is None:
            visible = not self._current_asset_btn.isVisible()
        self._current_asset_btn.setVisible(visible)

    def select_asset(self, asset_id):
        index = self._model.get_index_by_asset_id(asset_id)
        new_index = self._proxy.mapFromSource(index)
        self._select_indexes([new_index])

    def select_asset_by_name(self, asset_name):
        index = self._model.get_index_by_asset_name(asset_name)
        new_index = self._proxy.mapFromSource(index)
        self._select_indexes([new_index])

    def activate_flick_charm(self):
        self._view.activate_flick_charm()

    def deactivate_flick_charm(self):
        self._view.deactivate_flick_charm()

    def _on_selection_change(self):
        self.selection_changed.emit()

    def _on_filter_text_change(self, new_text):
        self._proxy.setFilterFixedString(new_text)

    def _on_model_refresh(self, has_item):
        self._proxy.sort(0)
        self._set_loading_state(loading=False, empty=not has_item)
        self.refreshed.emit()

    def _refresh_model(self):
        # Store selection
        self._set_loading_state(loading=True, empty=True)

        # Trigger signal before refresh is called
        self.refresh_triggered.emit()
        # Refresh model
        self._model.refresh()

    def _set_loading_state(self, loading, empty):
        self._view.set_loading_state(loading, empty)

    def _select_indexes(self, indexes):
        valid_indexes = [
            index
            for index in indexes
            if index.isValid()
        ]
        if not valid_indexes:
            return

        selection_model = self._view.selectionModel()
        selection_model.clearSelection()

        mode = selection_model.Select | selection_model.Rows
        for index in valid_indexes:
            self._view.expand(self._proxy.parent(index))
            selection_model.select(index, mode)
        self._view.setCurrentIndex(valid_indexes[0])


class SingleSelectAssetsWidget(AssetsWidget):
    def get_selected_asset_id(self):
        """Return the asset item of the current selection."""
        selection_model = self._view.selectionModel()
        indexes = selection_model.selectedRows()
        for index in indexes:
            return index.data(ASSET_ID_ROLE)
        return None

    def get_selected_asset_name(self):
        """Return the asset document of the current selection."""
        selection_model = self._view.selectionModel()
        indexes = selection_model.selectedRows()
        for index in indexes:
            return index.data(ASSET_NAME_ROLE)
        return None


class MultiSelectAssetsWidget(AssetsWidget):
    def __init__(self, *args, **kwargs):
        super(MultiSelectAssetsWidget, self).__init__(*args, **kwargs)
        delegate = UnderlinesAssetDelegate()

        self._view.setSelectionMode(QtWidgets.QTreeView.ExtendedSelection)
        self._view.setItemDelegate(delegate)

        self._delegate = delegate

    def get_selected_asset_ids(self):
        """Return the asset item of the current selection."""
        selection_model = self._view.selectionModel()
        indexes = selection_model.selectedRows()
        return [
            index.data(ASSET_ID_ROLE)
            for index in indexes
        ]

    def get_selected_asset_names(self):
        """Return the asset document of the current selection."""
        selection_model = self._view.selectionModel()
        indexes = selection_model.selectedRows()
        return [
            index.data(ASSET_NAME_ROLE)
            for index in indexes
        ]

    def select_assets(self, asset_ids):
        indexes = self._model.get_indexes_by_asset_ids(asset_ids)
        new_indexes = [
            self._proxy.mapFromSource(index)
            for index in indexes
        ]
        self._select_indexes(new_indexes)

    def select_assets_by_name(self, asset_names):
        indexes = self._model.get_indexes_by_asset_names(asset_names)
        new_indexes = [
            self._proxy.mapFromSource(index)
            for index in indexes
        ]
        self._select_indexes(new_indexes)

    def clear_underlines(self):
        self._model.clear_underlines()

        self._view.updateGeometries()

    def set_underline_colors(self, colors_by_asset_id):
        self._model.set_underline_colors(colors_by_asset_id)
        # Trigger repaint
        self._view.updateGeometries()
