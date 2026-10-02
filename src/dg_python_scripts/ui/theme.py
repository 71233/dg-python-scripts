"""Minimal DGpy palette, applied to DGpy widgets only."""

BACKGROUND = "#25282d"
FOREGROUND = "#eeeeee"
ACCENT = "#f28c28"

STYLESHEET = f"""
QDialog {{ background-color: {BACKGROUND}; color: {FOREGROUND}; }}
QLabel {{ color: {FOREGROUND}; }}
QPushButton {{ background-color: #373d45; color: {FOREGROUND};
               border: 1px solid {ACCENT}; padding: 6px 18px; }}
QToolButton {{ background-color: #373d45; color: {FOREGROUND};
               border: 1px solid {ACCENT}; padding: 4px 10px; }}
QPushButton:hover, QToolButton:hover {{ background-color: #434a54; }}
QPushButton:pressed, QToolButton:pressed {{ background-color: #2f343b; }}
QLineEdit, QTableWidget {{ background-color: #1f2227; color: {FOREGROUND};
                           border: 1px solid #4b525c; }}
QLineEdit:focus {{ border: 1px solid {ACCENT}; }}
QHeaderView::section {{ background-color: #373d45; color: {FOREGROUND};
                        border: 0; padding: 5px; }}
QLabel#errorLabel {{ color: #ff8f8f; }}
"""
