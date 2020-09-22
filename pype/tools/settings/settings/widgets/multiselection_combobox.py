from Qt import QtCore, QtGui, QtWidgets


class ComboItemDelegate(QtWidgets.QStyledItemDelegate):
    """
    Helper styled delegate (mostly based on existing private Qt's
    delegate used by the QtWidgets.QComboBox). Used to style the popup like a
    list view (e.g windows style).
    """

    def paint(self, painter, option, index):
        option = QtWidgets.QStyleOptionViewItem(option)
        option.showDecorationSelected = True

        # option.state &= (
        #     ~QtWidgets.QStyle.State_HasFocus
        #     & ~QtWidgets.QStyle.State_MouseOver
        # )
        super(ComboItemDelegate, self).paint(painter, option, index)


class ComboMenuDelegate(QtWidgets.QAbstractItemDelegate):
    """
    Helper styled delegate (mostly based on existing private Qt's
    delegate used by the QtWidgets.QComboBox). Used to style the popup like a
    menu. (e.g osx aqua style).
    """

    def paint(self, painter, option, index):
        menuopt = self._menu_style_option(option, index)
        if option.widget is not None:
            style = option.widget.style()
        else:
            style = QtWidgets.QApplication.style()
        style.drawControl(QtWidgets.QStyle.CE_MenuItem, menuopt, painter,
                          option.widget)

    def sizeHint(self, option, index):
        menuopt = self._menu_style_option(option, index)
        if option.widget is not None:
            style = option.widget.style()
        else:
            style = QtWidgets.QApplication.style()
        return style.sizeFromContents(
            QtWidgets.QStyle.CT_MenuItem, menuopt, menuopt.rect.size(),
            option.widget
        )

    def _menu_style_option(self, option, index):
        menuoption = QtWidgets.QStyleOptionMenuItem()
        if option.widget:
            palette_source = option.widget.palette("QMenu")
        else:
            palette_source = QtWidgets.QApplication.palette("QMenu")

        palette = option.palette.resolve(palette_source)
        foreground = index.data(QtCore.Qt.ForegroundRole)
        if isinstance(foreground, (QtGui.QBrush, QtGui.QColor, QtGui.QPixmap)):
            foreground = QtGui.QBrush(foreground)
            palette.setBrush(QtGui.QPalette.Text, foreground)
            palette.setBrush(QtGui.QPalette.ButtonText, foreground)
            palette.setBrush(QtGui.QPalette.WindowText, foreground)

        background = index.data(QtCore.Qt.BackgroundRole)
        if isinstance(background, (QtGui.QBrush, QtGui.QColor, QtGui.QPixmap)):
            background = QtGui.QBrush(background)
            palette.setBrush(QtGui.QPalette.Background, background)

        menuoption.palette = palette

        decoration = index.data(QtCore.Qt.DecorationRole)
        if isinstance(decoration, QtGui.QIcon):
            menuoption.icon = decoration

        menuoption.menuItemType = QtWidgets.QStyleOptionMenuItem.Normal

        if index.flags() & QtCore.Qt.ItemIsUserCheckable:
            menuoption.checkType = QtWidgets.QStyleOptionMenuItem.NonExclusive
        else:
            menuoption.checkType = QtWidgets.QStyleOptionMenuItem.NotCheckable

        check = index.data(QtCore.Qt.CheckStateRole)
        menuoption.checked = check == QtCore.Qt.Checked

        if option.widget is not None:
            menuoption.font = option.widget.font()
        else:
            menuoption.font = QtWidgets.QApplication.font("QMenu")

        menuoption.maxIconWidth = option.decorationSize.width() + 4
        menuoption.rect = option.rect
        menuoption.menuRect = option.rect

        # menuoption.menuHasCheckableItems = True
        menuoption.tabWidth = 0
        # TODO: self.displayText(QVariant, QLocale)
        # TODO: Why is this not a QtWidgets.QStyledItemDelegate?
        menuoption.text = str(index.data(QtCore.Qt.DisplayRole))

        menuoption.fontMetrics = QtGui.QFontMetrics(menuoption.font)
        state = option.state & (
            QtWidgets.QStyle.State_MouseOver
            | QtWidgets.QStyle.State_Selected
            | QtWidgets.QStyle.State_Active
        )

        if index.flags() & QtCore.Qt.ItemIsEnabled:
            state = state | QtWidgets.QStyle.State_Enabled
            menuoption.palette.setCurrentColorGroup(QtGui.QPalette.Active)
        else:
            state = state & ~QtWidgets.QStyle.State_Enabled
            menuoption.palette.setCurrentColorGroup(QtGui.QPalette.Disabled)

        if menuoption.checked:
            state = state | QtWidgets.QStyle.State_On
        else:
            state = state | QtWidgets.QStyle.State_Off

        menuoption.state = state
        return menuoption


