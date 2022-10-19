from Qt import QtWidgets, QtCore

from .border_label_widget import BorderedLabelWidget

from .card_view_widgets import InstanceCardView
from .list_view_widgets import InstanceListView
from .widgets import (
    SubsetAttributesWidget,
    CreateInstanceBtn,
    RemoveInstanceBtn,
    ChangeViewBtn,
)
from .create_widget import CreateWidget


class OverviewWidget(QtWidgets.QFrame):
    active_changed = QtCore.Signal()
    instance_context_changed = QtCore.Signal()
    create_requested = QtCore.Signal()

    anim_end_value = 200
    anim_duration = 200

    def __init__(self, controller, parent):
        super(OverviewWidget, self).__init__(parent)

        self._refreshing_instances = False
        self._controller = controller

        create_widget = CreateWidget(controller, self)

        # --- Created Subsets/Instances ---
        # Common widget for creation and overview
        subset_views_widget = BorderedLabelWidget(
            "Subsets to publish", self
        )

        subset_view_cards = InstanceCardView(controller, subset_views_widget)
        subset_list_view = InstanceListView(controller, subset_views_widget)

        subset_views_layout = QtWidgets.QStackedLayout()
        subset_views_layout.addWidget(subset_view_cards)
        subset_views_layout.addWidget(subset_list_view)
        subset_views_layout.setCurrentWidget(subset_view_cards)

        # Buttons at the bottom of subset view
        create_btn = CreateInstanceBtn(self)
        delete_btn = RemoveInstanceBtn(self)
        change_view_btn = ChangeViewBtn(self)

        # --- Overview ---
        # Subset details widget
        subset_attributes_wrap = BorderedLabelWidget(
            "Publish options", self
        )
        subset_attributes_widget = SubsetAttributesWidget(
            controller, subset_attributes_wrap
        )
        subset_attributes_wrap.set_center_widget(subset_attributes_widget)

        # Layout of buttons at the bottom of subset view
        subset_view_btns_layout = QtWidgets.QHBoxLayout()
        subset_view_btns_layout.setContentsMargins(0, 5, 0, 0)
        subset_view_btns_layout.addWidget(create_btn)
        subset_view_btns_layout.addSpacing(5)
        subset_view_btns_layout.addWidget(delete_btn)
        subset_view_btns_layout.addStretch(1)
        subset_view_btns_layout.addWidget(change_view_btn)

        # Layout of view and buttons
        # - widget 'subset_view_widget' is necessary
        # - only layout won't be resized automatically to minimum size hint
        #   on child resize request!
        subset_view_widget = QtWidgets.QWidget(subset_views_widget)
        subset_view_layout = QtWidgets.QVBoxLayout(subset_view_widget)
        subset_view_layout.setContentsMargins(0, 0, 0, 0)
        subset_view_layout.addLayout(subset_views_layout, 1)
        subset_view_layout.addLayout(subset_view_btns_layout, 0)

        subset_views_widget.set_center_widget(subset_view_widget)

        # Whole subset layout with attributes and details
        subset_content_widget = QtWidgets.QWidget(self)
        subset_content_layout = QtWidgets.QHBoxLayout(subset_content_widget)
        subset_content_layout.setContentsMargins(0, 0, 0, 0)
        subset_content_layout.addWidget(create_widget, 7)
        subset_content_layout.addWidget(subset_views_widget, 3)
        subset_content_layout.addWidget(subset_attributes_wrap, 7)

        # Subset frame layout
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(subset_content_widget, 1)

        change_anim = QtCore.QVariantAnimation()
        change_anim.setStartValue(0)
        change_anim.setEndValue(self.anim_end_value)
        change_anim.setDuration(self.anim_duration)
        change_anim.setEasingCurve(QtCore.QEasingCurve.InOutQuad)

        # --- Calbacks for instances/subsets view ---
        create_btn.clicked.connect(self._on_create_clicked)
        delete_btn.clicked.connect(self._on_delete_clicked)
        change_view_btn.clicked.connect(self._on_change_view_clicked)

        change_anim.valueChanged.connect(self._on_change_anim)
        change_anim.finished.connect(self._on_change_anim_finished)

        # Selection changed
        subset_list_view.selection_changed.connect(
            self._on_subset_change
        )
        subset_view_cards.selection_changed.connect(
            self._on_subset_change
        )
        # Active instances changed
        subset_list_view.active_changed.connect(
            self._on_active_changed
        )
        subset_view_cards.active_changed.connect(
            self._on_active_changed
        )
        # Instance context has changed
        subset_attributes_widget.instance_context_changed.connect(
            self._on_instance_context_change
        )

        # --- Controller callbacks ---
        controller.event_system.add_callback(
            "publish.process.started", self._on_publish_start
        )
        controller.event_system.add_callback(
            "publish.reset.finished", self._on_publish_reset
        )
        controller.event_system.add_callback(
            "instances.refresh.finished", self._on_instances_refresh
        )

        self._subset_content_widget = subset_content_widget
        self._subset_content_layout = subset_content_layout

        self._subset_view_cards = subset_view_cards
        self._subset_list_view = subset_list_view
        self._subset_views_layout = subset_views_layout

        self._delete_btn = delete_btn

        self._subset_attributes_widget = subset_attributes_widget
        self._create_widget = create_widget
        self._subset_views_widget = subset_views_widget
        self._subset_attributes_wrap = subset_attributes_wrap

        self._change_anim = change_anim

        # Start in create mode
        self._create_widget_policy = create_widget.sizePolicy()
        self._subset_views_widget_policy = subset_views_widget.sizePolicy()
        self._subset_attributes_wrap_policy = (
            subset_attributes_wrap.sizePolicy()
        )
        self._max_widget_width = None
        self._current_state = "create"
        subset_attributes_wrap.setVisible(False)

    def set_state(self, new_state, animate):
        if new_state == self._current_state:
            return

        self._current_state = new_state

        anim_is_running = (
            self._change_anim.state() == self._change_anim.Running
        )
        if not animate:
            self._change_visibility_for_state()
            if anim_is_running:
                self._change_anim.stop()
            return

        if self._max_widget_width is None:
            self._max_widget_width = self._subset_views_widget.maximumWidth()

        if new_state == "create":
            direction = self._change_anim.Backward
        else:
            direction = self._change_anim.Forward
        self._change_anim.setDirection(direction)

        if not anim_is_running:
            view_width = self._subset_views_widget.width()
            self._subset_views_widget.setMinimumWidth(view_width)
            self._subset_views_widget.setMaximumWidth(view_width)
            self._change_anim.start()

    def _on_create_clicked(self):
        """Pass signal to parent widget which should care about changing state.

        We don't change anything here until the parent will care about it.
        """

        self.create_requested.emit()

    def _on_delete_clicked(self):
        instances, _ = self.get_selected_items()

        # Ask user if he really wants to remove instances
        dialog = QtWidgets.QMessageBox(self)
        dialog.setIcon(QtWidgets.QMessageBox.Question)
        dialog.setWindowTitle("Are you sure?")
        if len(instances) > 1:
            msg = (
                "Do you really want to remove {} instances?"
            ).format(len(instances))
        else:
            msg = (
                "Do you really want to remove the instance?"
            )
        dialog.setText(msg)
        dialog.setStandardButtons(
            QtWidgets.QMessageBox.Ok | QtWidgets.QMessageBox.Cancel
        )
        dialog.setDefaultButton(QtWidgets.QMessageBox.Ok)
        dialog.setEscapeButton(QtWidgets.QMessageBox.Cancel)
        dialog.exec_()
        # Skip if OK was not clicked
        if dialog.result() == QtWidgets.QMessageBox.Ok:
            instance_ids = {
                instance.id
                for instance in instances
            }
            self._controller.remove_instances(instance_ids)

    def _on_change_view_clicked(self):
        self._change_view_type()

    def _on_subset_change(self, *_args):
        # Ignore changes if in middle of refreshing
        if self._refreshing_instances:
            return

        instances, context_selected = self.get_selected_items()

        # Disable delete button if nothing is selected
        self._delete_btn.setEnabled(len(instances) > 0)

        self._subset_attributes_widget.set_current_instances(
            instances, context_selected
        )

    def _on_active_changed(self):
        if self._refreshing_instances:
            return
        self.active_changed.emit()

    def _on_change_anim(self, value):
        self._create_widget.setVisible(True)
        self._subset_attributes_wrap.setVisible(True)
        width = (
            self._subset_content_widget.width()
            - (
                self._subset_views_widget.width()
                + (self._subset_content_layout.spacing() * 2)
            )
        )
        subset_attrs_width = int(float(width) / self.anim_end_value) * value
        if subset_attrs_width > width:
            subset_attrs_width = width
        create_width = width - subset_attrs_width

        self._create_widget.setMinimumWidth(create_width)
        self._create_widget.setMaximumWidth(create_width)
        self._subset_attributes_wrap.setMinimumWidth(subset_attrs_width)
        self._subset_attributes_wrap.setMaximumWidth(subset_attrs_width)

    def _on_change_anim_finished(self):
        self._change_visibility_for_state()
        self._create_widget.setMinimumWidth(0)
        self._create_widget.setMaximumWidth(self._max_widget_width)
        self._subset_attributes_wrap.setMinimumWidth(0)
        self._subset_attributes_wrap.setMaximumWidth(self._max_widget_width)
        self._subset_views_widget.setMinimumWidth(0)
        self._subset_views_widget.setMaximumWidth(self._max_widget_width)
        self._create_widget.setSizePolicy(
            self._create_widget_policy
        )
        self._subset_attributes_wrap.setSizePolicy(
            self._subset_attributes_wrap_policy
        )
        self._subset_views_widget.setSizePolicy(
            self._subset_views_widget_policy
        )

    def _change_visibility_for_state(self):
        self._create_widget.setVisible(
            self._current_state == "create"
        )
        self._subset_attributes_wrap.setVisible(
            self._current_state == "publish"
        )

    def _on_instance_context_change(self):
        current_idx = self._subset_views_layout.currentIndex()
        for idx in range(self._subset_views_layout.count()):
            if idx == current_idx:
                continue
            widget = self._subset_views_layout.widget(idx)
            if widget.refreshed:
                widget.set_refreshed(False)

        current_widget = self._subset_views_layout.widget(current_idx)
        current_widget.refresh_instance_states()

        self.instance_context_changed.emit()

    def get_selected_items(self):
        view = self._subset_views_layout.currentWidget()
        return view.get_selected_items()

    def _change_view_type(self):
        idx = self._subset_views_layout.currentIndex()
        new_idx = (idx + 1) % self._subset_views_layout.count()
        self._subset_views_layout.setCurrentIndex(new_idx)

        new_view = self._subset_views_layout.currentWidget()
        if not new_view.refreshed:
            new_view.refresh()
            new_view.set_refreshed(True)
        else:
            new_view.refresh_instance_states()

        self._on_subset_change()

    def _refresh_instances(self):
        if self._refreshing_instances:
            return

        self._refreshing_instances = True

        for idx in range(self._subset_views_layout.count()):
            widget = self._subset_views_layout.widget(idx)
            widget.set_refreshed(False)

        view = self._subset_views_layout.currentWidget()
        view.refresh()
        view.set_refreshed(True)

        self._refreshing_instances = False

        # Force to change instance and refresh details
        self._on_subset_change()

    def _on_publish_start(self):
        """Publish started."""

        self._subset_attributes_wrap.setEnabled(False)

    def _on_publish_reset(self):
        """Context in controller has been refreshed."""

        self._subset_attributes_wrap.setEnabled(True)
        self._subset_content_widget.setEnabled(self._controller.host_is_valid)

    def _on_instances_refresh(self):
        """Controller refreshed instances."""

        self._refresh_instances()

        # Give a change to process Resize Request
        QtWidgets.QApplication.processEvents()
        # Trigger update geometry of
        widget = self._subset_views_layout.currentWidget()
        widget.updateGeometry()
