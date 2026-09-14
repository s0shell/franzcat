import json
import datetime
import base64

from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox,
    QTextEdit, QGroupBox, QSplitter, QCheckBox, QSpinBox
)
from PyQt6.QtGui import QFont
from PyQt6.QtCore import Qt

from widgets.kafka_broker_bar import KafkaBrokerBar
from widgets.log_pane import LogPane
from workers.kafka_consumer_worker import KafkaConsumerWorker

class ReaderPanel(QGroupBox):
    def __init__(self):
        super().__init__("[ READ FROM TOPIC ]")
        self._worker      = None
        self._cert_panel  = None
        self._schema_panel = None
        self._messages:  list[dict] = []   # stored envelope dicts
        self._current_idx: int      = -1   # which message is shown in detail pane
        self._msg_count:   int      = 0
        self._build()

    def set_cert_panel(self, p):   self._cert_panel   = p
    def set_schema_panel(self, p): self._schema_panel = p

    # ── UI build ─────────────────────────────────────────────

    def _build(self):
        root = QVBoxLayout(self)
        root.setSpacing(8)

        # ── connection controls ──────────────────────────────
        self.broker_bar = KafkaBrokerBar(show_group=True)
        root.addWidget(self.broker_bar)

        opts = QHBoxLayout()
        lbl_offset = QLabel("Start Offset")
        lbl_offset.setObjectName("lbl_key")
        self.cmb_offset = QComboBox()
        self.cmb_offset.addItems(["latest", "earliest", "specific"])
        self.inp_offset_val = QSpinBox()
        self.inp_offset_val.setRange(0, 99999999)
        self.inp_offset_val.setFixedWidth(100)
        self.inp_offset_val.setEnabled(False)
        self.cmb_offset.currentTextChanged.connect(
            lambda t: self.inp_offset_val.setEnabled(t == "specific")
        )
        lbl_count = QLabel("Max Messages")
        lbl_count.setObjectName("lbl_key")
        self.inp_count = QSpinBox()
        self.inp_count.setRange(1, 1000)
        self.inp_count.setValue(1)
        self.inp_count.setFixedWidth(80)
        opts.addWidget(lbl_offset)
        opts.addWidget(self.cmb_offset)
        opts.addWidget(self.inp_offset_val)
        opts.addSpacing(16)
        opts.addWidget(lbl_count)
        opts.addWidget(self.inp_count)
        opts.addStretch()
        root.addLayout(opts)

        btns = QHBoxLayout()
        self.btn_read = QPushButton("READ MESSAGE(S)")
        self.btn_read.setObjectName("btn_accent")
        self.btn_stop = QPushButton("STOP")
        self.btn_stop.setObjectName("btn_danger")
        self.btn_stop.setEnabled(False)
        self.btn_clear_log = QPushButton("CLEAR")
        self.lbl_msg_count = QLabel("0 received")
        self.lbl_msg_count.setObjectName("lbl_status_inf")
        btns.addWidget(self.btn_read)
        btns.addWidget(self.btn_stop)
        btns.addWidget(self.btn_clear_log)
        btns.addSpacing(12)
        btns.addWidget(self.lbl_msg_count)
        btns.addStretch()
        root.addLayout(btns)

        # ── horizontal splitter: log | detail ────────────────
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(4)

        # Left — raw event log
        self.log = LogPane("// consumed messages will appear here")
        splitter.addWidget(self.log)

        # Right — detail viewer
        detail = QWidget()
        detail_vbox = QVBoxLayout(detail)
        detail_vbox.setContentsMargins(6, 0, 0, 0)
        detail_vbox.setSpacing(6)

        # Navigation bar
        nav = QHBoxLayout()
        self.btn_prev = QPushButton("< PREV")
        self.btn_prev.setEnabled(False)
        self.lbl_nav = QLabel("no messages")
        self.lbl_nav.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_nav.setObjectName("lbl_status_inf")
        self.lbl_nav.setMinimumWidth(100)
        self.btn_next = QPushButton("NEXT >")
        self.btn_next.setEnabled(False)
        self.btn_copy_detail = QPushButton("COPY")
        self.btn_copy_detail.setEnabled(False)
        nav.addWidget(self.btn_prev)
        nav.addWidget(self.lbl_nav, 1)
        nav.addWidget(self.btn_next)
        nav.addSpacing(8)
        nav.addWidget(self.btn_copy_detail)
        detail_vbox.addLayout(nav)

        # Ignore-schema / display-format row
        raw_row = QHBoxLayout()
        self.chk_ignore_schema = QCheckBox("Ignore schema")
        self.chk_ignore_schema.setToolTip(
            "Skip Avro deserialization and show raw bytes in the chosen format."
        )
        lbl_fmt = QLabel("Display as")
        lbl_fmt.setObjectName("lbl_key")
        self.cmb_display_fmt = QComboBox()
        self.cmb_display_fmt.addItems([
            "auto-detect",
            "hex",
            "hex dump",
            "UTF-8 raw",
            "base64",
        ])
        raw_row.addWidget(self.chk_ignore_schema)
        raw_row.addSpacing(16)
        raw_row.addWidget(lbl_fmt)
        raw_row.addWidget(self.cmb_display_fmt)
        raw_row.addStretch()
        detail_vbox.addLayout(raw_row)

        # Metadata line
        self.lbl_meta = QLabel("")
        self.lbl_meta.setObjectName("lbl_status_inf")
        self.lbl_meta.setWordWrap(True)
        detail_vbox.addWidget(self.lbl_meta)

        # Deserialized content — scrollable, read-only
        self.detail_view = QTextEdit()
        self.detail_view.setReadOnly(True)
        self.detail_view.setFont(QFont("Courier New", 11))
        self.detail_view.setPlaceholderText(
            "// select a message with < > to inspect it here\n"
            "// avro messages will be deserialized using the loaded schema"
        )
        detail_vbox.addWidget(self.detail_view, 1)

        splitter.addWidget(detail)
        splitter.setSizes([420, 460])

        root.addWidget(splitter, 1)

        # Wire
        self.btn_read.clicked.connect(self._on_read)
        self.btn_stop.clicked.connect(self._on_stop)
        self.btn_clear_log.clicked.connect(self._on_clear)
        self.btn_prev.clicked.connect(self._on_prev)
        self.btn_next.clicked.connect(self._on_next)
        self.btn_copy_detail.clicked.connect(self._on_copy_detail)
        self.chk_ignore_schema.toggled.connect(self._on_view_opts_changed)
        self.cmb_display_fmt.currentIndexChanged.connect(self._on_view_opts_changed)

    # ── consumer control ─────────────────────────────────────

    def _on_read(self):
        broker   = self.broker_bar.inp_broker.text().strip()
        topic    = self.broker_bar.inp_topic.text().strip()
        group_id = self.broker_bar.inp_group.text().strip() or "kafkapt-consumer"

        if not broker or not topic:
            self.log.append_line("! broker and topic are required", "error")
            return

        if self._worker and self._worker.isRunning():
            return

        offset_mode     = self.cmb_offset.currentText()
        specific_offset = self.inp_offset_val.value()
        max_messages    = self.inp_count.value()

        tls_cfg = None
        if self._cert_panel is not None:
            tls_cfg = self._cert_panel.get_tls_config().get("broker")

        self._msg_count = 0
        self.lbl_msg_count.setText("0 received")
        self.btn_read.setEnabled(False)
        self.btn_stop.setEnabled(True)

        self._worker = KafkaConsumerWorker(
            broker, topic, group_id,
            offset_mode, specific_offset, max_messages,
            tls_cfg,
        )
        self._worker.message_received.connect(self._on_message)
        self._worker.status_update.connect(self._on_status)
        self._worker.consumer_error.connect(self._on_error)
        self._worker.done.connect(self._on_done)
        self._worker.start()

    def _on_stop(self):
        if self._worker and self._worker.isRunning():
            self.log.append_line("// stop requested — finishing current poll …", "warn")
            self._worker.stop()

    # ── worker signal handlers ───────────────────────────────

    def _on_message(
        self,
        topic: str,
        partition: int,
        offset: int,
        ts_type: int,
        ts_ms: int,
        decoded: str,
        raw: bytes,
    ):
        self._msg_count += 1
        self.lbl_msg_count.setText(f"{self._msg_count} received")

        ts_str = self._fmt_ts(ts_ms, ts_type)

        # Store envelope for the detail viewer
        self._messages.append({
            "topic":     topic,
            "partition": partition,
            "offset":    offset,
            "ts_ms":     ts_ms,
            "ts_type":   ts_type,
            "ts_str":    ts_str,
            "decoded":   decoded,
            "raw":       raw,
        })

        # Log summary line (no raw content — detail pane handles that)
        self.log.append_line(
            f"── msg #{self._msg_count}  "
            f"topic={topic}  partition={partition}  "
            f"offset={offset}  {ts_str}",
            "ok",
        )
        # Brief decoded preview (first 2 lines only)
        preview = decoded.splitlines()[:2]
        for line in preview:
            self.log.append_line(line, "data")
        if len(decoded.splitlines()) > 2:
            self.log.append_line("  …", "muted")
        self.log.append_line("", "muted")

        # Auto-navigate to newest message
        self._show_message(len(self._messages) - 1)

    def _on_status(self, msg: str):
        self.log.append_line(f"// {msg}", "muted")

    def _on_error(self, msg: str):
        self.log.append_line(f"! {msg}", "error")

    def _on_done(self, total: int):
        self.btn_read.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.log.append_line(
            f"// consumer closed  —  {total} message(s) received", "warn"
        )

    # ── detail viewer ────────────────────────────────────────

    def _show_message(self, idx: int):
        if not self._messages or idx < 0 or idx >= len(self._messages):
            return

        self._current_idx = idx
        env = self._messages[idx]
        n   = len(self._messages)

        # Navigation labels / button state
        self.lbl_nav.setText(f"msg  {idx + 1}  /  {n}")
        self.btn_prev.setEnabled(idx > 0)
        self.btn_next.setEnabled(idx < n - 1)
        self.btn_copy_detail.setEnabled(True)

        # Metadata
        self.lbl_meta.setText(
            f"topic={env['topic']}  partition={env['partition']}  "
            f"offset={env['offset']}  {env['ts_str']}"
        )

        # Deserialize and render
        content = self._deserialize(
            env["raw"],
            ignore_schema = self.chk_ignore_schema.isChecked(),
            display_fmt   = self.cmb_display_fmt.currentText(),
        )
        self.detail_view.setPlainText(content)

    def _on_prev(self):
        self._show_message(self._current_idx - 1)

    def _on_next(self):
        self._show_message(self._current_idx + 1)

    def _on_copy_detail(self):
        QApplication.clipboard().setText(self.detail_view.toPlainText())

    def _on_view_opts_changed(self):
        """Re-render the current message when ignore-schema or display format changes."""
        if self._current_idx >= 0:
            self._show_message(self._current_idx)

    def _on_clear(self):
        self.log.clear_log()
        self._messages.clear()
        self._current_idx = -1
        self._msg_count   = 0
        self.lbl_msg_count.setText("0 received")
        self.lbl_nav.setText("no messages")
        self.lbl_meta.setText("")
        self.detail_view.clear()
        self.btn_prev.setEnabled(False)
        self.btn_next.setEnabled(False)
        self.btn_copy_detail.setEnabled(False)

    # ── deserialization ──────────────────────────────────────

    def _deserialize(
        self,
        raw: bytes,
        ignore_schema: bool = False,
        display_fmt:   str  = "auto-detect",
    ) -> str:
        """
        Deserialize raw message bytes for display.

        ignore_schema=True  → skip Avro path entirely, apply display_fmt directly
        display_fmt         → controls how raw bytes are rendered when schema is
                              ignored or unavailable:
                              auto-detect | hex | hex dump | UTF-8 raw | base64
        """
        if not raw:
            return "<empty payload>"

        # ── ignore-schema: go straight to raw rendering ───────
        if ignore_schema:
            return self._render_raw(raw, display_fmt)

        # ── Confluent Avro wire format (magic byte 0x00) ──────
        if len(raw) > 5 and raw[0] == 0x00:
            schema_id = int.from_bytes(raw[1:5], "big")
            payload   = raw[5:]
            schema    = (
                self._schema_panel.get_loaded_schema()
                if self._schema_panel else None
            )

            if schema is not None:
                try:
                    import io
                    import fastavro
                    parsed_schema = fastavro.parse_schema(dict(schema))
                    record = fastavro.schemaless_reader(
                        io.BytesIO(payload), parsed_schema
                    )
                    header = (
                        f"// confluent-avro  schema_id={schema_id}"
                        f"  ({len(payload)} bytes)\n"
                        + "─" * 48 + "\n"
                    )
                    return header + json.dumps(record, indent=2, default=str)
                except ImportError:
                    return (
                        f"// confluent-avro  schema_id={schema_id}\n"
                        f"// fastavro not installed — pip install fastavro\n"
                        f"// raw payload hex:\n{payload.hex()}"
                    )
                except Exception as exc:
                    return (
                        f"// confluent-avro  schema_id={schema_id}\n"
                        f"// deserialization error: {exc}\n"
                        f"// raw payload hex:\n{payload.hex()}"
                    )
            else:
                return (
                    f"// confluent-avro  schema_id={schema_id}  ({len(payload)} bytes)\n"
                    f"// load schema ID {schema_id} in the SCHEMA tab to deserialize\n"
                    f"// — or check 'Ignore schema' to view raw bytes —\n"
                    f"// raw payload hex:\n{payload.hex()}"
                )

        # ── not Avro: apply display_fmt or auto-detect ────────
        return self._render_raw(raw, display_fmt)

    def _render_raw(self, raw: bytes, display_fmt: str) -> str:
        """Render raw bytes according to the chosen display format."""

        if display_fmt == "hex":
            return raw.hex()

        if display_fmt == "hex dump":
            return self._hex_dump(raw)

        if display_fmt == "base64":
            return base64.b64encode(raw).decode("ascii")

        if display_fmt == "UTF-8 raw":
            try:
                return raw.decode("utf-8")
            except UnicodeDecodeError as exc:
                return (
                    f"// UTF-8 decode failed: {exc}\n"
                    f"// falling back to hex dump:\n{self._hex_dump(raw)}"
                )

        # auto-detect: JSON → UTF-8 → hex dump
        try:
            parsed = json.loads(raw.decode("utf-8"))
            return json.dumps(parsed, indent=2, ensure_ascii=False)
        except Exception:
            pass
        try:
            return raw.decode("utf-8")
        except Exception:
            pass
        return f"// binary payload  {len(raw)} bytes\n{self._hex_dump(raw)}"

    @staticmethod
    def _hex_dump(data: bytes, width: int = 16) -> str:
        """
        Classic hex editor layout:
          0000  0c 54 45 53 54 2d 31 0e  4d 6f 6e 69 74 6f 72 02  .TEST-1. Monitor.
        """
        lines = []
        for offset in range(0, len(data), width):
            chunk     = data[offset : offset + width]
            hex_part  = " ".join(f"{b:02x}" for b in chunk)
            # Insert a visual gap at the midpoint
            mid       = width // 2 * 3 - 1          # character position of gap
            if len(hex_part) > mid:
                hex_part = hex_part[:mid] + "  " + hex_part[mid:]
            ascii_part = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
            col_w     = width * 3 + 1                # padded hex column width
            lines.append(f"{offset:04x}  {hex_part:<{col_w}}  {ascii_part}")
        return "\n".join(lines)

    # ── helpers ──────────────────────────────────────────────

    @staticmethod
    def _fmt_ts(ts_ms: int, ts_type: int = 0) -> str:
        """
        Format a Kafka message timestamp.

        ts_type:  0 = TIMESTAMP_NOT_AVAILABLE  (value is undefined — show nothing)
                  1 = TIMESTAMP_CREATE_TIME     (set by producer)
                  2 = TIMESTAMP_LOG_APPEND_TIME (set by broker on write)
        """
        _TYPE_LABEL = {1: "create", 2: "append"}

        if ts_type == 0 or ts_ms <= 0:
            return "no timestamp"

        try:
            dt     = datetime.datetime.fromtimestamp(
                ts_ms / 1000, tz=datetime.timezone.utc
            )
            label  = _TYPE_LABEL.get(ts_type, "")
            suffix = f"  [{label}]" if label else ""
            return dt.strftime("%Y-%m-%d %H:%M:%S UTC") + suffix
        except (OSError, OverflowError, ValueError):
            return f"ts={ts_ms} ms (parse error)"