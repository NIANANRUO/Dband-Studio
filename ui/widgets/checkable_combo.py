from PySide6.QtWidgets import QComboBox, QStyledItemDelegate
from PySide6.QtCore import Qt, Signal, QEvent
from PySide6.QtGui import QStandardItemModel, QPalette

class CheckableComboBox(QComboBox):
    """A ComboBox that allows multiple items to be checked."""
    selection_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.view().pressed.connect(self._handle_item_pressed)
        self.setModel(QStandardItemModel(self))
        self._changed = False
        
        # Prevent popup from closing when clicking an item
        self.view().viewport().installEventFilter(self)

    def _handle_item_pressed(self, index):
        item = self.model().itemFromIndex(index)
        if item.checkState() == Qt.Checked:
            item.setCheckState(Qt.Unchecked)
        else:
            item.setCheckState(Qt.Checked)
        self._changed = True
        self.selection_changed.emit()

    def eventFilter(self, obj, event):
        # Don't close the popup on mouse release
        if obj == self.view().viewport():
            if event.type() == QEvent.MouseButtonRelease:
                return True
        return super().eventFilter(obj, event)

    def hidePopup(self):
        # Emit signal if something was changed while popup was open
        if self._changed:
            self._changed = False
        super().hidePopup()

    def add_item(self, text, checked=True):
        super().addItem(text)
        item = self.model().item(self.count() - 1, 0)
        item.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
        item.setCheckState(Qt.Checked if checked else Qt.Unchecked)

    def get_checked_items(self):
        checked = []
        for i in range(self.count()):
            item = self.model().item(i, 0)
            if item.checkState() == Qt.Checked:
                checked.append(self.itemText(i))
        return checked

    def clear_items(self):
        self.clear()
