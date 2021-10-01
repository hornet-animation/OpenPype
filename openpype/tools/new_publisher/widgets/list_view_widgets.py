import collections

from Qt import QtWidgets, QtCore, QtGui

from openpype.style import get_objected_colors
from openpype.widgets.nice_checkbox import NiceCheckbox
from .widgets import AbstractInstanceView
from .icons import get_image
from ..constants import (
    INSTANCE_ID_ROLE,
    SORT_VALUE_ROLE,
    IS_GROUP_ROLE,
    CONTEXT_ID,
    CONTEXT_LABEL
)


class ListItemDelegate(QtWidgets.QStyledItemDelegate):
    """Generic delegate for instance header"""
    radius_ratio = 0.3

    def __init__(self, parent):
        super(ListItemDelegate, self).__init__(parent)

        colors_data = get_objected_colors()
        group_color_info = colors_data["publisher"]["list-view-group"]

        self._group_colors = {
            key: value.get_qcolor()
            for key, value in group_color_info.items()
        }

    def paint(self, painter, option, index):
        if index.data(IS_GROUP_ROLE):
            self.group_item_paint(painter, option, index)
        else:
            super(ListItemDelegate, self).paint(painter, option, index)

    def group_item_paint(self, painter, option, index):
        self.initStyleOption(option, index)

        bg_rect = QtCore.QRectF(
            option.rect.left(), option.rect.top() + 1,
            option.rect.width(), option.rect.height() - 2
        )
        ratio = bg_rect.height() * self.radius_ratio
        bg_path = QtGui.QPainterPath()
        bg_path.addRoundedRect(
            QtCore.QRectF(bg_rect), ratio, ratio
        )

        painter.save()
        painter.setRenderHints(
            painter.Antialiasing
            | painter.SmoothPixmapTransform
            | painter.TextAntialiasing
        )

        # Draw backgrounds
        painter.fillPath(bg_path, self._group_colors["bg"])
        selected = option.state & QtWidgets.QStyle.State_Selected
        hovered = option.state & QtWidgets.QStyle.State_MouseOver
        if selected and hovered:
            painter.fillPath(bg_path, self._group_colors["bg-selected-hover"])

        elif hovered:
            painter.fillPath(bg_path, self._group_colors["bg-hover"])

        painter.restore()


class InstanceListItemWidget(QtWidgets.QWidget):
    active_changed = QtCore.Signal(str, bool)

    def __init__(self, instance, parent):
        super(InstanceListItemWidget, self).__init__(parent)

        self.instance = instance

        subset_name_label = QtWidgets.QLabel(instance.data["subset"], self)
        subset_name_label.setObjectName("ListViewSubsetName")

        active_checkbox = NiceCheckbox(parent=self)
        active_checkbox.setChecked(instance.data["active"])

        layout = QtWidgets.QHBoxLayout(self)
        content_margins = layout.contentsMargins()
        layout.setContentsMargins(content_margins.left() + 2, 0, 2, 0)
        layout.addWidget(subset_name_label)
        layout.addStretch(1)
        layout.addWidget(active_checkbox)

        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        subset_name_label.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        active_checkbox.setAttribute(QtCore.Qt.WA_TranslucentBackground)

        active_checkbox.stateChanged.connect(self._on_active_change)

        self.subset_name_label = subset_name_label
        self.active_checkbox = active_checkbox

        self._has_valid_context = None

        self._set_valid_property(instance.has_valid_context)

    def _set_valid_property(self, valid):
        if self._has_valid_context == valid:
            return
        self._has_valid_context = valid
        state = ""
        if not valid:
            state = "invalid"
        self.subset_name_label.setProperty("state", state)
        self.subset_name_label.style().polish(self.subset_name_label)

    def is_active(self):
        return self.instance.data["active"]

    def set_active(self, new_value):
        checkbox_value = self.active_checkbox.isChecked()
        instance_value = self.instance.data["active"]
        if new_value is None:
            new_value = not instance_value

        # First change instance value and them change checkbox
        # - prevent to trigger `active_changed` signal
        if instance_value != new_value:
            self.instance.data["active"] = new_value

        if checkbox_value != new_value:
            self.active_checkbox.setChecked(new_value)

    def update_instance(self, instance):
        self.instance = instance
        self.update_instance_values()

    def update_instance_values(self):
        self.set_active(self.instance.data["active"])
        self._set_valid_property(self.instance.has_valid_context)

    def _on_active_change(self):
        new_value = self.active_checkbox.isChecked()
        old_value = self.instance.data["active"]
        if new_value == old_value:
            return

        self.instance.data["active"] = new_value
        self.active_changed.emit(self.instance.id, new_value)


