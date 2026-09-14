from PyQt6.QtWidgets import (
    QHBoxLayout, QGridLayout, QLabel, QLineEdit, QPushButton, QFileDialog, QGroupBox, QFrame, QCheckBox
)
class CertPanel(QGroupBox):
    def __init__(self):
        super().__init__("[ mTLS CERTIFICATES ]")
        self._build()

    def _build(self):
        grid = QGridLayout(self)
        grid.setSpacing(8)
        grid.setColumnStretch(1, 1)

        # ── mTLS target toggles ──────────────────────────────
        toggle_row = QHBoxLayout()

        self.chk_mtls_sr = QCheckBox("mTLS  —  Schema Registry")
        self.chk_mtls_sr.setChecked(False)

        self.chk_mtls_broker = QCheckBox("mTLS  —  Kafka Broker")
        self.chk_mtls_broker.setChecked(False)

        self.lbl_mtls_hint = QLabel("enable per target to activate certificate fields below")
        self.lbl_mtls_hint.setObjectName("lbl_status_inf")

        toggle_row.addWidget(self.chk_mtls_sr)
        toggle_row.addSpacing(24)
        toggle_row.addWidget(self.chk_mtls_broker)
        toggle_row.addSpacing(16)
        toggle_row.addWidget(self.lbl_mtls_hint)
        toggle_row.addStretch()

        grid.addLayout(toggle_row, 0, 0, 1, 3)

        # ── Separator ────────────────────────────────────────
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        grid.addWidget(sep, 1, 0, 1, 3)

        # ── Certificate file fields ──────────────────────────
        fields = [
            ("CA Cert",     "ca_cert",     "ca-cert.pem"),
            ("Client Cert", "client_cert", "client-cert.pem"),
            ("Client Key",  "client_key",  "client-key.pem"),
        ]

        self._paths = {}
        self._cert_labels = []
        self._cert_inputs = []
        self._cert_buttons = []

        for i, (label, key, hint) in enumerate(fields):
            row = i + 2
            lbl = QLabel(label)
            lbl.setObjectName("lbl_key")
            inp = QLineEdit()
            inp.setPlaceholderText(hint)
            inp.setObjectName(f"inp_{key}")
            btn = QPushButton("BROWSE")
            btn.setFixedWidth(80)
            btn.clicked.connect(lambda _, k=key: self._browse(k))
            self._paths[key] = inp
            self._cert_labels.append(lbl)
            self._cert_inputs.append(inp)
            self._cert_buttons.append(btn)
            grid.addWidget(lbl, row, 0)
            grid.addWidget(inp, row, 1)
            grid.addWidget(btn, row, 2)

        # ── Key passphrase ───────────────────────────────────
        pass_row = len(fields) + 2
        lbl_pass = QLabel("Key Passphrase")
        lbl_pass.setObjectName("lbl_key")
        self.inp_passphrase = QLineEdit()
        self.inp_passphrase.setPlaceholderText("leave empty if not required")
        self.inp_passphrase.setEchoMode(QLineEdit.EchoMode.Password)
        self._cert_labels.append(lbl_pass)
        self._cert_inputs.append(self.inp_passphrase)
        grid.addWidget(lbl_pass, pass_row, 0)
        grid.addWidget(self.inp_passphrase, pass_row, 1, 1, 2)

        # ── Server cert verification ─────────────────────────
        verify_row = pass_row + 1
        self.chk_verify = QCheckBox("Verify server certificate")
        self.chk_verify.setChecked(True)
        self.lbl_verify_note = QLabel(
            "uncheck to skip CA validation  —  useful for self-signed broker / SR certs"
        )
        self.lbl_verify_note.setObjectName("lbl_status_inf")
        self._cert_labels.append(self.lbl_verify_note)
        grid.addWidget(self.chk_verify, verify_row, 0, 1, 2)
        grid.addWidget(self.lbl_verify_note, verify_row + 1, 0, 1, 3)

        # ── Wire toggles ─────────────────────────────────────
        self.chk_mtls_sr.toggled.connect(self._on_toggle)
        self.chk_mtls_broker.toggled.connect(self._on_toggle)
        self._on_toggle()   # set initial disabled state

    # ── Helpers ──────────────────────────────────────────────

    def _any_mtls_active(self) -> bool:
        return self.chk_mtls_sr.isChecked() or self.chk_mtls_broker.isChecked()

    def _on_toggle(self):
        active = self._any_mtls_active()
        for w in self._cert_inputs + self._cert_buttons + self._cert_labels:
            w.setEnabled(active)
        self.chk_verify.setEnabled(active)
        if active:
            targets = []
            if self.chk_mtls_sr.isChecked():
                targets.append("SR")
            if self.chk_mtls_broker.isChecked():
                targets.append("broker")
            self.lbl_mtls_hint.setText(f"certificates will be applied to: {', '.join(targets)}")
        else:
            self.lbl_mtls_hint.setText("enable per target to activate certificate fields below")

    def _browse(self, key: str):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select file", "", "PEM Files (*.pem *.crt *.key);;All Files (*)"
        )
        if path:
            self._paths[key].setText(path)

    def get_tls_config(self) -> dict:
        """
        Returns per-target TLS config.

        Keys:  'schema_registry'  and  'broker'
        Each value is either None (mTLS disabled for that target)
        or a dict with ca_cert / client_cert / client_key / key_passphrase / verify.
        """
        certs = {
            "ca_cert":        self._paths["ca_cert"].text(),
            "client_cert":    self._paths["client_cert"].text(),
            "client_key":     self._paths["client_key"].text(),
            "key_passphrase": self.inp_passphrase.text(),
            "verify":         self.chk_verify.isChecked(),
        }
        return {
            "schema_registry": certs if self.chk_mtls_sr.isChecked()     else None,
            "broker":          certs if self.chk_mtls_broker.isChecked() else None,
        }