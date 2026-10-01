"""Minimal DGpy palette, applied to DGpy widgets only."""

BACKGROUND = "#25282d"
FOREGROUND = "#eeeeee"
ACCENT = "#68b7ce"

STYLESHEET = f"""
QDialog {{ background-color: {BACKGROUND}; color: {FOREGROUND}; }}
QLabel {{ color: {FOREGROUND}; }}
QPushButton {{ background-color: #373d45; color: {FOREGROUND};
               border: 1px solid {ACCENT}; padding: 6px 18px; }}
"""