class MultiSelectionComboBox(QtWidgets.QComboBox):
    value_changed = QtCore.Signal()
    ignored_keys = {
        QtCore.Qt.Key_Up,
        QtCore.Qt.Key_Down,
        QtCore.Qt.Key_PageDown,
        QtCore.Qt.Key_PageUp,
        QtCore.Qt.Key_Home,
        QtCore.Qt.Key_End
    }

    top_bottom_padding = 2
    left_right_padding = 3
    left_offset = 2
    top_bottom_margins = 2
    item_spacing = 5

    item_bg_color = QtGui.QColor("#555555")

    def __init__(
        self, parent=None, placeholder="", separator=", ", **kwargs
    ):
        super(MultiSelectionComboBox, self).__init__(parent=parent, **kwargs)
        self.setObjectName("MultiSelectionComboBox")
        self.setFocusPolicy(QtCore.Qt.StrongFocus)

        self._popup_is_shown = False
        # self.__supressPopupHide = False
        self._block_mouse_release_timer = QtCore.QTimer(self, singleShot=True)
        self._initial_mouse_pos = None
        self._separator = separator
        self.placeholder_text = placeholder
        self._update_item_delegate()

        self.lines = {}
        self.item_height = (
            self.fontMetrics().height()
            + (2 * self.top_bottom_padding)
            + (2 * self.top_bottom_margins)
        )

    def mousePressEvent(self, event):
        """Reimplemented."""
        self._popup_is_shown = False
        super(MultiSelectionComboBox, self).mousePressEvent(event)
        if self._popup_is_shown:
            self._initial_mouse_pos = self.mapToGlobal(event.pos())
            self._block_mouse_release_timer.start(
                QtWidgets.QApplication.doubleClickInterval()
            )

    def changeEvent(self, event):
        """Reimplemented."""
        if event.type() == QtCore.QEvent.StyleChange:
            self._update_item_delegate()
        super(MultiSelectionComboBox, self).changeEvent(event)

    def showPopup(self):
        """Reimplemented."""
        super(MultiSelectionComboBox, self).showPopup()
        view = self.view()
        view.installEventFilter(self)
        view.viewport().installEventFilter(self)
        self._popup_is_shown = True

    def hidePopup(self):
        """Reimplemented."""
        self.view().removeEventFilter(self)
        self.view().viewport().removeEventFilter(self)
        self._popup_is_shown = False
        self._initial_mouse_pos = None
        super(MultiSelectionComboBox, self).hidePopup()
        self.view().clearFocus()

    def eventFilter(self, obj, event):
        """Reimplemented."""
        if (
            self._popup_is_shown
            and event.type() == QtCore.QEvent.MouseMove
            and self.view().isVisible()
            and self._initial_mouse_pos is not None
        ):
            diff = obj.mapToGlobal(event.pos()) - self._initial_mouse_pos
            if (
                diff.manhattanLength() > 9
                and self._block_mouse_release_timer.isActive()
            ):
                self._block_mouse_release_timer.stop()

        current_index = self.view().currentIndex()
        if (
            self._popup_is_shown
            and event.type() == QtCore.QEvent.MouseButtonRelease
            and self.view().isVisible()
            and self.view().rect().contains(event.pos())
            and current_index.isValid()
            and current_index.flags() & QtCore.Qt.ItemIsSelectable
            and current_index.flags() & QtCore.Qt.ItemIsEnabled
            and current_index.flags() & QtCore.Qt.ItemIsUserCheckable
            and self.view().visualRect(current_index).contains(event.pos())
            and not self._block_mouse_release_timer.isActive()
        ):
            model = self.model()
            index = self.view().currentIndex()
            state = model.data(index, QtCore.Qt.CheckStateRole)
            if state == QtCore.Qt.Unchecked:
                check_state = QtCore.Qt.Checked
            else:
                check_state = QtCore.Qt.Unchecked

            model.setData(index, check_state, QtCore.Qt.CheckStateRole)
            self.view().update(index)
            self.update_size_hint()
            self.value_changed.emit()
            return True

        if self._popup_is_shown and event.type() == QtCore.QEvent.KeyPress:
            if event.key() == QtCore.Qt.Key_Space:
                # toogle the current items check state
                model = self.model()
                index = self.view().currentIndex()
                flags = model.flags(index)
                state = model.data(index, QtCore.Qt.CheckStateRole)
                if flags & QtCore.Qt.ItemIsUserCheckable and \
                        flags & QtCore.Qt.ItemIsTristate:
                    state = QtCore.Qt.CheckState((int(state) + 1) % 3)
                elif flags & QtCore.Qt.ItemIsUserCheckable:
                    state = (
                        QtCore.Qt.Checked
                        if state != QtCore.Qt.Checked
                        else QtCore.Qt.Unchecked
                    )
                model.setData(index, state, QtCore.Qt.CheckStateRole)
                self.view().update(index)
                self.update()
                return True
            # TODO: handle QtCore.Qt.Key_Enter, Key_Return?

        return super(MultiSelectionComboBox, self).eventFilter(obj, event)

    def paintEvent(self, event):
        """Reimplemented."""
        painter = QtWidgets.QStylePainter(self)
        option = QtWidgets.QStyleOptionComboBox()
        self.initStyleOption(option)
        painter.drawComplexControl(QtWidgets.QStyle.CC_ComboBox, option)

        # draw the icon and text
        items = self.checked_items_text()
        if not items:
            option.currentText = self.placeholder_text
            option.palette.setCurrentColorGroup(QtGui.QPalette.Disabled)
            painter.drawControl(QtWidgets.QStyle.CE_ComboBoxLabel, option)
            return

        font_metricts = self.fontMetrics()
        for line, items in self.lines.items():
            top_y = (
                option.rect.top()
                + (line * self.item_height)
                + self.top_bottom_margins
            )
            left_x = option.rect.left() + self.left_offset
            for item in items:
                label_rect = font_metricts.boundingRect(item)
                label_height = label_rect.height()

                label_rect.moveTop(top_y)
                label_rect.moveLeft(left_x)
                label_rect.setHeight(self.item_height)

                bg_rect = QtCore.QRectF(label_rect)
                bg_rect.setWidth(
                    label_rect.width()
                    + (2 * self.left_right_padding)
                )
                left_x = bg_rect.right() + self.item_spacing

                label_rect.moveLeft(label_rect.x() + self.left_right_padding)

                bg_rect.setHeight(label_height + (2 * self.top_bottom_padding))
                bg_rect.moveTop(bg_rect.top() + self.top_bottom_margins)

                path = QtGui.QPainterPath()
                path.addRoundedRect(bg_rect, 5, 5)

                painter.fillPath(path, self.item_bg_color)

                painter.drawText(
                    label_rect,
                    QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter,
                    item
                )

    def resizeEvent(self, *args, **kwargs):
        super(MultiSelectionComboBox, self).resizeEvent(*args, **kwargs)
        self.update_size_hint()

    def update_size_hint(self):
        previous_lines = len(self.lines)

        self.lines = {}

        items = self.checked_items_text()
        if not items:
            self.update()
            return

        option = QtWidgets.QStyleOptionComboBox()
        self.initStyleOption(option)
        btn_rect = self.style().subControlRect(
            QtWidgets.QStyle.CC_ComboBox,
            option,
            QtWidgets.QStyle.SC_ComboBoxArrow
        )
        total_width = self.width() - btn_rect.width()
        font_metricts = self.fontMetrics()

        line = 0
        self.lines = {line: []}

        font_metricts = self.fontMetrics()
        left_x = None
        for item in items:
            if left_x is None:
                left_x = 0 + self.left_offset
            rect = font_metricts.boundingRect(item)
            width = rect.width() + (2 * self.left_right_padding)
            right_x = left_x + width
            if right_x > total_width:
                if self.lines.get(line):
                    line += 1
                    left_x = None
                    self.lines[line] = [item]
                else:
                    self.lines[line] = [item]
                    line += 1
                    left_x = None
            else:
                self.lines[line].append(item)
                left_x = left_x + width + self.item_spacing

        self.update()
        if len(self.lines) != previous_lines:
            self.updateGeometry()

    def sizeHint(self):
        value = super(MultiSelectionComboBox, self).sizeHint()
        lines = len(self.lines)
        if lines == 0:
            lines = 1
        value.setHeight(
            (lines * self.item_height)
            + (2 * self.top_bottom_margins)
        )
        return value

    def setItemCheckState(self, index, state):
        self.setItemData(index, state, QtCore.Qt.CheckStateRole)

    def set_value(self, values):
        for idx in range(self.count()):
            value = self.itemData(idx, role=QtCore.Qt.UserRole)
            state = self.itemData(idx, role=QtCore.Qt.CheckStateRole)
            if value in values:
                check_state = QtCore.Qt.Checked
            else:
                check_state = QtCore.Qt.Unchecked
            self.setItemData(idx, check_state, QtCore.Qt.CheckStateRole)

    def value(self):
        items = list()
        for idx in range(self.count()):
            state = self.itemData(idx, role=QtCore.Qt.CheckStateRole)
            if state == QtCore.Qt.Checked:
                items.append(
                    self.itemData(idx, role=QtCore.Qt.UserRole)
                )
        return items

    def checked_items_text(self):
        items = list()
        for idx in range(self.count()):
            state = self.itemData(idx, role=QtCore.Qt.CheckStateRole)
            if state == QtCore.Qt.Checked:
                items.append(self.itemText(idx))
        return items

    def wheelEvent(self, event):
        event.ignore()

    def keyPressEvent(self, event):
        if (
            event.key() == QtCore.Qt.Key_Down
            and event.modifiers() & QtCore.Qt.AltModifier
        ):
            self.showPopup()
            return

        if event.key() in self.ignored_keys:
            event.ignore()
            return

        return super(MultiSelectionComboBox, self).keyPressEvent(event)

    def _update_item_delegate(self):
        opt = QtWidgets.QStyleOptionComboBox()
        opt.initFrom(self)
        if self.style().styleHint(
            QtWidgets.QStyle.SH_ComboBox_Popup, opt, self
        ):
            delegate = ComboMenuDelegate(self)
        else:
            delegate = ComboItemDelegate(self)
        self.setItemDelegate(delegate)
