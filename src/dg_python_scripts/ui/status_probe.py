"""One-shot Status HUD probe dialog."""

from concurrent.futures import ThreadPoolExecutor

from dg_python_scripts.status.probe import (
    collect_flame_probe,
    collect_system_probe,
    format_probe_report,
)


def show_status_probe_dialog() -> None:
    from PySide6 import QtCore, QtGui, QtWidgets

    from .theme import BORDER, FIELD, FOREGROUND, MUTED, STYLESHEET

    app = QtWidgets.QApplication.instance()
    if app is None:
        raise RuntimeError("DGpy UI requires Flame's running QApplication")

    flame_probe = collect_flame_probe()
    project_name = flame_probe.project.value
    if project_name == "—":
        project_name = ""

    class StatusProbeDialog(QtWidgets.QDialog):
        def __init__(self, parent=None):
            super().__init__(parent)
            self.setWindowTitle("DGpy — Status HUD Probe")
            self.resize(760, 560)
            self.setStyleSheet(
                STYLESHEET
                + f"""
                QPlainTextEdit {{
                    background-color: {FIELD};
                    color: {FOREGROUND};
                    border: 1px solid {BORDER};
                    border-radius: 6px;
                    padding: 10px;
                }}
                QLabel#probeHint {{
                    color: {MUTED};
                    font-size: 12px;
                }}
                """
            )

            layout = QtWidgets.QVBoxLayout(self)
            layout.setContentsMargins(20, 20, 20, 20)
            layout.setSpacing(10)

            hint = QtWidgets.QLabel(
                "One-shot diagnostic only. System, storage, and GPU collection "
                "runs off the Flame UI thread."
            )
            hint.setObjectName("probeHint")
            hint.setWordWrap(True)
            layout.addWidget(hint)

            self.output = QtWidgets.QPlainTextEdit()
            self.output.setReadOnly(True)
            self.output.setLineWrapMode(QtWidgets.QPlainTextEdit.LineWrapMode.NoWrap)
            self.output.setFont(
                QtGui.QFontDatabase.systemFont(
                    QtGui.QFontDatabase.SystemFont.FixedFont
                )
            )
            self.output.setPlainText(
                "DGpy Status HUD Probe\n\n"
                "Collecting OS / storage / GPU data..."
            )
            layout.addWidget(self.output, 1)

            buttons = QtWidgets.QHBoxLayout()
            buttons.addStretch(1)

            self.copy_button = QtWidgets.QPushButton("Copy Results")
            self.copy_button.setObjectName("secondaryButton")
            self.copy_button.setEnabled(False)
            self.copy_button.clicked.connect(self._copy_results)
            buttons.addWidget(self.copy_button)

            close_button = QtWidgets.QPushButton("Close")
            close_button.setObjectName("primaryButton")
            close_button.clicked.connect(self.accept)
            buttons.addWidget(close_button)
            layout.addLayout(buttons)

            self._executor = ThreadPoolExecutor(
                max_workers=1,
                thread_name_prefix="dgpy-status-probe",
            )
            self._future = self._executor.submit(
                collect_system_probe,
                project_name,
            )
            self._timer = QtCore.QTimer(self)
            self._timer.setInterval(75)
            self._timer.timeout.connect(self._poll)
            self._timer.start()

        def _poll(self) -> None:
            if not self._future.done():
                return
            self._timer.stop()
            try:
                system_probe = self._future.result()
                report = format_probe_report(flame_probe, system_probe)
            except Exception as error:
                report = (
                    "DGpy Status HUD Probe\n\n"
                    "Probe worker failed unexpectedly:\n"
                    f"{type(error).__name__}: {error}"
                )
            self.output.setPlainText(report)
            self.output.moveCursor(QtGui.QTextCursor.MoveOperation.Start)
            self.copy_button.setEnabled(True)
            self._executor.shutdown(wait=False, cancel_futures=True)
            self._executor = None

        def _copy_results(self) -> None:
            app.clipboard().setText(self.output.toPlainText())

        def closeEvent(self, event) -> None:
            if self._executor is not None:
                self._executor.shutdown(wait=False, cancel_futures=True)
                self._executor = None
            super().closeEvent(event)

    dialog = StatusProbeDialog(app.activeWindow())
    dialog.exec()
