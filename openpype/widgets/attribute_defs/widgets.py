from openpype.pipeline.lib import (
    AbtractAttrDef,
    NumberDef,
    TextDef,
    EnumDef,
    BoolDef
)
from Qt import QtWidgets, QtCore, QtGui


def create_widget_for_attr_def(attr_def, parent=None):
    if not isinstance(attr_def, AbtractAttrDef):
        raise TypeError("Unexpected type \"{}\" expected \"{}\"".format(
            str(type(attr_def)), AbtractAttrDef
        ))

    if isinstance(attr_def, NumberDef):
        return NumberAttrWidget(attr_def, parent)

    if isinstance(attr_def, TextDef):
        return TextAttrWidget(attr_def, parent)

    if isinstance(attr_def, EnumDef):
        return EnumAttrWidget(attr_def, parent)

    if isinstance(attr_def, BoolDef):
        return BoolAttrWidget(attr_def, parent)

    raise ValueError("Unknown attribute definition \"{}\"".format(
        str(type(attr_def))
    ))


class _BaseAttrDefWidget(QtWidgets.QWidget):
    value_changed = QtCore.Signal(object, object)

    def __init__(self, attr_def, parent):
        super(_BaseAttrDefWidget, self).__init__(parent)

        self.attr_def = attr_def

        main_layout = QtWidgets.QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        self.main_layout = main_layout

        self._ui_init()

    def _ui_init(self):
        raise NotImplementedError(
            "Method '_ui_init' is not implemented. {}".format(
                self.__class__.__name__
            )
        )

    def current_value(self):
        raise NotImplementedError(
            "Method 'current_value' is not implemented. {}".format(
                self.__class__.__name__
            )
        )


class NumberAttrWidget(_BaseAttrDefWidget):
    def _ui_init(self):
        decimals = self.attr_def.decimals
        if decimals > 0:
            input_widget = QtWidgets.QDoubleSpinBox(self)
            input_widget.setDecimals(decimals)
        else:
            input_widget = QtWidgets.QSpinBox(self)

        input_widget.setMinimum(self.attr_def.minimum)
        input_widget.setMaximum(self.attr_def.maximum)
        input_widget.setValue(self.attr_def.default)

        input_widget.setButtonSymbols(
            QtWidgets.QAbstractSpinBox.ButtonSymbols.NoButtons
        )

        self._last_value = input_widget.value()

        input_widget.valueChanged.connect(self._on_value_change)

        self._input_widget = input_widget

        self.main_layout.addWidget(input_widget, 0)

    def _on_value_change(self, new_value):
        old_value = self._last_value
        self._last_value = new_value
        self.value_changed.emit(old_value, new_value)

    def current_value(self):
        return self._input_widget.value()


class TextAttrWidget(_BaseAttrDefWidget):
    def _ui_init(self):
        # TODO Solve how to handle regex
        # self.attr_def.regex

        self.multiline = self.attr_def.multiline
        if self.multiline:
            input_widget = QtWidgets.QPlainTextEdit(self)
        else:
            input_widget = QtWidgets.QLineEdit(self)

        if (
            self.attr_def.placeholder
            and hasattr(input_widget, "setPlaceholderText")
        ):
            input_widget.setPlaceholderText(self.attr_def.placeholder)

        if self.attr_def.default:
            if self.multiline:
                input_widget.setPlainText(self.attr_def.default)
            else:
                input_widget.setText(self.attr_def.default)

        self._last_value = self.current_value()

        input_widget.textChanged.connect(self._on_value_change)

        self._input_widget = input_widget

        self.main_layout.addWidget(input_widget, 0)

    def _on_value_change(self):
        new_value = self._input_widget.toPlainText()
        old_value = self._last_value
        self._last_value = new_value
        self.value_changed.emit(old_value, new_value)

    def current_value(self):
        if self.multiline:
            return self._input_widget.toPlainText()
        return self._input_widget.text()


class BoolAttrWidget(_BaseAttrDefWidget):
    def _ui_init(self):
        input_widget = QtWidgets.QCheckBox(self)
        input_widget.setChecked(self.attr_def.default)

        input_widget.stateChanged.connect(self._on_value_change)

        self._last_value = input_widget.isChecked()
        self.input_widget = input_widget

        self.main_layout.addWidget(input_widget, 0)

    def _on_value_change(self):
        new_value = self.input_widget.isChecked()
        old_value = self._last_value
        self._last_value = new_value
        self.value_changed.emit(old_value, new_value)

    def current_value(self):
        return self._input_widget.isChecked()


class EnumAttrWidget(_BaseAttrDefWidget):
    def _ui_init(self):
        input_widget = QtWidgets.QComboBox(self)
        combo_delegate = QtWidgets.QStyledItemDelegate(input_widget)
        input_widget.setItemDelegate(combo_delegate)

        items = self.attr_def.items
        for key, label in items.items():
            input_widget.addItem(label, key)

        idx = input_widget.findData(self.attr_def.default)
        if idx >= 0:
            input_widget.setCurrentIndex(idx)

        input_widget.currentIndexChanged.connect(self._on_value_change)

        self._combo_delegate = combo_delegate
        self._input_widget = input_widget
        self._last_value = self.current_value()

        self.main_layout.addWidget(input_widget, 0)

    def _on_value_change(self):
        new_value = self.current_value()
        old_value = self._last_value
        self._last_value = new_value
        self.value_changed.emit(old_value, new_value)

    def current_value(self):
        idx = self._input_widget.currentIndex()
        return self._input_widget.itemData(idx)
