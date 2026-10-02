"""DGpy batch Rename dialog."""

from __future__ import annotations

from datetime import datetime

from dg_python_scripts.rename import (
    RenameApplyError,
    StaleRenameError,
    TemplateError,
    apply_plan,
    build_plan,
)
from .theme import STYLESHEET


_STATUS_LABELS = {
    "ready": "Ready",
    "unchanged": "Unchanged",
    "unsupported": "Unsupported",
}


def show_rename_dialog(selection=()) -> None:
    from PySide6 import QtCore, QtWidgets

    app = QtWidgets.QApplication.instance()
    if app is None:
        raise RuntimeError("DGpy UI requires Flame's running QApplication")

    selected = tuple(selection)
    frozen_now = datetime.now().astimezone()

    dialog = QtWidgets.QDialog(app.activeWindow())
    dialog.setWindowTitle("DGpy — Rename")
    dialog.resize(820, 520)
    dialog.setStyleSheet(STYLESHEET)

    root = QtWidgets.QVBoxLayout(dialog)
    root.setContentsMargins(18, 18, 18, 18)
    root.setSpacing(10)

    form = QtWidgets.QFormLayout()
    template_edit = QtWidgets.QLineEdit("{name}")
    find_edit = QtWidgets.QLineEdit()
    replace_edit = QtWidgets.QLineEdit()
    form.addRow("Template", template_edit)
    form.addRow("Find", find_edit)
    form.addRow("Replace", replace_edit)
    root.addLayout(form)

    help_label = QtWidgets.QLabel(
        "Tokens: {name}   {date:%Y%m%d}   "
        "{index}   {index:###}   {index:###@8-2}"
    )
    help_label.setTextInteractionFlags(
        QtCore.Qt.TextInteractionFlag.TextSelectableByMouse
    )
    root.addWidget(help_label)

    error_label = QtWidgets.QLabel()
    error_label.setWordWrap(True)
    error_label.setObjectName("errorLabel")
    root.addWidget(error_label)

    table = QtWidgets.QTableWidget(0, 4)
    table.setHorizontalHeaderLabels(("Status", "Type", "Current", "New"))
    table.setEditTriggers(
        QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers
    )
    table.setSelectionBehavior(
        QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows
    )
    table.verticalHeader().setVisible(False)
    header = table.horizontalHeader()
    header.setSectionResizeMode(
        0, QtWidgets.QHeaderView.ResizeMode.ResizeToContents
    )
    header.setSectionResizeMode(
        1, QtWidgets.QHeaderView.ResizeMode.ResizeToContents
    )
    header.setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeMode.Stretch)
    header.setSectionResizeMode(3, QtWidgets.QHeaderView.ResizeMode.Stretch)
    root.addWidget(table, 1)

    buttons = QtWidgets.QHBoxLayout()
    buttons.addStretch(1)
    cancel_button = QtWidgets.QPushButton("Cancel")
    rename_button = QtWidgets.QPushButton("Rename")
    rename_button.setDefault(True)
    buttons.addWidget(cancel_button)
    buttons.addWidget(rename_button)
    root.addLayout(buttons)

    state = {"plan": None}

    def set_item(row: int, column: int, text: str, tooltip: str | None = None):
        item = QtWidgets.QTableWidgetItem(text)
        if tooltip:
            item.setToolTip(tooltip)
        table.setItem(row, column, item)

    def refresh_preview():
        try:
            plan = build_plan(
                selected,
                template_edit.text(),
                find_edit.text(),
                replace_edit.text(),
                now=frozen_now,
            )
        except TemplateError as error:
            state["plan"] = None
            error_label.setText(str(error))
            table.setRowCount(0)
            rename_button.setEnabled(False)
            return

        state["plan"] = plan
        error_label.setText("")
        table.setRowCount(len(plan.rows))

        for row_index, row in enumerate(plan.rows):
            set_item(
                row_index,
                0,
                _STATUS_LABELS.get(row.status, row.status),
                row.reason,
            )
            set_item(row_index, 1, row.type_name)
            set_item(row_index, 2, row.original_name or "")
            set_item(row_index, 3, row.new_name or "")

        rename_button.setEnabled(bool(plan.ready_rows))

    def apply_current_plan():
        plan = state["plan"]
        if plan is None:
            return
        try:
            apply_plan(plan)
        except (StaleRenameError, RenameApplyError) as error:
            QtWidgets.QMessageBox.critical(
                dialog,
                "DGpy Rename",
                str(error),
            )
            refresh_preview()
            return
        dialog.accept()

    template_edit.textChanged.connect(refresh_preview)
    find_edit.textChanged.connect(refresh_preview)
    replace_edit.textChanged.connect(refresh_preview)
    cancel_button.clicked.connect(dialog.reject)
    rename_button.clicked.connect(apply_current_plan)

    refresh_preview()
    dialog.exec()
