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


def _index_token(digits: int, start: int, step: int) -> str:
    padding = "#" * digits

    if start == 1 and step == 1:
        spec = padding
    else:
        spec = f"{padding}@{start}"
        if step != 1:
            spec += f"{step:+d}"

    return "{index" + (f":{spec}" if spec else "") + "}"


def show_rename_dialog(selection=()) -> None:
    from PySide6 import QtCore, QtWidgets

    app = QtWidgets.QApplication.instance()
    if app is None:
        raise RuntimeError("DGpy UI requires Flame's running QApplication")

    selected = tuple(selection)
    frozen_now = datetime.now().astimezone()

    dialog = QtWidgets.QDialog(app.activeWindow())
    dialog.setWindowTitle("DGpy — Rename")
    dialog.resize(820, 560)
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

    token_row = QtWidgets.QHBoxLayout()
    token_row.setSpacing(6)
    token_row.addWidget(QtWidgets.QLabel("Insert token:"))

    name_button = QtWidgets.QPushButton("Name")
    date_button = QtWidgets.QPushButton("Date")
    index_button = QtWidgets.QPushButton("Index")
    token_row.addWidget(name_button)
    token_row.addWidget(date_button)
    token_row.addWidget(index_button)
    token_row.addStretch(1)
    root.addLayout(token_row)

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

    def insert_token(token: str) -> None:
        template_edit.insert(token)
        template_edit.setFocus()

    def add_menu_item(menu, label: str, token: str) -> None:
        action = menu.addAction(label)
        action.triggered.connect(
            lambda checked=False, value=token: insert_token(value)
        )

    date_menu = QtWidgets.QMenu(date_button)
    add_menu_item(date_menu, "YYYYMMDD  (20261002)", "{date:%Y%m%d}")
    add_menu_item(date_menu, "YYYY-MM-DD  (2026-10-02)", "{date:%Y-%m-%d}")
    add_menu_item(date_menu, "YYMMDD  (261002)", "{date:%y%m%d}")
    date_button.setMenu(date_menu)

    index_menu = QtWidgets.QMenu(index_button)
    add_menu_item(index_menu, "1, 2, 3…", "{index}")
    add_menu_item(index_menu, "01, 02, 03…", "{index:##}")
    add_menu_item(index_menu, "001, 002, 003…", "{index:###}")
    add_menu_item(index_menu, "0001, 0002, 0003…", "{index:####}")
    index_menu.addSeparator()
    custom_index_action = index_menu.addAction("Custom…")
    index_button.setMenu(index_menu)

    def insert_custom_index() -> None:
        helper = QtWidgets.QDialog(dialog)
        helper.setWindowTitle("Index Token")
        helper.setStyleSheet(STYLESHEET)

        helper_layout = QtWidgets.QVBoxLayout(helper)
        helper_form = QtWidgets.QFormLayout()

        digits_spin = QtWidgets.QSpinBox()
        digits_spin.setRange(0, 12)
        digits_spin.setValue(3)
        digits_spin.setSpecialValueText("No padding")

        start_spin = QtWidgets.QSpinBox()
        start_spin.setRange(-999999, 999999)
        start_spin.setValue(1)

        step_spin = QtWidgets.QSpinBox()
        step_spin.setRange(-999999, 999999)
        step_spin.setValue(1)

        helper_form.addRow("Digits", digits_spin)
        helper_form.addRow("Start", start_spin)
        helper_form.addRow("Step", step_spin)
        helper_layout.addLayout(helper_form)

        token_preview = QtWidgets.QLineEdit()
        token_preview.setReadOnly(True)
        helper_layout.addWidget(token_preview)

        helper_buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok
            | QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )
        helper_layout.addWidget(helper_buttons)

        def refresh_index_token() -> None:
            token_preview.setText(
                _index_token(
                    digits_spin.value(),
                    start_spin.value(),
                    step_spin.value(),
                )
            )

        digits_spin.valueChanged.connect(refresh_index_token)
        start_spin.valueChanged.connect(refresh_index_token)
        step_spin.valueChanged.connect(refresh_index_token)
        helper_buttons.accepted.connect(helper.accept)
        helper_buttons.rejected.connect(helper.reject)
        refresh_index_token()

        if helper.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            insert_token(token_preview.text())

    name_button.clicked.connect(lambda: insert_token("{name}"))
    custom_index_action.triggered.connect(insert_custom_index)

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
