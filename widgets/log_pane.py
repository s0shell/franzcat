from PyQt6.QtGui import QFont, QTextCursor
from PyQt6.QtWidgets import QTextEdit
from styles.themes import LOG_COLORS_DARK, LOG_COLORS_LIGHT

class LogPane(QTextEdit):
    """Read-only output pane with colour helpers."""

    COLORS = LOG_COLORS_DARK

    @classmethod
    def set_dark_mode(cls, dark: bool) -> None:
        cls.COLORS = LOG_COLORS_DARK if dark else LOG_COLORS_LIGHT

    def __init__(self, placeholder="// output will appear here", parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setPlaceholderText(placeholder)
        self.setFont(QFont("Courier New", 11))
        self.setMinimumHeight(40)

    def append_line(self, text: str, kind: str = "data"):
        color = self.COLORS.get(kind, self.COLORS["data"])
        html = f'<span style="color:{color};">{text}</span>'
        self.append(html)
        self.moveCursor(QTextCursor.MoveOperation.End)

    def clear_log(self):
        self.clear()