"""DGpy palette and compact UI styling."""

BACKGROUND = "#202328"
SURFACE = "#292d33"
SURFACE_RAISED = "#30353c"
FIELD = "#1b1e22"
BORDER = "#454b54"
FOREGROUND = "#f1f1f1"
MUTED = "#9ea5ae"
ACCENT = "#f28c28"
ACCENT_HOVER = "#ffa13e"
ACCENT_PRESSED = "#d97819"
ERROR = "#ff7d7d"

STYLESHEET = f"""
QDialog {{
    background-color: {BACKGROUND};
    color: {FOREGROUND};
}}

QLabel {{
    color: {FOREGROUND};
}}

QLabel#sectionLabel {{
    color: {MUTED};
    font-size: 12px;
    font-weight: 600;
}}

QLabel#arrowLabel {{
    color: {MUTED};
    font-size: 16px;
}}

QLabel#previewTitle {{
    color: {MUTED};
    font-size: 11px;
    font-weight: 600;
}}

QLabel#previewName {{
    color: {MUTED};
    font-size: 12px;
    font-weight: 400;
}}

QLabel#previewNameNew {{
    color: {FOREGROUND};
    font-size: 16px;
    font-weight: 600;
}}

QLabel#summaryLabel {{
    color: {MUTED};
    font-size: 12px;
}}

QLabel#errorLabel {{
    color: {ERROR};
    font-size: 12px;
}}

QFrame#previewCard {{
    background-color: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 8px;
}}

QLineEdit,
QSpinBox {{
    background-color: {FIELD};
    color: {FOREGROUND};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 7px 9px;
    selection-background-color: {ACCENT};
}}

QLineEdit:focus,
QSpinBox:focus {{
    border: 1px solid {ACCENT};
}}

QPushButton,
QToolButton {{
    background-color: {SURFACE_RAISED};
    color: {FOREGROUND};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 7px 14px;
}}

QToolButton#tokenButton {{
    padding: 6px 11px;
}}

QPushButton:hover,
QToolButton:hover {{
    background-color: #3a4048;
    border-color: #5a626d;
}}

QPushButton:pressed,
QToolButton:pressed {{
    background-color: #272b31;
}}

QPushButton#primaryButton {{
    background-color: {ACCENT};
    color: #171717;
    border-color: {ACCENT};
    font-weight: 600;
    min-width: 84px;
}}

QPushButton#primaryButton:hover {{
    background-color: {ACCENT_HOVER};
    border-color: {ACCENT_HOVER};
}}

QPushButton#primaryButton:pressed {{
    background-color: {ACCENT_PRESSED};
    border-color: {ACCENT_PRESSED};
}}

QPushButton#primaryButton:disabled {{
    background-color: #5b4938;
    color: #9f958c;
    border-color: #5b4938;
}}

QPushButton#secondaryButton {{
    min-width: 84px;
}}

QPushButton:focus,
QToolButton:focus {{
    outline: none;
}}

QMenu {{
    background-color: {SURFACE};
    color: {FOREGROUND};
    border: 1px solid {BORDER};
    padding: 4px;
}}

QMenu::item {{
    padding: 6px 24px 6px 10px;
    border-radius: 4px;
}}

QMenu::item:selected {{
    background-color: {SURFACE_RAISED};
}}

QMenu::separator {{
    height: 1px;
    background: {BORDER};
    margin: 4px 8px;
}}
"""
