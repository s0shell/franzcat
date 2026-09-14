import json

from PyQt6.QtWidgets import (
    QApplication, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QGroupBox
)

from services.avro_randomizer import AvroRandomizer
from widgets.log_pane import LogPane

class RandomizerPanel(QGroupBox):
    def __init__(self):
        super().__init__("[ AVRO DATA RANDOMIZER ]")
        self._schema_panel  = None   # injected by MainWindow
        self._last_payload  = None   # last generated dict, for writer panel
        self._engine        = AvroRandomizer()
        self._gen_count     = 0
        self._build()

    def set_schema_panel(self, schema_panel):
        self._schema_panel = schema_panel

    def get_last_payload(self) -> dict | None:
        return self._last_payload

    def _build(self):
        vbox = QVBoxLayout(self)
        vbox.setSpacing(8)

        top = QHBoxLayout()
        self.btn_randomize = QPushButton("GENERATE RANDOM PAYLOAD")
        self.btn_randomize.setObjectName("btn_accent")
        self.btn_copy  = QPushButton("COPY JSON")
        self.btn_clear = QPushButton("CLEAR")
        self.lbl_count = QLabel("0 generated")
        self.lbl_count.setObjectName("lbl_status_inf")
        top.addWidget(self.btn_randomize)
        top.addWidget(self.btn_copy)
        top.addWidget(self.btn_clear)
        top.addSpacing(12)
        top.addWidget(self.lbl_count)
        top.addStretch()

        self.lbl_note = QLabel(
            "schema must be loaded first — values are generated per field type and constraints"
        )
        self.payload_view = LogPane("// generated payload will appear here")

        vbox.addLayout(top)
        vbox.addWidget(self.lbl_note)
        vbox.addWidget(self.payload_view)

        self.btn_randomize.clicked.connect(self._on_randomize)
        self.btn_copy.clicked.connect(self._on_copy)
        self.btn_clear.clicked.connect(self._on_clear)

    # ── slots ────────────────────────────────────────────────

    def _on_randomize(self):
        if self._schema_panel is None:
            self.payload_view.append_line("! schema panel not connected", "error")
            return

        schema = self._schema_panel.get_loaded_schema()
        if schema is None:
            self.payload_view.append_line(
                "! no schema loaded — fetch a schema from the SCHEMA tab first", "error"
            )
            return

        try:
            payload = self._engine.generate(schema)
        except Exception as exc:
            self.payload_view.append_line(f"! generation error: {exc}", "error")
            return

        self._last_payload = payload
        self._gen_count   += 1
        self.lbl_count.setText(f"{self._gen_count} generated")

        pretty = json.dumps(payload, indent=2, ensure_ascii=False)

        self.payload_view.clear_log()
        self.payload_view.append_line(
            f"// payload #{self._gen_count}  —  "
            f"{len(pretty)} bytes  —  "
            f"{self._count_fields(payload)} fields",
            "muted"
        )
        self.payload_view.append_line("─" * 60, "muted")
        for line in pretty.splitlines():
            # colour keys differently from values for readability
            self.payload_view.append_line(line, "data")

    def _on_copy(self):
        if self._last_payload is None:
            return
        QApplication.clipboard().setText(
            json.dumps(self._last_payload, indent=2, ensure_ascii=False)
        )

    def _on_clear(self):
        self.payload_view.clear_log()
        self._last_payload = None
        self._gen_count    = 0
        self.lbl_count.setText("0 generated")

    # ── helpers ──────────────────────────────────────────────

    @staticmethod
    def _count_fields(obj, _depth=0) -> int:
        """Recursively count leaf values in a nested dict/list."""
        if isinstance(obj, dict):
            return sum(RandomizerPanel._count_fields(v, _depth + 1) for v in obj.values())
        if isinstance(obj, list):
            return sum(RandomizerPanel._count_fields(v, _depth + 1) for v in obj)
        return 1