class ListContextWidget(QtWidgets.QFrame):
    def __init__(self, parent):
        super(ListContextWidget, self).__init__(parent)

        label_widget = QtWidgets.QLabel(CONTEXT_LABEL, self)

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(5, 0, 2, 0)
        layout.addWidget(
            label_widget, 1, QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter
        )

        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        label_widget.setAttribute(QtCore.Qt.WA_TranslucentBackground)

        self.label_widget = label_widget


class InstanceListGroupWidget(QtWidgets.QFrame):
    expand_changed = QtCore.Signal(str, bool)
    toggle_requested = QtCore.Signal(str, int)

    def __init__(self, family, parent):
        super(InstanceListGroupWidget, self).__init__(parent)
        self.setObjectName("InstanceListGroupWidget")

        self.family = family
        self._expanded = False

        expand_btn = QtWidgets.QToolButton(self)
        expand_btn.setObjectName("ArrowBtn")
        expand_btn.setArrowType(QtCore.Qt.RightArrow)
        expand_btn.setMaximumWidth(14)

        subset_name_label = QtWidgets.QLabel(family, self)

        toggle_checkbox = NiceCheckbox(parent=self)

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(5, 0, 2, 0)
        layout.addWidget(expand_btn)
        layout.addWidget(
            subset_name_label, 1, QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter
        )
        layout.addWidget(toggle_checkbox, 0)

        # self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        subset_name_label.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        expand_btn.setAttribute(QtCore.Qt.WA_TranslucentBackground)

        expand_btn.clicked.connect(self._on_expand_clicked)
        toggle_checkbox.stateChanged.connect(self._on_checkbox_change)

        self._ignore_state_change = False

        self._expected_checkstate = None

        self.subset_name_label = subset_name_label
        self.expand_btn = expand_btn
        self.toggle_checkbox = toggle_checkbox

    def set_checkstate(self, state):
        if self.checkstate() == state:
            return
        self._ignore_state_change = True
        self.toggle_checkbox.setCheckState(state)
        self._ignore_state_change = False

    def checkstate(self):
        return self.toggle_checkbox.checkState()

    def _on_checkbox_change(self, state):
        if not self._ignore_state_change:
            self.toggle_requested.emit(self.family, state)

    def _on_expand_clicked(self):
        self.expand_changed.emit(self.family, not self._expanded)

    def set_expanded(self, expanded):
        if self._expanded == expanded:
            return

        self._expanded = expanded
        if expanded:
            self.expand_btn.setArrowType(QtCore.Qt.DownArrow)
        else:
            self.expand_btn.setArrowType(QtCore.Qt.RightArrow)


