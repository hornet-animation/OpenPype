from Qt import QtWidgets, QtCore, QtGui

from openpype.style import get_colors_data


class _VLineWidget(QtWidgets.QWidget):
    def __init__(self, color, left, parent):
        super(_VLineWidget, self).__init__(parent)
        self._color = color
        self._left = left

    def paintEvent(self, event):
        if not self.isVisible():
            return

        if self._left:
            pos_x = 0
        else:
            pos_x = self.width()
        painter = QtGui.QPainter(self)
        painter.setRenderHints(
            painter.Antialiasing
            | painter.SmoothPixmapTransform
        )
        if self._color:
            pen = QtGui.QPen(self._color)
        else:
            pen = painter.pen()
        pen.setWidth(1)
        painter.setPen(pen)
        painter.setBrush(QtCore.Qt.transparent)
        painter.drawLine(pos_x, 0, pos_x, self.height())
        painter.end()


class _HLineWidget(QtWidgets.QWidget):
    def __init__(self, color, parent):
        super(_HLineWidget, self).__init__(parent)
        self._color = color
        self._radius = 0

    def set_radius(self, radius):
        self._radius = radius

    def paintEvent(self, event):
        if not self.isVisible():
            return

        rect = QtCore.QRect(
            0, -self._radius, self.width(), self.height() + self._radius
        )
        painter = QtGui.QPainter(self)
        painter.setRenderHints(
            painter.Antialiasing
            | painter.SmoothPixmapTransform
        )
        if self._color:
            pen = QtGui.QPen(self._color)
        else:
            pen = painter.pen()
        pen.setWidth(1)
        painter.setPen(pen)
        painter.setBrush(QtCore.Qt.transparent)
        painter.drawRoundedRect(rect, self._radius, self._radius)
        painter.end()


class _HCornerLineWidget(QtWidgets.QWidget):
    def __init__(self, color, left_side, parent):
        super(_HCornerLineWidget, self).__init__(parent)
        self._left_side = left_side
        self._color = color
        self._radius = 0

    def set_radius(self, radius):
        self._radius = radius

    def paintEvent(self, event):
        if not self.isVisible():
            return

        pos_y = self.height() / 2

        if self._left_side:
            rect = QtCore.QRect(
                0, pos_y, self.width() + self._radius, self.height()
            )
        else:
            rect = QtCore.QRect(
                -self._radius,
                pos_y,
                self.width() + self._radius,
                self.height()
            )

        painter = QtGui.QPainter(self)
        painter.setRenderHints(
            painter.Antialiasing
            | painter.SmoothPixmapTransform
        )
        if self._color:
            pen = QtGui.QPen(self._color)
        else:
            pen = painter.pen()
        pen.setWidth(1)
        painter.setPen(pen)
        painter.setBrush(QtCore.Qt.transparent)
        painter.drawRoundedRect(rect, self._radius, self._radius)
        painter.end()


class BorderedLabelWidget(QtWidgets.QFrame):
    """Draws borders around widget with label in the middle of top.

    +------- Label --------+
    |                      |
    |                      |
    |       CONTENT        |
    |                      |
    |                      |
    +----------------------+
    """
    def __init__(self, label, parent):
        super(BorderedLabelWidget, self).__init__(parent)
        colors_data = get_colors_data()
        color_value = colors_data.get("border")
        try:
            color = QtGui.QColor(color_value)
        except Exception:
            color = None

        top_left_w = _HCornerLineWidget(color, True, self)
        top_right_w = _HCornerLineWidget(color, False, self)

        label_widget = QtWidgets.QLabel(label, self)

        top_layout = QtWidgets.QHBoxLayout()
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(5)
        top_layout.addWidget(top_left_w, 1)
        top_layout.addWidget(label_widget, 0)
        top_layout.addWidget(top_right_w, 1)

        left_w = _VLineWidget(color, True, self)
        right_w = _VLineWidget(color, False, self)

        bottom_w = _HLineWidget(color, self)

        center_layout = QtWidgets.QHBoxLayout()
        center_layout.setContentsMargins(5, 5, 5, 5)

        layout = QtWidgets.QGridLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        layout.addLayout(top_layout, 0, 0, 1, 3)

        layout.addWidget(left_w, 1, 0)
        layout.addLayout(center_layout, 1, 1)
        layout.addWidget(right_w, 1, 2)

        layout.addWidget(bottom_w, 2, 0, 1, 3)

        layout.setColumnStretch(1, 1)
        layout.setRowStretch(1, 1)

        self._widget = None

        self._radius = 0

        self._top_left_w = top_left_w
        self._top_right_w = top_right_w
        self._left_w = left_w
        self._right_w = right_w
        self._bottom_w = bottom_w
        self._label_widget = label_widget
        self._center_layout = center_layout

    def set_content_margins(self, value):
        self._center_layout.setContentsMargins(
            value, value, value, value
        )

    def showEvent(self, event):
        super(BorderedLabelWidget, self).showEvent(event)

        height = self._label_widget.height()
        radius = (height + (height % 2)) / 2
        self._radius = radius

        side_width = 1 + radius
        # Dont't use fixed width/height as that would set also set
        #   the other size (When fixed width is set then is also set
        #   fixed height).
        self._left_w.setMinimumWidth(side_width)
        self._left_w.setMaximumWidth(side_width)
        self._right_w.setMinimumWidth(side_width)
        self._right_w.setMaximumWidth(side_width)
        self._bottom_w.setMinimumHeight(radius)
        self._bottom_w.setMaximumHeight(radius)
        self._bottom_w.set_radius(radius)
        self._top_right_w.set_radius(radius)
        self._top_left_w.set_radius(radius)
        if self._widget:
            self._widget.update()

    def set_center_widget(self, widget):
        while self._center_layout.count():
            item = self._center_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        self._widget = widget
        if isinstance(widget, QtWidgets.QLayout):
            self._center_layout.addLayout(widget)
        else:
            self._center_layout.addWidget(widget)
