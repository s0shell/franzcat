import json

from PyQt6.QtWidgets import (QGroupBox, QGridLayout, QLabel, QLineEdit, QSpinBox, QPushButton)

from widgets.log_pane import LogPane
from workers.schema_fetch_worker import SchemaFetchWorker

class SchemaPanel(QGroupBox):
    def __init__(self):
        super().__init__("[ SCHEMA REGISTRY ]")
        self._cert_panel   = None   # injected by MainWindow after construction
        self._fetch_worker = None   # active QThread, kept alive during fetch
        self._last_schema  = None   # last successfully parsed schema dict
        self._build()

    def set_cert_panel(self, cert_panel):
        """Called by MainWindow so SchemaPanel can read TLS config on demand."""
        self._cert_panel = cert_panel

    def get_loaded_schema(self) -> dict | None:
        """Returns the last successfully fetched Avro schema dict, or None."""
        return self._last_schema

    def _build(self):
        grid = QGridLayout(self)
        grid.setSpacing(8)
        grid.setColumnStretch(1, 1)

        # Registry URL
        lbl_url = QLabel("Registry URL")
        lbl_url.setObjectName("lbl_key")
        self.inp_url = QLineEdit()
        self.inp_url.setPlaceholderText("http://schema-registry:8081")
        grid.addWidget(lbl_url, 0, 0)
        grid.addWidget(self.inp_url, 0, 1, 1, 2)

        # Schema ID
        lbl_id = QLabel("Schema ID")
        lbl_id.setObjectName("lbl_key")
        self.inp_schema_id = QSpinBox()
        self.inp_schema_id.setRange(1, 999999)
        self.inp_schema_id.setValue(1)
        self.inp_schema_id.setFixedWidth(100)
        grid.addWidget(lbl_id, 1, 0)
        grid.addWidget(self.inp_schema_id, 1, 1)

        # Load button + status
        self.btn_load = QPushButton("FETCH SCHEMA")
        self.btn_load.setObjectName("btn_accent")
        self.btn_load.setFixedWidth(140)
        grid.addWidget(self.btn_load, 1, 2)

        # Schema preview pane
        self.schema_view = LogPane("// fetched schema will appear here")
        self.schema_view.setMaximumHeight(160)
        grid.addWidget(self.schema_view, 3, 0, 1, 3)

        # Wire stub
        self.btn_load.clicked.connect(self._on_fetch)

    def _on_fetch(self):
        url = self.inp_url.text().strip()
        sid = self.inp_schema_id.value()

        if not url:
            self.schema_view.clear_log()
            self.schema_view.append_line("Registry URL is required!", "error")
            return

        # Prevent concurrent fetches
        if self._fetch_worker and self._fetch_worker.isRunning():
            return

        # Resolve mTLS config for Schema Registry (None if disabled)
        tls_cfg = None
        if self._cert_panel is not None:
            tls_cfg = self._cert_panel.get_tls_config().get("schema_registry")

        self.btn_load.setEnabled(False)
        self.schema_view.clear_log()
        self.schema_view.append_line(f"connecting to {url} …", "info")
        self.schema_view.append_line(
            f"GET {url}/schemas/ids/{sid}", "muted"
        )
        if tls_cfg:
            self.schema_view.append_line(
                f"mTLS: cert={tls_cfg.get('client_cert') or '—'}  "
                f"verify={tls_cfg.get('verify', True)}", "muted"
            )
        else:
            self.schema_view.append_line("mTLS: disabled (plain HTTP / no client cert)", "muted")

        self._fetch_worker = SchemaFetchWorker(url, sid, tls_cfg)
        self._fetch_worker.result.connect(self._on_fetch_result)
        self._fetch_worker.error.connect(self._on_fetch_error)
        self._fetch_worker.finished.connect(lambda: self.btn_load.setEnabled(True))
        self._fetch_worker.start()

    def _on_fetch_result(self, pretty: str, schema_type: str):
        self.schema_view.append_line("─" * 60, "muted")
        for line in pretty.splitlines():
            self.schema_view.append_line(line, "data")

        # Cache parsed schema for the randomizer
        try:
            self._last_schema = json.loads(pretty)
        except ValueError:
            self._last_schema = None

    def _on_fetch_error(self, msg: str):
        self.schema_view.append_line(f"error: {msg}", "error")