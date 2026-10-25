from PyQt6.QtCore import QUrl, pyqtSignal
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QPushButton, QWidget

from services.environment_store import environments_dir

CUSTOM = "(custom)"


class EnvironmentBar(QWidget):
    """Environment selector: '(custom)' or one of the loaded environments."""

    selected = pyqtSignal(str)   # user picked an entry ('' for custom)
    reload_requested = pyqtSignal()

    def __init__(self):
        super().__init__()
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)

        lbl = QLabel("Environment")
        lbl.setObjectName("lbl_key")
        self.cmb = QComboBox()
        self.cmb.setMinimumWidth(220)
        self.btn_reload = QPushButton("RELOAD")
        self.btn_reload.setToolTip("Re-read environment files and re-apply the selected one")
        self.btn_folder = QPushButton("OPEN FOLDER")
        self.btn_folder.setToolTip("Open the folder with environment files")
        self.lbl_state = QLabel("")
        self.lbl_state.setObjectName("lbl_status_inf")

        row.addWidget(lbl)
        row.addWidget(self.cmb)
        row.addWidget(self.btn_reload)
        row.addWidget(self.btn_folder)
        row.addSpacing(8)
        row.addWidget(self.lbl_state, 1)

        self.cmb.activated.connect(self._on_activated)
        self.btn_reload.clicked.connect(self.reload_requested)
        self.btn_folder.clicked.connect(self._open_folder)
        self.set_names([])

    def set_names(self, names: list[str], current: str = "") -> None:
        """Rebuild the list without emitting 'selected'."""
        self.cmb.blockSignals(True)
        self.cmb.clear()
        self.cmb.addItem(CUSTOM)
        self.cmb.addItems(names)
        idx = self.cmb.findText(current) if current else 0
        self.cmb.setCurrentIndex(max(idx, 0))
        self.cmb.blockSignals(False)

    def current_name(self) -> str:
        """Selected environment name, '' for custom."""
        return "" if self.cmb.currentIndex() <= 0 else self.cmb.currentText()

    def set_state(self, text: str) -> None:
        self.lbl_state.setText(text)

    def _on_activated(self, index: int) -> None:
        self.selected.emit(self.current_name())

    def _open_folder(self) -> None:
        path = environments_dir()
        path.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
