from Qt import QtWidgets, QtCore, QtGui

from openpype import (
    resources,
    style
)

from .control import PublisherController
from .widgets import (
    PublishFrame,
    SubsetAttributesWidget,
    InstanceCardView,
    InstanceListView,
    CreateDialog,
    IconBtn,
    get_icon
)


class PublisherWindow(QtWidgets.QDialog):
    default_width = 1000
    default_height = 600

    def __init__(self, parent=None):
        super(PublisherWindow, self).__init__(parent)

        self.setWindowTitle("OpenPype publisher")

        icon = QtGui.QIcon(resources.pype_icon_filepath())
        self.setWindowIcon(icon)

        if parent is None:
            on_top_flag = QtCore.Qt.WindowStaysOnTopHint
        else:
            on_top_flag = QtCore.Qt.Dialog

        self.setWindowFlags(
            self.windowFlags()
            | QtCore.Qt.WindowTitleHint
            | QtCore.Qt.WindowMaximizeButtonHint
            | QtCore.Qt.WindowMinimizeButtonHint
            | QtCore.Qt.WindowCloseButtonHint
            | on_top_flag
        )

        self._first_show = True
        self._refreshing_instances = False

        controller = PublisherController()

        # Header
        header_widget = QtWidgets.QWidget(self)
        context_label = QtWidgets.QLabel(header_widget)
        context_label.setObjectName("PublishContextLabel")

        header_layout = QtWidgets.QHBoxLayout(header_widget)
        header_layout.addWidget(context_label, 1)

        line_widget = QtWidgets.QWidget(self)
        line_widget.setObjectName("Separator")
        line_widget.setMinimumHeight(2)

        # Content
        # Subset widget
        subset_frame = QtWidgets.QWidget(self)

        subset_view_cards = InstanceCardView(controller, subset_frame)
        subset_list_view = InstanceListView(controller, subset_frame)

        subset_views_layout = QtWidgets.QStackedLayout()
        subset_views_layout.addWidget(subset_view_cards)
        subset_views_layout.addWidget(subset_list_view)

        # Buttons at the bottom of subset view
        create_btn = QtWidgets.QPushButton("+", subset_frame)
        delete_btn = QtWidgets.QPushButton("-", subset_frame)
        change_view_btn = QtWidgets.QPushButton("=", subset_frame)

        # Subset details widget
        subset_attributes_widget = SubsetAttributesWidget(
            controller, subset_frame
        )

        # Layout of buttons at the bottom of subset view
        subset_view_btns_layout = QtWidgets.QHBoxLayout()
        subset_view_btns_layout.setContentsMargins(0, 0, 0, 0)
        subset_view_btns_layout.setSpacing(5)
        subset_view_btns_layout.addWidget(create_btn)
        subset_view_btns_layout.addWidget(delete_btn)
        subset_view_btns_layout.addStretch(1)
        subset_view_btns_layout.addWidget(change_view_btn)

        # Layout of view and buttons
        subset_view_layout = QtWidgets.QVBoxLayout()
        subset_view_layout.setContentsMargins(0, 0, 0, 0)
        subset_view_layout.addLayout(subset_views_layout, 1)
        subset_view_layout.addLayout(subset_view_btns_layout, 0)

        # Whole subset layout with attributes and details
        subset_content_widget = QtWidgets.QWidget(subset_frame)
        subset_content_layout = QtWidgets.QHBoxLayout(subset_content_widget)
        subset_content_layout.setContentsMargins(0, 0, 0, 0)
        subset_content_layout.addLayout(subset_view_layout, 0)
        subset_content_layout.addWidget(subset_attributes_widget, 1)

        # Footer
        message_input = QtWidgets.QLineEdit(subset_frame)

        reset_btn = IconBtn(subset_frame)
        reset_btn.setIcon(get_icon("refresh"))
        reset_btn.setToolTip("Refresh publishing")

        stop_btn = IconBtn(subset_frame)
        stop_btn.setIcon(get_icon("stop"))
        stop_btn.setToolTip("Stop/Pause publishing")

        validate_btn = IconBtn(subset_frame)
        validate_btn.setIcon(get_icon("validate"))
        validate_btn.setToolTip("Validate")

        publish_btn = IconBtn(subset_frame)
        publish_btn.setIcon(get_icon("play"))
        publish_btn.setToolTip("Publish")

        footer_layout = QtWidgets.QHBoxLayout()
        footer_layout.addWidget(message_input, 1)
        footer_layout.addWidget(reset_btn, 0)
        footer_layout.addWidget(stop_btn, 0)
        footer_layout.addWidget(validate_btn, 0)
        footer_layout.addWidget(publish_btn, 0)

        # Subset frame layout
        subset_layout = QtWidgets.QVBoxLayout(subset_frame)
        marings = subset_layout.contentsMargins()
        marings.setLeft(marings.left() * 2)
        marings.setRight(marings.right() * 2)
        marings.setTop(marings.top() * 2)
        marings.setBottom(marings.bottom() * 2)
        subset_layout.setContentsMargins(marings)
        subset_layout.addWidget(subset_content_widget, 1)
        subset_layout.addLayout(footer_layout, 0)

        # Create publish frame
        publish_frame = PublishFrame(controller, self)

        content_stacked_layout = QtWidgets.QStackedLayout()
        content_stacked_layout.setStackingMode(
            QtWidgets.QStackedLayout.StackAll
        )
        content_stacked_layout.addWidget(subset_frame)
        content_stacked_layout.addWidget(publish_frame)

        # Add main frame to this window
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        main_layout.addWidget(header_widget, 0)
        main_layout.addWidget(line_widget, 0)
        main_layout.addLayout(content_stacked_layout, 1)

        creator_window = CreateDialog(controller, parent=self)

        create_btn.clicked.connect(self._on_create_clicked)
        delete_btn.clicked.connect(self._on_delete_clicked)
        change_view_btn.clicked.connect(self._on_change_view_clicked)

        reset_btn.clicked.connect(self._on_reset_clicked)
        stop_btn.clicked.connect(self._on_stop_clicked)
        validate_btn.clicked.connect(self._on_validate_clicked)
        publish_btn.clicked.connect(self._on_publish_clicked)

        subset_list_view.selection_changed.connect(
            self._on_subset_change
        )
        subset_view_cards.selection_changed.connect(
            self._on_subset_change
        )
        subset_attributes_widget.instance_context_changed.connect(
            self._on_instance_context_change
        )

        controller.add_instances_refresh_callback(self._on_instances_refresh)

        controller.add_publish_reset_callback(self._on_publish_reset)
        controller.add_publish_started_callback(self._on_publish_start)
        controller.add_publish_validated_callback(self._on_publish_validated)
        controller.add_publish_stopped_callback(self._on_publish_stop)

        self.content_stacked_layout = content_stacked_layout
        self.publish_frame = publish_frame
        self.subset_frame = subset_frame
        self.subset_content_widget = subset_content_widget

        self.context_label = context_label

        self.subset_view_cards = subset_view_cards
        self.subset_list_view = subset_list_view
        self.subset_views_layout = subset_views_layout

        self.delete_btn = delete_btn

        self.subset_attributes_widget = subset_attributes_widget
        self.message_input = message_input

        self.stop_btn = stop_btn
        self.reset_btn = reset_btn
        self.validate_btn = validate_btn
        self.publish_btn = publish_btn

        self.controller = controller

        self.creator_window = creator_window

        self.setStyleSheet(style.load_stylesheet())

        self.resize(self.default_width, self.default_height)

        # DEBUGING
        self.set_context_label(
            "<project>/<hierarchy>/<asset>/<task>/<workfile>"
        )

    def showEvent(self, event):
        super(PublisherWindow, self).showEvent(event)
        if self._first_show:
            self._first_show = False
            self.reset()

    def closeEvent(self, event):
        self.controller.save_changes()
        super(PublisherWindow, self).closeEvent(event)

    def reset(self):
        self.controller.reset()

    def set_context_label(self, label):
        self.context_label.setText(label)

    def get_selected_items(self):
        view = self.subset_views_layout.currentWidget()
        return view.get_selected_items()

    def _on_instance_context_change(self):
        current_idx = self.subset_views_layout.currentIndex()
        for idx in range(self.subset_views_layout.count()):
            if idx == current_idx:
                continue
            widget = self.subset_views_layout.widget(idx)
            if widget.refreshed:
                widget.set_refreshed(False)

        current_widget = self.subset_views_layout.widget(current_idx)
        current_widget.refresh_instance_states()

    def _change_view_type(self):
        old_view = self.subset_views_layout.currentWidget()

        idx = self.subset_views_layout.currentIndex()
        new_idx = (idx + 1) % self.subset_views_layout.count()
        self.subset_views_layout.setCurrentIndex(new_idx)

        new_view = self.subset_views_layout.currentWidget()
        if not new_view.refreshed:
            new_view.refresh()
            new_view.set_refreshed(True)
        else:
            new_view.refresh_instance_states()

        if new_view is not old_view:
            selected_instances, context_selected = (
                old_view.get_selected_items()
            )
            new_view.set_selected_items(
                selected_instances, context_selected
            )

    def _on_create_clicked(self):
        self.creator_window.show()

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
            self.controller.remove_instances(instances)

    def _on_change_view_clicked(self):
        self._change_view_type()

    def _set_publish_visibility(self, visible):
        if visible:
            widget = self.publish_frame
        else:
            widget = self.subset_frame
        self.content_stacked_layout.setCurrentWidget(widget)

    def _on_reset_clicked(self):
        self.controller.reset()

    def _on_stop_clicked(self):
        self.controller.stop_publish()

    def _on_validate_clicked(self):
        self._set_publish_visibility(True)
        self.controller.validate()

    def _on_publish_clicked(self):
        self._set_publish_visibility(True)
        self.controller.publish()

    def _refresh_instances(self):
        if self._refreshing_instances:
            return

        self._refreshing_instances = True

        for idx in range(self.subset_views_layout.count()):
            widget = self.subset_views_layout.widget(idx)
            widget.set_refreshed(False)

        view = self.subset_views_layout.currentWidget()
        view.refresh()
        view.set_refreshed(True)

        self._refreshing_instances = False

        # Force to change instance and refresh details
        self._on_subset_change()

    def _on_instances_refresh(self):
        self._refresh_instances()

    def _on_subset_change(self, *_args):
        # Ignore changes if in middle of refreshing
        if self._refreshing_instances:
            return

        instances, context_selected = self.get_selected_items()

        # Disable delete button if nothing is selected
        self.delete_btn.setEnabled(len(instances) >= 0)

        self.subset_attributes_widget.set_current_instances(
            instances, context_selected
        )

    def _on_publish_reset(self):
        self.reset_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.validate_btn.setEnabled(True)
        self.publish_btn.setEnabled(True)

        self._set_publish_visibility(False)

        self.subset_content_widget.setEnabled(self.controller.host_is_valid)

    def _on_publish_start(self):
        self.reset_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.validate_btn.setEnabled(False)
        self.publish_btn.setEnabled(False)

    def _on_publish_validated(self):
        self.validate_btn.setEnabled(False)

    def _on_publish_stop(self):
        self.reset_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        validate_enabled = not self.controller.publish_has_crashed
        publish_enabled = not self.controller.publish_has_crashed
        if validate_enabled:
            validate_enabled = not self.controller.publish_has_validated
        if publish_enabled:
            if (
                self.controller.publish_has_validated
                and self.controller.publish_has_validation_errors
            ):
                publish_enabled = False

            else:
                publish_enabled = not self.controller.publish_has_finished

        self.validate_btn.setEnabled(validate_enabled)
        self.publish_btn.setEnabled(publish_enabled)