class InstanceTreeView(QtWidgets.QTreeView):
    toggle_requested = QtCore.Signal(int)

    def __init__(self, *args, **kwargs):
        super(InstanceTreeView, self).__init__(*args, **kwargs)

        self.setObjectName("InstanceListView")
        self.setHeaderHidden(True)
        self.setIndentation(0)
        self.setExpandsOnDoubleClick(False)
        self.setSelectionMode(
            QtWidgets.QAbstractItemView.ExtendedSelection
        )
        self.viewport().setMouseTracking(True)
        self._pressed_group_index = None

    def _expand_item(self, index, expand=None):
        is_expanded = self.isExpanded(index)
        if expand is None:
            expand = not is_expanded

        if expand != is_expanded:
            if expand:
                self.expand(index)
            else:
                self.collapse(index)

    def get_selected_instance_ids(self):
        instance_ids = set()
        for index in self.selectionModel().selectedIndexes():
            instance_id = index.data(INSTANCE_ID_ROLE)
            if instance_id is not None:
                instance_ids.add(instance_id)
        return instance_ids

    def event(self, event):
        if not event.type() == QtCore.QEvent.KeyPress:
            pass

        elif event.key() == QtCore.Qt.Key_Space:
            self.toggle_requested.emit(-1)
            return True

        elif event.key() == QtCore.Qt.Key_Backspace:
            self.toggle_requested.emit(0)
            return True

        elif event.key() == QtCore.Qt.Key_Return:
            self.toggle_requested.emit(1)
            return True

        return super(InstanceTreeView, self).event(event)

    def _mouse_press(self, event):
        if event.button() != QtCore.Qt.LeftButton:
            return

        pressed_group_index = None
        pos_index = self.indexAt(event.pos())
        if pos_index.data(IS_GROUP_ROLE):
            pressed_group_index = pos_index

        self._pressed_group_index = pressed_group_index

    def mousePressEvent(self, event):
        if not self._mouse_press(event):
            super(InstanceTreeView, self).mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        if not self._mouse_press(event):
            super(InstanceTreeView, self).mouseDoubleClickEvent(event)

    def _mouse_release(self, event, pressed_index):
        if event.button() != QtCore.Qt.LeftButton:
            return False

        pos_index = self.indexAt(event.pos())
        if not pos_index.data(IS_GROUP_ROLE) or pressed_index != pos_index:
            return False

        if self.state() == QtWidgets.QTreeView.State.DragSelectingState:
            indexes = self.selectionModel().selectedIndexes()
            if len(indexes) != 1 or indexes[0] != pos_index:
                return False

        self._expand_item(pos_index)
        return True

    def mouseReleaseEvent(self, event):
        pressed_index = self._pressed_group_index
        self._pressed_group_index = None
        result = self._mouse_release(event, pressed_index)
        if not result:
            super(InstanceTreeView, self).mouseReleaseEvent(event)


