"""Read-only About/Diagnostics dialog hosted by Flame's existing Qt app."""

from dgpy.runtime import detect_runtime
from dgpy.version import __version__
from .theme import STYLESHEET


def diagnostics_text() -> str:
    runtime = detect_runtime()
    return (
        f"DGpy {__version__}\n"
        f"Flame: {runtime.flame_version or 'not available'}\n"
        f"Python: {runtime.python_version}\n"
        f"Runtime: {runtime.status}\n"
        "Primary target: Flame 2025.2.7\n"
        "2026+ compatibility: not yet validated"
    )


def show_about_dialog() -> None:
    from PySide6 import QtCore, QtWidgets

    app = QtWidgets.QApplication.instance()
    if app is None:
        raise RuntimeError("DGpy UI requires Flame's running QApplication")
    dialog = QtWidgets.QDialog(app.activeWindow())
    dialog.setWindowTitle("DGpy — About / Diagnostics")
    dialog.setStyleSheet(STYLESHEET)
    layout = QtWidgets.QVBoxLayout(dialog)
    layout.setContentsMargins(20, 20, 20, 20)
    label = QtWidgets.QLabel(diagnostics_text())
    label.setTextFormat(QtCore.Qt.TextFormat.PlainText)
    label.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)
    layout.addWidget(label)
    close = QtWidgets.QPushButton("Close")
    close.clicked.connect(dialog.accept)
    layout.addWidget(close)
    dialog.exec()
