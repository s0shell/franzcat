from pathlib import Path
from .themes import DARK_THEME, LIGHT_THEME

def load_stylesheet(dark=True):
    theme = DARK_THEME if dark else LIGHT_THEME

    qss = Path(__file__).with_name("stylesheet.qss").read_text()

    return qss.format(**theme)