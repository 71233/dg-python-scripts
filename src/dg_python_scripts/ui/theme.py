"""Minimal DGpy palette, applied to DGpy widgets only."""

BACKGROUND = "#25282d"
FOREGROUND = "#eeeeee"
ACCENT = "#68b7ce"

STYLESHEET = f"""
QDialog {{ background-color: {BACKGROUND}; color: {FOREGROUND}; }}
QLabel {{ color: {FOREGROUND}; }}
QPushButton {{ background-color: #373d45; color: {FOREGROUND};
               border: 1px solid {ACCENT}; padding: 6px 18px; }}
QLineEdit, QTableWidget {{ background-color: #1f2227; color: {FOREGROUND};
                           border: 1px solid #4b525c; }}
QHeaderView::section {{ background-color: #373d45; color: {FOREGROUND};
                        border: 0; padding: 5px; }}
QLabel#errorLabel {{ color: #ff8f8f; }}
"""
