"""
FranzCat - Kafka Testing Tool
Requires: pip install PyQt6 urllib3 requests confluent-kafka fastavro
"""

import sys

from PyQt6.QtWidgets import (
    QApplication
)

from services.settings_store import SettingsStore
from styles.theme_manager import load_stylesheet
from ui.main_window import MainWindow
from widgets.log_pane import LogPane



# ─────────────────────────────────────────────────────────
#  Entry point
# ─────────────────────────────────────────────────────────

def main():
    app = QApplication(sys.argv)
    app.setOrganizationName("FranzCat")
    app.setApplicationName("FranzCat")

    store = SettingsStore()
    dark = store.get("window.dark_mode", True)
    dark = dark if isinstance(dark, bool) else True
    app.setStyleSheet(load_stylesheet(dark=dark))
    LogPane.set_dark_mode(dark)

    window = MainWindow(store, dark)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()