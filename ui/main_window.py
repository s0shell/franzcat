from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QFrame,
    QTabWidget, QStatusBar
)

from PyQt6.QtCore import QByteArray
from PyQt6.QtGui import QFont

from panels.cert_panel import CertPanel
from panels.randomizer_panel import RandomizerPanel
from panels.reader_panel import ReaderPanel
from panels.schema_panel import SchemaPanel
from panels.writer_panel import WriterPanel
from styles.theme_manager import load_stylesheet
from services.settings_store import SettingsStore
from widgets.log_pane import LogPane


APP_VERSION = "1.01"


class MainWindow(QMainWindow):
    def __init__(self, store: SettingsStore, dark_mode: bool = True):
        super().__init__()
        self._store = store
        self._dark_mode = dark_mode
        self.setWindowTitle("FranzCat  //  Kafka Testing Tool")
        self.resize(1100, 700)
        self._build()
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage(
            f"FranzCat v{APP_VERSION} | MIT License | Developed by Karol Wuwer with AI assistance"
        )
        self._apply_theme_labels()
        self._init_settings()

    def _init_settings(self):
        """Register persisted widgets, restore them, and restore window geometry."""
        store = self._store
        store.register("schema", self.schema_panel.settings_widgets())
        store.register("certs", self.cert_panel.settings_widgets())
        store.register("reader", self.reader_panel.settings_widgets())
        store.register("writer", self.writer_panel.settings_widgets())
        store.restore()

        geometry = store.get("window.geometry")
        if isinstance(geometry, str):
            try:
                self.restoreGeometry(QByteArray.fromBase64(geometry.encode("ascii")))
            except UnicodeEncodeError:
                pass

    def closeEvent(self, event):
        geometry = bytes(self.saveGeometry().toBase64()).decode("ascii")
        self._store.set("window.geometry", geometry)
        self._store.save()
        super().closeEvent(event)

    def _build(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(10)

        # ── Header ──────────────────────────────────────
        header_row = QHBoxLayout()

        self.lbl_header = QLabel("FranzCat")
        self.lbl_header.setFont(QFont("Courier New", 22, QFont.Weight.Bold))
        self.lbl_header.setStyleSheet("color: #4caf50; letter-spacing: 8px; padding: 4px 0;")

        self.btn_theme = QPushButton("☀  LIGHT")
        self.btn_theme.setFixedWidth(110)
        self.btn_theme.setToolTip("Switch between dark and light mode")
        self.btn_theme.clicked.connect(self._toggle_theme)

        header_row.addWidget(self.lbl_header)
        header_row.addStretch()
        header_row.addWidget(self.btn_theme)
        root.addLayout(header_row)

        self.lbl_sub = QLabel(f"FranzCat  / v{APP_VERSION}")
        self.lbl_sub.setStyleSheet("color: #2e5a2e; letter-spacing: 3px; font-size: 11px;")
        root.addWidget(self.lbl_sub)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        root.addWidget(sep)

        # ── Config tabs (schema / certs ) ──
        cfg_tabs = QTabWidget()
        cfg_tabs.setMaximumHeight(320)

        self.schema_panel = SchemaPanel()
        self.cert_panel   = CertPanel()

        # Give SchemaPanel access to TLS config
        self.schema_panel.set_cert_panel(self.cert_panel)

        cfg_tabs.addTab(self.schema_panel, "SCHEMA")
        cfg_tabs.addTab(self.cert_panel,   "CERTIFICATES")
        root.addWidget(cfg_tabs)

        # ── Operations (randomizer / reader / writer) ──
        ops_tabs = QTabWidget()

        self.rand_panel   = RandomizerPanel()
        self.reader_panel = ReaderPanel()
        self.writer_panel = WriterPanel()

        # Give RandomizerPanel access to the loaded schema
        self.rand_panel.set_schema_panel(self.schema_panel)

        # Give ReaderPanel access to TLS config and schema
        self.reader_panel.set_cert_panel(self.cert_panel)
        self.reader_panel.set_schema_panel(self.schema_panel)

        # Give WriterPanel access to all config panels
        self.writer_panel.set_cert_panel(self.cert_panel)
        self.writer_panel.set_schema_panel(self.schema_panel)
        self.writer_panel.set_rand_panel(self.rand_panel)

        ops_tabs.addTab(self.rand_panel,   "RANDOMIZE")
        ops_tabs.addTab(self.reader_panel, "READ")
        ops_tabs.addTab(self.writer_panel, "SEND")
        root.addWidget(ops_tabs, 1)

    def _toggle_theme(self):
        self._dark_mode = not self._dark_mode
        QApplication.instance().setStyleSheet(load_stylesheet(self._dark_mode))
        LogPane.set_dark_mode(self._dark_mode)
        # Fix Issue #1
        SchemaPanel.rerender(self.schema_panel)

        self._apply_theme_labels()
        self._store.set("window.dark_mode", self._dark_mode)

    def _apply_theme_labels(self):
        if self._dark_mode:
            self.btn_theme.setText("☀  LIGHT")
            self.lbl_header.setStyleSheet(
                "color: #4caf50; letter-spacing: 8px; padding: 4px 0;"
            )
            self.lbl_sub.setStyleSheet(
                "color: #2e5a2e; letter-spacing: 3px; font-size: 11px;"
            )
        else:
            self.btn_theme.setText("☾  DARK")
            self.lbl_header.setStyleSheet(
                "color: #2e7d32; letter-spacing: 8px; padding: 4px 0;"
            )
            self.lbl_sub.setStyleSheet(
                "color: #4a7a4a; letter-spacing: 3px; font-size: 11px;"
            )