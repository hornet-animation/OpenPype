import os
import json
import time

from Qt import QtWidgets, QtCore

from openpype.pipeline import KnownPublishError

from .widgets import (
    StopBtn,
    ResetBtn,
    ValidateBtn,
    PublishBtn,
    PublishReportBtn,
)


class PublishFrame(QtWidgets.QWidget):
    """Frame showed during publishing.

    Shows all information related to publishing. Contains validation error
    widget which is showed if only validation error happens during validation.

    Processing layer is default layer. Validation error layer is shown if only
    validation exception is raised during publishing. Report layer is available
    only when publishing process is stopped and must be manually triggered to
    change into that layer.

    +------------------------------------------------------------------------+
    |                             < Main label >                             |
    |                             < Label top >                              |
    |        (####                      10%  <Progress bar>                ) |
    | <Instance label>                                        <Plugin label> |
    | <Report><Label bottom>                <Reset><Stop><Validate><Publish> |
    +------------------------------------------------------------------------+
    """

    details_page_requested = QtCore.Signal()

    def __init__(self, controller, parent):
        super(PublishFrame, self).__init__(parent)

        # Bottom part of widget where process and callback buttons are showed
        # - QFrame used to be able set background using stylesheets easily
        #   and not override all children widgets style
        content_frame = QtWidgets.QFrame(self)
        content_frame.setObjectName("PublishInfoFrame")

        top_content_widget = QtWidgets.QWidget(content_frame)

        # Center widget displaying current state (without any specific info)
        main_label = QtWidgets.QLabel(top_content_widget)
        main_label.setObjectName("PublishInfoMainLabel")
        main_label.setAlignment(QtCore.Qt.AlignCenter)

        # Supporting labels for main label
        # Top label is displayed just under main label
        message_label_top = QtWidgets.QLabel(top_content_widget)
        message_label_top.setAlignment(QtCore.Qt.AlignCenter)

        # Bottom label is displayed between report and publish buttons
        #   at bottom part of info frame
        message_label_bottom = QtWidgets.QLabel(top_content_widget)
        message_label_bottom.setAlignment(QtCore.Qt.AlignCenter)

        # Label showing currently processed instance
        instance_label = QtWidgets.QLabel("<Instance name>", top_content_widget)
        instance_label.setAlignment(
            QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter
        )
        # Label showing currently processed plugin
        plugin_label = QtWidgets.QLabel("<Plugin name>", top_content_widget)
        plugin_label.setAlignment(
            QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter
        )
        instance_plugin_layout = QtWidgets.QHBoxLayout()
        instance_plugin_layout.addWidget(instance_label, 1)
        instance_plugin_layout.addWidget(plugin_label, 1)

        # Progress bar showing progress of publishing
        progress_widget = QtWidgets.QProgressBar(top_content_widget)
        progress_widget.setObjectName("PublishProgressBar")

        top_content_layout = QtWidgets.QVBoxLayout(top_content_widget)
        top_content_layout.setContentsMargins(0, 0, 0, 0)
        top_content_layout.setSpacing(5)
        top_content_layout.setAlignment(QtCore.Qt.AlignCenter)
        top_content_layout.addWidget(main_label)
        # TODO stretches should be probably replaced by spacing...
        # - stretch in floating frame doesn't make sense
        top_content_layout.addWidget(message_label_top)
        top_content_layout.addLayout(instance_plugin_layout)
        top_content_layout.addWidget(progress_widget)

        # Publishing buttons to stop, reset or trigger publishing
        footer_widget = QtWidgets.QWidget(content_frame)

        report_btn = PublishReportBtn(footer_widget)

        shrunk_main_label = QtWidgets.QLabel(footer_widget)
        shrunk_main_label.setObjectName("PublishInfoMainLabel")
        shrunk_main_label.setAlignment(
            QtCore.Qt.AlignVCenter | QtCore.Qt.AlignLeft
        )

        reset_btn = ResetBtn(footer_widget)
        stop_btn = StopBtn(footer_widget)
        validate_btn = ValidateBtn(footer_widget)
        publish_btn = PublishBtn(footer_widget)

        report_btn.add_action("Go to details", "go_to_report")
        report_btn.add_action("Copy report", "copy_report")
        report_btn.add_action("Export report", "export_report")

        # Footer on info frame layout
        footer_layout = QtWidgets.QHBoxLayout(footer_widget)
        footer_layout.setContentsMargins(0, 0, 0, 0)
        footer_layout.addWidget(report_btn, 0)
        footer_layout.addWidget(shrunk_main_label, 1)
        footer_layout.addWidget(message_label_bottom, 1)
        footer_layout.addWidget(reset_btn, 0)
        footer_layout.addWidget(stop_btn, 0)
        footer_layout.addWidget(validate_btn, 0)
        footer_layout.addWidget(publish_btn, 0)

        # Info frame content
        content_layout = QtWidgets.QVBoxLayout(content_frame)
        content_layout.setSpacing(5)

        content_layout.addWidget(top_content_widget)
        content_layout.addWidget(footer_widget)

        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(content_frame)

        shrunk_anim = QtCore.QVariantAnimation()
        shrunk_anim.setDuration(140)
        shrunk_anim.setEasingCurve(QtCore.QEasingCurve.InOutQuad)

        # Force translucent background for widgets
        for widget in (
            self,
            top_content_widget,
            footer_widget,
        ):
            widget.setAttribute(QtCore.Qt.WA_TranslucentBackground)

        report_btn.triggered.connect(self._on_report_triggered)
        reset_btn.clicked.connect(self._on_reset_clicked)
        stop_btn.clicked.connect(self._on_stop_clicked)
        validate_btn.clicked.connect(self._on_validate_clicked)
        publish_btn.clicked.connect(self._on_publish_clicked)

        shrunk_anim.valueChanged.connect(self._on_shrunk_anim)
        shrunk_anim.finished.connect(self._on_shrunk_anim_finish)

        controller.add_publish_reset_callback(self._on_publish_reset)
        controller.add_publish_started_callback(self._on_publish_start)
        controller.add_publish_validated_callback(self._on_publish_validated)
        controller.add_publish_stopped_callback(self._on_publish_stop)

        controller.add_instance_change_callback(self._on_instance_change)
        controller.add_plugin_change_callback(self._on_plugin_change)

        self._shrunk_anim = shrunk_anim

        self.controller = controller

        self._content_frame = content_frame
        self._content_layout = content_layout
        self._top_content_widget = top_content_widget

        self._main_label = main_label
        self._message_label_top = message_label_top

        self._instance_label = instance_label
        self._plugin_label = plugin_label

        self._progress_widget = progress_widget

        self._shrunk_main_label = shrunk_main_label
        self._message_label_bottom = message_label_bottom
        self._reset_btn = reset_btn
        self._stop_btn = stop_btn
        self._validate_btn = validate_btn
        self._publish_btn = publish_btn

        self._shrunken = False
        self._top_widget_max_height = None
        self._top_widget_size_policy = top_content_widget.sizePolicy()

        shrunk_main_label.setVisible(False)

    def mouseReleaseEvent(self, event):
        super(PublishFrame, self).mouseReleaseEvent(event)
        self._change_shrunk_state()

    def _change_shrunk_state(self):
        self.set_shrunk_state(not self._shrunken)

    def set_shrunk_state(self, shrunk):
        if shrunk is self._shrunken:
            return

        if self._top_widget_max_height is None:
            self._top_widget_max_height = (
                self._top_content_widget.maximumHeight()
            )

        self._shrunken = shrunk

        anim_is_running = (
            self._shrunk_anim.state() == self._shrunk_anim.Running
        )
        if not self.isVisible():
            if anim_is_running:
                self._shrunk_anim.stop()
            self._on_shrunk_anim_finish()
            return

        start = 0
        end = 0
        if shrunk:
            start = self._top_content_widget.height()
        else:
            if anim_is_running:
                start = self._shrunk_anim.currentValue()
            hint = self._top_content_widget.minimumSizeHint()
            end = hint.height()

        self._shrunk_anim.setStartValue(start)
        self._shrunk_anim.setEndValue(end)
        if not anim_is_running:
            self._shrunk_anim.start()

    def _on_shrunk_anim(self, value):
        diff = self._top_content_widget.height() - value
        if not self._top_content_widget.isVisible():
            diff -= self._content_layout.spacing()

        window_pos = self.pos()
        window_pos_y = self.pos().y() + diff
        window_height = self.height() - diff

        self._top_content_widget.setMinimumHeight(value)
        self._top_content_widget.setMaximumHeight(value)
        self._top_content_widget.setVisible(True)

        self.resize(self.width(), window_height)
        self.move(window_pos.x(), window_pos_y)

    def _on_shrunk_anim_finish(self):
        self._top_content_widget.setVisible(not self._shrunken)
        self._top_content_widget.setMinimumHeight(0)
        self._top_content_widget.setMaximumHeight(
            self._top_widget_max_height
        )
        self._top_content_widget.setSizePolicy(self._top_widget_size_policy)

        self._message_label_bottom.setVisible(not self._shrunken)
        self._shrunk_main_label.setVisible(self._shrunken)

        if self._shrunken:
            content_frame_hint = self._content_frame.sizeHint()
            window_height = content_frame_hint.height()

            diff = self.height() - window_height
            window_pos = self.pos()
            window_pos_y = self.pos().y() + diff
            self.resize(self.width(), window_height)
            self.move(window_pos.x(), window_pos_y)

    def _set_main_label(self, message):
        self._main_label.setText(message)
        self._shrunk_main_label.setText(message)

    def _on_publish_reset(self):
        self._set_success_property()
        self._set_progress_visibility(True)

        self._main_label.setText("Hit publish (play button)! If you want")
        self._message_label_top.setText("")
        self._message_label_bottom.setText("")

        self._reset_btn.setEnabled(True)
        self._stop_btn.setEnabled(False)
        self._validate_btn.setEnabled(True)
        self._publish_btn.setEnabled(True)

        self._progress_widget.setValue(self.controller.publish_progress)
        self._progress_widget.setMaximum(self.controller.publish_max_progress)

    def _on_publish_start(self):
        self._set_success_property(-1)
        self._set_progress_visibility(True)
        self._set_main_label("Publishing...")

        self._reset_btn.setEnabled(False)
        self._stop_btn.setEnabled(True)
        self._validate_btn.setEnabled(False)
        self._publish_btn.setEnabled(False)

    def _on_publish_validated(self):
        self._validate_btn.setEnabled(False)

    def _on_instance_change(self, context, instance):
        """Change instance label when instance is going to be processed."""
        if instance is None:
            new_name = (
                context.data.get("label")
                or context.data.get("name")
                or "Context"
            )
        else:
            new_name = (
                instance.data.get("label")
                or instance.data["name"]
            )

        self._instance_label.setText(new_name)
        QtWidgets.QApplication.processEvents()

    def _on_plugin_change(self, plugin):
        """Change plugin label when instance is going to be processed."""
        plugin_name = plugin.__name__
        if hasattr(plugin, "label") and plugin.label:
            plugin_name = plugin.label

        self._progress_widget.setValue(self.controller.publish_progress)
        self._plugin_label.setText(plugin_name)
        QtWidgets.QApplication.processEvents()

    def _on_publish_stop(self):
        self._progress_widget.setValue(self.controller.publish_progress)

        self._reset_btn.setEnabled(True)
        self._stop_btn.setEnabled(False)
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

        self._validate_btn.setEnabled(validate_enabled)
        self._publish_btn.setEnabled(publish_enabled)

        error = self.controller.get_publish_crash_error()
        validation_errors = self.controller.get_validation_errors()
        if error:
            self._set_error(error)

        elif validation_errors:
            self._set_progress_visibility(False)
            self._set_validation_errors()

        elif self.controller.publish_has_finished:
            self._set_finished()

        else:
            self._set_stopped()

    def _set_stopped(self):
        main_label = "Publish paused"
        if self.controller.publish_has_validated:
            main_label += " - Validation passed"

        self._set_main_label(main_label)
        self._message_label_top.setText(
            "Hit publish (play button) to continue."
        )

        self._set_success_property(-1)

    def _set_error(self, error):
        self._set_main_label("Error happened")
        if isinstance(error, KnownPublishError):
            msg = str(error)
        else:
            msg = (
                "Something went wrong. Send report"
                " to your supervisor or OpenPype."
            )
        self._message_label_top.setText(msg)
        self._message_label_bottom.setText("")
        self._set_success_property(0)

    def _set_validation_errors(self):
        self._set_main_label("Your publish didn't pass studio validations")
        self._message_label_top.setText("")
        self._message_label_bottom.setText("Check results above please")
        self._set_success_property(2)

    def _set_finished(self):
        self._set_main_label("Finished")
        self._message_label_top.setText("")
        self._message_label_bottom.setText("")
        self._set_success_property(1)

    def _set_progress_visibility(self, visible):
        self._instance_label.setVisible(visible)
        self._plugin_label.setVisible(visible)
        self._progress_widget.setVisible(visible)
        self._message_label_top.setVisible(visible)

    def _set_success_property(self, state=None):
        if state is None:
            state = ""
        else:
            state = str(state)

        for widget in (self._progress_widget, self._content_frame):
            if widget.property("state") != state:
                widget.setProperty("state", state)
                widget.style().polish(widget)

    def _copy_report(self):
        logs = self.controller.get_publish_report()
        logs_string = json.dumps(logs, indent=4)

        mime_data = QtCore.QMimeData()
        mime_data.setText(logs_string)
        QtWidgets.QApplication.instance().clipboard().setMimeData(
            mime_data
        )

    def _export_report(self):
        default_filename = "publish-report-{}".format(
            time.strftime("%y%m%d-%H-%M")
        )
        default_filepath = os.path.join(
            os.path.expanduser("~"),
            default_filename
        )
        new_filepath, ext = QtWidgets.QFileDialog.getSaveFileName(
            self, "Save report", default_filepath, ".json"
        )
        if not ext or not new_filepath:
            return

        logs = self.controller.get_publish_report()
        full_path = new_filepath + ext
        dir_path = os.path.dirname(full_path)
        if not os.path.exists(dir_path):
            os.makedirs(dir_path)

        with open(full_path, "w") as file_stream:
            json.dump(logs, file_stream)

    def _on_report_triggered(self, identifier):
        if identifier == "export_report":
            self._export_report()

        elif identifier == "copy_report":
            self._copy_report()

        elif identifier == "go_to_report":
            self.details_page_requested.emit()

    def _on_reset_clicked(self):
        self.controller.reset()

    def _on_stop_clicked(self):
        self.controller.stop_publish()

    def _on_validate_clicked(self):
        self.controller.validate()

    def _on_publish_clicked(self):
        self.controller.publish()
