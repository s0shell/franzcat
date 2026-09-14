"""
FranzCat - Kafka Testing Tool
Requires: pip install PyQt6 urllib3 requests confluent-kafka fastavro
"""

import sys

from PyQt6.QtWidgets import (
    QApplication
)

from styles.theme_manager import load_stylesheet
from ui.main_window import MainWindow



# ─────────────────────────────────────────────────────────
#  Entry point
# ─────────────────────────────────────────────────────────

def main():
    app = QApplication(sys.argv)
    app.setStyleSheet(load_stylesheet(dark=True))
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()