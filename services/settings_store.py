"""
Persistent application settings (JSON, stored in the per-user config dir).

Panels expose a ``settings_widgets()`` dict (key -> widget); this module
collects/applies their values and handles reading/writing the file.
Secrets (e.g. the key passphrase) are intentionally never registered.
"""

import json
import os
import tempfile
from pathlib import Path

from PyQt6.QtCore import QStandardPaths, QTimer
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QLineEdit, QSpinBox, QTextEdit
)

SETTINGS_VERSION = 1
SAVE_DEBOUNCE_MS = 400


def settings_path() -> Path:
    """Per-user settings file; FRANZCAT_CONFIG overrides the location."""
    override = os.environ.get("FRANZCAT_CONFIG")
    if override:
        return Path(override).expanduser()
    base = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppConfigLocation)
    return Path(base) / "settings.json"


# ── widget <-> value helpers ─────────────────────────────────

def read_widget(w):
    if isinstance(w, QCheckBox):
        return w.isChecked()
    if isinstance(w, QSpinBox):
        return w.value()
    if isinstance(w, QComboBox):
        return w.currentText()
    if isinstance(w, QLineEdit):
        return w.text()
    if isinstance(w, QTextEdit):
        return w.toPlainText()
    raise TypeError(f"unsupported widget type: {type(w).__name__}")


def write_widget(w, value) -> None:
    """Apply a stored value; invalid values are ignored (default stays)."""
    if isinstance(w, QCheckBox):
        if isinstance(value, bool):
            w.setChecked(value)
    elif isinstance(w, QSpinBox):
        if isinstance(value, int) and not isinstance(value, bool):
            w.setValue(max(w.minimum(), min(w.maximum(), value)))
    elif isinstance(w, QComboBox):
        idx = w.findText(value) if isinstance(value, str) else -1
        if idx >= 0:
            w.setCurrentIndex(idx)
    elif isinstance(w, QLineEdit):
        if isinstance(value, str):
            w.setText(value)
    elif isinstance(w, QTextEdit):
        if isinstance(value, str):
            w.setPlainText(value)


def change_signal(w):
    if isinstance(w, QCheckBox):
        return w.toggled
    if isinstance(w, QSpinBox):
        return w.valueChanged
    if isinstance(w, QComboBox):
        return w.currentTextChanged
    return w.textChanged


class SettingsStore:
    """Registry of settings widgets plus debounced JSON persistence."""

    def __init__(self, path: Path | None = None):
        self._path = path or settings_path()
        self._widgets: dict[str, object] = {}
        self._extra: dict[str, object] = {}     # non-widget values (theme, geometry)
        self._data: dict = self._read_file()
        self._timer = QTimer()
        self._timer.setSingleShot(True)
        self._timer.setInterval(SAVE_DEBOUNCE_MS)
        self._timer.timeout.connect(self.save)

    @property
    def path(self) -> Path:
        return self._path

    # ── registration ─────────────────────────────────────────

    def register(self, prefix: str, widgets: dict) -> None:
        """Register widgets as '<prefix>.<key>' and restore their stored values."""
        for key, w in widgets.items():
            self._widgets[f"{prefix}.{key}"] = w

    def restore(self) -> None:
        """Apply stored values to all registered widgets, then watch for changes."""
        for name, w in self._widgets.items():
            if name in self._data:
                write_widget(w, self._data[name])
        # connect only after restoring so loading does not trigger saves
        for w in self._widgets.values():
            change_signal(w).connect(self.schedule_save)

    # ── plain (non-widget) values ────────────────────────────

    def get(self, name: str, default=None):
        return self._data.get(name, default)

    def set(self, name: str, value) -> None:
        self._extra[name] = value
        self.schedule_save()

    # ── persistence ──────────────────────────────────────────

    def schedule_save(self, *_):
        self._timer.start()

    def save(self) -> None:
        self._timer.stop()
        data = dict(self._data)
        data.update(self._extra)
        data.update({name: read_widget(w) for name, w in self._widgets.items()})
        self._data = data
        payload = {"version": SETTINGS_VERSION, "values": data}
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            # write to a temp file, then atomically replace
            fd, tmp = tempfile.mkstemp(dir=self._path.parent, suffix=".tmp")
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, ensure_ascii=False)
            os.replace(tmp, self._path)
        except OSError as exc:
            print(f"warning: could not save settings to {self._path}: {exc}")

    def _read_file(self) -> dict:
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            values = raw.get("values")
            return values if isinstance(values, dict) else {}
        except (OSError, ValueError, AttributeError):
            return {}