class InstanceListView(AbstractInstanceView):
    def __init__(self, controller, parent):
        super(InstanceListView, self).__init__(parent)

        self.controller = controller

        instance_view = InstanceTreeView(self)
        instance_delegate = ListItemDelegate(instance_view)
        instance_view.setItemDelegate(instance_delegate)
        instance_model = QtGui.QStandardItemModel()

        proxy_model = QtCore.QSortFilterProxyModel()
        proxy_model.setSourceModel(instance_model)
        proxy_model.setFilterCaseSensitivity(QtCore.Qt.CaseInsensitive)
        proxy_model.setSortRole(SORT_VALUE_ROLE)
        proxy_model.setFilterKeyColumn(0)
        proxy_model.setDynamicSortFilter(True)

        instance_view.setModel(proxy_model)

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(instance_view)

        instance_view.selectionModel().selectionChanged.connect(
            self._on_selection_change
        )
        instance_view.collapsed.connect(self._on_collapse)
        instance_view.expanded.connect(self._on_expand)
        instance_view.toggle_requested.connect(self._on_toggle_request)

        self._group_items = {}
        self._group_widgets = {}
        self._widgets_by_id = {}
        self._family_by_instance_id = {}
        self._context_item = None
        self._context_widget = None

        self.instance_view = instance_view
        self._instance_delegate = instance_delegate
        self.instance_model = instance_model
        self.proxy_model = proxy_model

    def _on_expand(self, index):
        family = index.data(SORT_VALUE_ROLE)
        group_widget = self._group_widgets.get(family)
        if group_widget:
            group_widget.set_expanded(True)

    def _on_collapse(self, index):
        family = index.data(SORT_VALUE_ROLE)
        group_widget = self._group_widgets.get(family)
        if group_widget:
            group_widget.set_expanded(False)

    def _on_toggle_request(self, toggle):
        selected_instance_ids = self.instance_view.get_selected_instance_ids()
        if toggle == -1:
            active = None
        elif toggle == 1:
            active = True
        else:
            active = False

        for instance_id in selected_instance_ids:
            widget = self._widgets_by_id.get(instance_id)
            if widget is not None:
                widget.set_active(active)

    def _update_family_checkstate(self, family):
        widget = self._group_widgets.get(family)
        if widget is None:
            return

        activity = None
        for instance_id, _family in self._family_by_instance_id.items():
            if _family != family:
                continue

            instance_widget = self._widgets_by_id.get(instance_id)
            if not instance_widget:
                continue

            if activity is None:
                activity = int(instance_widget.is_active())

            elif activity != instance_widget.is_active():
                activity = -1
                break

        if activity is None:
            return

        state = QtCore.Qt.PartiallyChecked
        if activity == 0:
            state = QtCore.Qt.Unchecked
        elif activity == 1:
            state = QtCore.Qt.Checked
        widget.set_checkstate(state)

    def refresh(self):
        instances_by_family = collections.defaultdict(list)
        families = set()
        for instance in self.controller.instances:
            family = instance.data["family"]
            families.add(family)
            instances_by_family[family].append(instance)

        sort_at_the_end = False
        root_item = self.instance_model.invisibleRootItem()

        context_item = None
        if self._context_item is None:
            sort_at_the_end = True
            context_item = QtGui.QStandardItem()
            context_item.setData(0, SORT_VALUE_ROLE)
            context_item.setData(CONTEXT_ID, INSTANCE_ID_ROLE)

            root_item.appendRow(context_item)

            index = self.instance_model.index(
                context_item.row(), context_item.column()
            )
            proxy_index = self.proxy_model.mapFromSource(index)
            widget = ListContextWidget(self.instance_view)
            self.instance_view.setIndexWidget(proxy_index, widget)

            self._context_widget = widget
            self._context_item = context_item

        new_group_items = []
        for family in families:
            if family in self._group_items:
                continue

            group_item = QtGui.QStandardItem()
            group_item.setData(family, SORT_VALUE_ROLE)
            group_item.setData(True, IS_GROUP_ROLE)
            group_item.setFlags(QtCore.Qt.ItemIsEnabled)
            self._group_items[family] = group_item
            new_group_items.append(group_item)

        if new_group_items:
            sort_at_the_end = True
            root_item.appendRows(new_group_items)

        for group_item in new_group_items:
            index = self.instance_model.index(
                group_item.row(), group_item.column()
            )
            proxy_index = self.proxy_model.mapFromSource(index)
            family = group_item.data(SORT_VALUE_ROLE)
            widget = InstanceListGroupWidget(family, self.instance_view)
            widget.expand_changed.connect(self._on_group_expand_request)
            widget.toggle_requested.connect(self._on_group_toggle_request)
            self._group_widgets[family] = widget
            self.instance_view.setIndexWidget(proxy_index, widget)

        for family in tuple(self._group_items.keys()):
            if family in families:
                continue

            group_item = self._group_items.pop(family)
            root_item.removeRow(group_item.row())
            widget = self._group_widgets.pop(family)
            widget.deleteLater()

        expand_families = set()
        for family, group_item in self._group_items.items():
            to_remove = set()
            existing_mapping = {}

            group_index = self.instance_model.index(
                group_item.row(), group_item.column()
            )

            for idx in range(group_item.rowCount()):
                index = self.instance_model.index(idx, 0, group_index)
                instance_id = index.data(INSTANCE_ID_ROLE)
                to_remove.add(instance_id)
                existing_mapping[instance_id] = idx

            new_items = []
            new_items_with_instance = []
            activity = None
            for instance in instances_by_family[family]:
                instance_id = instance.data["uuid"]
                if activity is None:
                    activity = int(instance.data["active"])
                elif activity == -1:
                    pass
                elif activity != instance.data["active"]:
                    activity = -1

                self._family_by_instance_id[instance_id] = family
                if instance_id in to_remove:
                    to_remove.remove(instance_id)
                    widget = self._widgets_by_id[instance_id]
                    widget.update_instance(instance)
                    continue

                item = QtGui.QStandardItem()
                item.setData(instance.data["subset"], SORT_VALUE_ROLE)
                item.setData(instance.data["uuid"], INSTANCE_ID_ROLE)
                new_items.append(item)
                new_items_with_instance.append((item, instance))

            state = QtCore.Qt.PartiallyChecked
            if activity == 0:
                state = QtCore.Qt.Unchecked
            elif activity == 1:
                state = QtCore.Qt.Checked

            widget = self._group_widgets[family]
            widget.set_checkstate(state)

            idx_to_remove = []
            for instance_id in to_remove:
                idx_to_remove.append(existing_mapping[instance_id])

            for idx in reversed(sorted(idx_to_remove)):
                group_item.removeRows(idx, 1)

            for instance_id in to_remove:
                self._family_by_instance_id.pop(instance_id)
                widget = self._widgets_by_id.pop(instance_id)
                widget.deleteLater()

            if new_items:
                sort_at_the_end = True

                group_item.appendRows(new_items)

                for item, instance in new_items_with_instance:
                    if not instance.has_valid_context:
                        expand_families.add(family)
                    item_index = self.instance_model.index(
                        item.row(),
                        item.column(),
                        group_index
                    )
                    proxy_index = self.proxy_model.mapFromSource(item_index)
                    widget = InstanceListItemWidget(
                        instance, self.instance_view
                    )
                    widget.active_changed.connect(self._on_active_changed)
                    self.instance_view.setIndexWidget(proxy_index, widget)
                    self._widgets_by_id[instance.data["uuid"]] = widget

            # Trigger sort at the end of refresh
            if sort_at_the_end:
                self.proxy_model.sort(0)

        for family in expand_families:
            family_item = self._group_items[family]
            proxy_index = self.proxy_model.mapFromSource(family_item.index())

            self.instance_view.expand(proxy_index)

    def refresh_instance_states(self):
        for widget in self._widgets_by_id.values():
            widget.update_instance_values()

    def _on_active_changed(self, changed_instance_id, new_value):
        selected_instances, _ = self.get_selected_items()

        selected_ids = set()
        found = False
        for instance in selected_instances:
            selected_ids.add(instance.id)
            if not found and instance.id == changed_instance_id:
                found = True

        if not found:
            selected_ids = set()
            selected_ids.add(changed_instance_id)

        self._change_active_instances(selected_ids, new_value)
        families = set()
        for instance_id in selected_ids:
            family = self._family_by_instance_id.get(instance_id)
            if family is not None:
                families.add(family)

        for family in families:
            self._update_family_checkstate(family)

    def _change_active_instances(self, instance_ids, new_value):
        if not instance_ids:
            return

        changed_ids = set()
        for instance_id in instance_ids:
            widget = self._widgets_by_id.get(instance_id)
            if widget:
                changed_ids.add(instance_id)
                widget.set_active(new_value)

        if changed_ids:
            self.active_changed.emit()

    def get_selected_items(self):
        instances = []
        instances_by_id = {}
        context_selected = False
        for instance in self.controller.instances:
            instance_id = instance.data["uuid"]
            instances_by_id[instance_id] = instance

        for index in self.instance_view.selectionModel().selectedIndexes():
            instance_id = index.data(INSTANCE_ID_ROLE)
            if not context_selected and instance_id == CONTEXT_ID:
                context_selected = True

            elif instance_id is not None:
                instance = instances_by_id.get(instance_id)
                if instance:
                    instances.append(instance)

        return instances, context_selected

    def _on_selection_change(self, *_args):
        self.selection_changed.emit()

    def _on_group_expand_request(self, family, expanded):
        group_item = self._group_items.get(family)
        if not group_item:
            return

        group_index = self.instance_model.index(
            group_item.row(), group_item.column()
        )
        proxy_index = self.proxy_model.mapFromSource(group_index)
        self.instance_view.setExpanded(proxy_index, expanded)

    def _on_group_toggle_request(self, family, state):
        if state == QtCore.Qt.PartiallyChecked:
            return

        if state == QtCore.Qt.Checked:
            active = True
        else:
            active = False

        group_item = self._group_items.get(family)
        if not group_item:
            return

        instance_ids = set()
        for row in range(group_item.rowCount()):
            item = group_item.child(row)
            instance_id = item.data(INSTANCE_ID_ROLE)
            if instance_id is not None:
                instance_ids.add(instance_id)

        self._change_active_instances(instance_ids, active)

        proxy_index = self.proxy_model.mapFromSource(group_item.index())
        if not self.instance_view.isExpanded(proxy_index):
            self.instance_view.expand(proxy_index)
