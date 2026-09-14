import json
import base64
import os

from PyQt6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QComboBox,
    QTextEdit, QGroupBox, QCheckBox, QSpinBox,
)
from PyQt6.QtGui import QFont

from widgets.kafka_broker_bar import KafkaBrokerBar
from widgets.log_pane import LogPane
from workers.kafka_producer_worker import KafkaProducerWorker

class WriterPanel(QGroupBox):
    def __init__(self):
        super().__init__("[ SEND TO TOPIC ]")
        self._cert_panel   = None   # injected by MainWindow
        self._enc_panel    = None
        self._schema_panel = None
        self._rand_panel   = None
        self._worker       = None
        self._sent_total   = 0
        self._build()

    def set_cert_panel(self, p):   self._cert_panel   = p
    def set_enc_panel(self, p):    self._enc_panel    = p
    def set_schema_panel(self, p): self._schema_panel = p
    def set_rand_panel(self, p):   self._rand_panel   = p

    # ── UI ───────────────────────────────────────────────────

    def _build(self):
        vbox = QVBoxLayout(self)
        vbox.setSpacing(8)

        self.broker_bar = KafkaBrokerBar()
        vbox.addWidget(self.broker_bar)

        key_row = QHBoxLayout()
        lbl_key = QLabel("Message Key")
        lbl_key.setObjectName("lbl_key")
        self.inp_msg_key = QLineEdit()
        self.inp_msg_key.setPlaceholderText("optional partition key")
        key_row.addWidget(lbl_key)
        key_row.addWidget(self.inp_msg_key)
        vbox.addLayout(key_row)

        src_row = QHBoxLayout()
        lbl_src = QLabel("Payload Source")
        lbl_src.setObjectName("lbl_key")
        self.cmb_src = QComboBox()
        self.cmb_src.addItems(["Manual JSON", "From Randomizer", "From Reader (replay)"])
        self.cmb_src.currentTextChanged.connect(self._on_src_change)
        src_row.addWidget(lbl_src)
        src_row.addWidget(self.cmb_src)
        src_row.addStretch()
        vbox.addLayout(src_row)

        # Raw mode row
        raw_row = QHBoxLayout()
        self.chk_raw = QCheckBox("Ignore schema  —  send raw payload")
        self.chk_raw.setToolTip(
            "Bypass Avro serialization and send bytes directly.\n"
            "Useful for testing consumer error handling and deserialization edge cases."
        )
        lbl_raw_enc = QLabel("Encoding")
        lbl_raw_enc.setObjectName("lbl_key")
        self.cmb_raw_enc = QComboBox()
        self.cmb_raw_enc.addItems(["UTF-8", "hex", "base64"])
        self.cmb_raw_enc.setEnabled(False)
        self.lbl_raw_hint = QLabel("schema and encryption steps will be skipped")
        self.lbl_raw_hint.setObjectName("lbl_status_inf")
        self.lbl_raw_hint.setVisible(False)
        self.chk_raw.toggled.connect(self._on_raw_toggle)
        raw_row.addWidget(self.chk_raw)
        raw_row.addSpacing(20)
        raw_row.addWidget(lbl_raw_enc)
        raw_row.addWidget(self.cmb_raw_enc)
        raw_row.addSpacing(12)
        raw_row.addWidget(self.lbl_raw_hint)
        raw_row.addStretch()
        vbox.addLayout(raw_row)

        self.payload_edit = QTextEdit()
        self.payload_edit.setPlaceholderText('{\n  "field": "value"\n}')
        self.payload_edit.setFont(QFont("Courier New", 11))
        self.payload_edit.setMinimumHeight(120)
        vbox.addWidget(self.payload_edit)

        btns = QHBoxLayout()
        self.btn_send = QPushButton("SEND MESSAGE")
        self.btn_send.setObjectName("btn_accent")
        self.chk_repeat = QCheckBox("Repeat")
        self.inp_repeat_n = QSpinBox()
        self.inp_repeat_n.setRange(1, 10000)
        self.inp_repeat_n.setValue(1)
        self.inp_repeat_n.setFixedWidth(80)
        self.inp_repeat_n.setEnabled(False)
        self.chk_repeat.toggled.connect(self.inp_repeat_n.setEnabled)
        self.lbl_sent = QLabel("0 sent")
        self.lbl_sent.setObjectName("lbl_status_inf")
        btns.addWidget(self.btn_send)
        btns.addWidget(self.chk_repeat)
        btns.addWidget(self.inp_repeat_n)
        btns.addSpacing(12)
        btns.addWidget(self.lbl_sent)
        btns.addStretch()
        vbox.addLayout(btns)

        self.send_log = LogPane("// delivery reports will appear here")
        self.send_log.setMaximumHeight(140)
        vbox.addWidget(self.send_log)

        self.btn_send.clicked.connect(self._on_send)

    def _on_raw_toggle(self, checked: bool):
        self.cmb_raw_enc.setEnabled(checked)
        self.lbl_raw_hint.setVisible(checked)
        if checked:
            self.cmb_src.setEnabled(False)
            self.payload_edit.setEnabled(True)
            self.payload_edit.setPlaceholderText(
                "// raw payload — paste UTF-8 text, hex bytes, or base64\n"
                "// example hex: 00 00 00 00 01 0c 54 45 53 54\n"
                "// spaces and newlines in hex input are stripped automatically"
            )
        else:
            self.cmb_src.setEnabled(True)
            self._on_src_change(self.cmb_src.currentText())

    def _on_src_change(self, src: str):
        if self.chk_raw.isChecked():
            return   # raw mode overrides source
        manual = src == "Manual JSON"
        self.payload_edit.setEnabled(manual)
        if src == "From Randomizer":
            self.payload_edit.setPlaceholderText(
                "// payload will be generated fresh from schema for each message"
            )
        elif src == "From Reader (replay)":
            self.payload_edit.setPlaceholderText(
                "// paste a message from the READ tab here, or switch source to Manual JSON"
            )
            self.payload_edit.setEnabled(True)
        else:
            self.payload_edit.setPlaceholderText('{\n  "field": "value"\n}')

    # ── main send slot ───────────────────────────────────────

    def _on_send(self):
        broker  = self.broker_bar.inp_broker.text().strip()
        topic   = self.broker_bar.inp_topic.text().strip()
        msg_key = self.inp_msg_key.text().strip() or None

        if not broker or not topic:
            self.send_log.append_line("! broker and topic are required", "error")
            return

        if self._worker and self._worker.isRunning():
            self.send_log.append_line("! a send is already in progress", "warn")
            return

        repeat    = self.inp_repeat_n.value() if self.chk_repeat.isChecked() else 1
        key_bytes = msg_key.encode("utf-8") if msg_key else None

        # ── raw mode: bypass all serialization ───────────────
        if self.chk_raw.isChecked():
            raw_text = self.payload_edit.toPlainText().strip()
            if not raw_text:
                self.send_log.append_line("! payload is empty", "error")
                return
            encoding = self.cmb_raw_enc.currentText()
            try:
                value_bytes = self._encode_raw(raw_text, encoding)
            except Exception as exc:
                self.send_log.append_line(f"! raw encode error ({encoding}): {exc}", "error")
                return
            messages = [(key_bytes, value_bytes)] * repeat
            tls_cfg  = (
                self._cert_panel.get_tls_config().get("broker")
                if self._cert_panel else None
            )
            self.send_log.append_line(
                f"raw send  {len(value_bytes)} bytes × {repeat}  "
                f"encoding={encoding}  mTLS={'yes' if tls_cfg else 'no'}",
                "muted",
            )
            self.btn_send.setEnabled(False)
            self._worker = KafkaProducerWorker(broker, topic, messages, tls_cfg)
            self._worker.delivery_report.connect(self._on_delivery)
            self._worker.producer_error.connect(self._on_produce_error)
            self._worker.done.connect(self._on_produce_done)
            self._worker.start()
            return

        # ── normal mode: schema + encryption pipeline ────────
        src = self.cmb_src.currentText()

        # ── build payload dicts ──────────────────────────────
        payload_dicts = []

        if src == "From Randomizer":
            if self._rand_panel is None:
                self.send_log.append_line("! randomizer panel not connected", "error")
                return
            schema = (
                self._schema_panel.get_loaded_schema()
                if self._schema_panel else None
            )
            if schema is None:
                self.send_log.append_line(
                    "! no schema loaded — fetch schema before using randomizer source",
                    "error",
                )
                return
            try:
                for _ in range(repeat):
                    payload_dicts.append(self._rand_panel._engine.generate(schema))
            except Exception as exc:
                self.send_log.append_line(f"! randomizer error: {exc}", "error")
                return
        else:
            raw_text = self.payload_edit.toPlainText().strip()
            if not raw_text:
                self.send_log.append_line("! payload is empty", "error")
                return
            try:
                parsed = json.loads(raw_text)
            except json.JSONDecodeError as exc:
                self.send_log.append_line(f"! invalid JSON: {exc}", "error")
                return
            payload_dicts = [parsed] * repeat

        # ── serialize + encrypt ──────────────────────────────
        messages  = []

        schema_active = (
            self._schema_panel is not None
            and self._schema_panel.get_loaded_schema() is not None
        )
        enc_mode = (
            self._enc_panel.get_config()["mode"]
            if self._enc_panel else "None (Avro only)"
        )

        self.send_log.append_line(
            f"serializing {len(payload_dicts)} message(s)  "
            f"avro={'yes' if schema_active else 'no (plain JSON)'}  "
            f"encryption={enc_mode}",
            "muted",
        )

        for i, d in enumerate(payload_dicts):
            try:
                value_bytes = self._serialize_and_encrypt(d)
            except Exception as exc:
                self.send_log.append_line(f"! msg #{i + 1} serialize error: {exc}", "error")
                return
            messages.append((key_bytes, value_bytes))

        # ── TLS config for broker ────────────────────────────
        tls_cfg = None
        if self._cert_panel is not None:
            tls_cfg = self._cert_panel.get_tls_config().get("broker")

        self.send_log.append_line(
            f"producing to {broker}/{topic}  mTLS={'yes' if tls_cfg else 'no'}",
            "muted",
        )

        self.btn_send.setEnabled(False)
        self._worker = KafkaProducerWorker(broker, topic, messages, tls_cfg)
        self._worker.delivery_report.connect(self._on_delivery)
        self._worker.producer_error.connect(self._on_produce_error)
        self._worker.done.connect(self._on_produce_done)
        self._worker.start()

    # ── worker signal handlers ───────────────────────────────

    def _on_delivery(self, idx: int, topic: str, partition: int, offset: int, error: str):
        if error:
            self.send_log.append_line(
                f"! msg #{idx + 1} delivery failed: {error}", "error"
            )
        else:
            self.send_log.append_line(
                f"ok  msg #{idx + 1}  topic={topic}  "
                f"partition={partition}  offset={offset}",
                "ok",
            )

    def _on_produce_error(self, msg: str):
        self.send_log.append_line(f"! {msg}", "error")

    def _on_produce_done(self, sent: int, failed: int):
        self.btn_send.setEnabled(True)
        self._sent_total += sent
        self.lbl_sent.setText(f"{self._sent_total} sent")
        kind = "ok" if failed == 0 else "warn"
        self.send_log.append_line(
            f"// done  sent={sent}  failed={failed}", kind
        )

    def _encode_raw(self, text: str, encoding: str) -> bytes:
        """Convert the payload editor text to raw bytes for raw-mode sends."""
        if encoding == "hex":
            # Strip whitespace and newlines so hex can be pasted with spaces
            clean = "".join(text.split())
            try:
                return bytes.fromhex(clean)
            except ValueError as exc:
                raise ValueError(f"invalid hex input: {exc}") from exc
        if encoding == "base64":
            try:
                return base64.b64decode(text)
            except Exception as exc:
                raise ValueError(f"invalid base64 input: {exc}") from exc
        # UTF-8 default
        return text.encode("utf-8")

    # ── serialization pipeline ───────────────────────────────

    def _serialize_and_encrypt(self, payload_dict: dict) -> bytes:
        """
        Step 1 — Avro serialize (Confluent wire format) if schema is loaded,
                  otherwise fall back to plain UTF-8 JSON.
        Step 2 — Encrypt if an encryption mode is configured.
        """
        # ── Step 1: serialise ────────────────────────────────
        schema = (
            self._schema_panel.get_loaded_schema()
            if self._schema_panel else None
        )

        if schema is not None:
            try:
                import io
                import fastavro
            except ImportError:
                raise RuntimeError(
                    "fastavro not installed — run: pip install fastavro"
                )
            try:
                parsed_schema = fastavro.parse_schema(dict(schema))
                buf = io.BytesIO()
                fastavro.schemaless_writer(buf, parsed_schema, payload_dict)
                avro_bytes = buf.getvalue()
            except Exception as exc:
                raise RuntimeError(f"Avro serialization failed: {exc}")

            schema_id = self._schema_panel.inp_schema_id.value()
            raw: bytes = b"\x00" + schema_id.to_bytes(4, "big") + avro_bytes
        else:
            raw = json.dumps(payload_dict, ensure_ascii=False).encode("utf-8")

        # ── Step 2: encrypt ──────────────────────────────────
        if self._enc_panel is None:
            return raw

        enc_cfg = self._enc_panel.get_config()
        if enc_cfg["mode"] == "None (Avro only)":
            return raw

        return self._encrypt(raw, enc_cfg)

    def _decode_key(self, secret: str, encoding: str, required_len: int) -> bytes:
        """Decode the shared secret string into bytes of exactly required_len."""
        if not secret:
            raise RuntimeError("encryption is enabled but shared secret is empty")

        if encoding == "hex":
            try:
                key = bytes.fromhex(secret)
            except ValueError:
                raise RuntimeError("shared secret is not valid hex")
        elif encoding == "base64":
            try:
                key = base64.b64decode(secret)
            except Exception:
                raise RuntimeError("shared secret is not valid base64")
        else:   # utf-8 raw
            key = secret.encode("utf-8")

        if len(key) < required_len:
            # Zero-pad — mirrors what many naive implementations do; useful
            # for spotting weak key-derivation on the consumer side
            key = key + b"\x00" * (required_len - len(key))
        elif len(key) > required_len:
            key = key[:required_len]

        return key

    def _resolve_iv(self, enc_cfg: dict, iv_len: int) -> tuple[bytes, bool]:
        """
        Returns (iv_bytes, prepend_to_output).
        'Prepended to ciphertext' mode → random IV that the caller prepends.
        """
        iv_mode = enc_cfg.get("iv_mode", "Random per message")

        if iv_mode == "Fixed (provide below)":
            fixed = enc_cfg.get("fixed_iv", "").strip()
            if not fixed:
                raise RuntimeError("Fixed IV mode selected but no IV value provided")
            try:
                iv = bytes.fromhex(fixed)
            except ValueError:
                raise RuntimeError("fixed IV is not valid hex")
            if len(iv) != iv_len:
                raise RuntimeError(
                    f"IV must be exactly {iv_len} bytes, got {len(iv)}"
                )
            return iv, False

        if iv_mode == "Prepended to ciphertext":
            return os.urandom(iv_len), True

        # "Random per message" — default
        return os.urandom(iv_len), False

    def _encrypt(self, plaintext: bytes, enc_cfg: dict) -> bytes:
        try:
            from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
            from cryptography.hazmat.primitives import padding as crypto_padding
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM, ChaCha20Poly1305
        except ImportError:
            raise RuntimeError(
                "cryptography not installed — run: pip install cryptography"
            )

        mode_str = enc_cfg["mode"]
        encoding = enc_cfg.get("encoding", "hex")
        secret   = enc_cfg.get("secret", "")

        # ── AES-CBC ──────────────────────────────────────────
        if "CBC" in mode_str:
            key_len        = 16 if "128" in mode_str else 32
            key            = self._decode_key(secret, encoding, key_len)
            iv, prepend    = self._resolve_iv(enc_cfg, 16)

            padder  = crypto_padding.PKCS7(128).padder()
            padded  = padder.update(plaintext) + padder.finalize()
            cipher  = Cipher(algorithms.AES(key), modes.CBC(iv))
            enc     = cipher.encryptor()
            ct      = enc.update(padded) + enc.finalize()
            return (iv + ct) if prepend else ct

        # ── AES-GCM ──────────────────────────────────────────
        if "GCM" in mode_str:
            key_len      = 16 if "128" in mode_str else 32
            key          = self._decode_key(secret, encoding, key_len)
            nonce, prepend = self._resolve_iv(enc_cfg, 12)

            aesgcm = AESGCM(key)
            ct     = aesgcm.encrypt(nonce, plaintext, None)  # tag appended by library
            return (nonce + ct) if prepend else ct

        # ── ChaCha20-Poly1305 ────────────────────────────────
        if "ChaCha20" in mode_str:
            key            = self._decode_key(secret, encoding, 32)
            nonce, prepend = self._resolve_iv(enc_cfg, 16)

            chacha = ChaCha20Poly1305(key)
            ct     = chacha.encrypt(nonce, plaintext, None)
            return (nonce + ct) if prepend else ct

        # Unknown mode — pass through (shouldn't happen with controlled combo)
        return plaintext