"""DGpy batch Rename dialog."""

from __future__ import annotations

from datetime import datetime

from dg_python_scripts.rename import (
    RenameApplyError,
    ReplacementRule,
    StaleRenameError,
    TemplateError,
    apply_plan,
    build_plan,
)
from .theme import STYLESHEET


def _index_token(digits: int, start: int, step: int) -> str:
    padding = "#" * digits

    if start == 1 and step == 1:
        spec = padding
    else:
        spec = f"{padding}@{start}"
        if step != 1:
            spec += f"{step:+d}"

    return "{index" + (f":{spec}" if spec else "") + "}"


def _representative_row(plan):
    for row in plan.rows:
        if row.status == "ready":
            return row
    for row in plan.rows:
        if row.status != "unsupported":
            return row
    return None


def show_rename_dialog(selection=()) -> None:
    from PySide6 import QtCore, QtWidgets

    app = QtWidgets.QApplication.instance()
    if app is None:
        raise RuntimeError("DGpy UI requires Flame's running QApplication")

    selected = tuple(selection)
    frozen_now = datetime.now().astimezone()

    dialog = QtWidgets.QDialog(app.activeWindow())
    dialog.setWindowTitle("DGpy — Rename")
    dialog.resize(720, 360)
    dialog.setMinimumWidth(620)
    dialog.setStyleSheet(STYLESHEET)

    root = QtWidgets.QVBoxLayout(dialog)
    root.setContentsMargins(24, 22, 24, 22)
    root.setSpacing(16)

    def section_label(text: str):
        label = QtWidgets.QLabel(text)
        label.setObjectName("sectionLabel")
        return label

    # Pattern
    root.addWidget(section_label("Pattern"))

    pattern_row = QtWidgets.QHBoxLayout()
    pattern_row.setSpacing(8)

    template_edit = QtWidgets.QLineEdit("{name}")
    template_edit.setPlaceholderText("Rename pattern")
    template_edit.setClearButtonEnabled(True)
    pattern_row.addWidget(template_edit, 1)

    name_button = QtWidgets.QToolButton()
    name_button.setText("Name")

    date_button = QtWidgets.QToolButton()
    date_button.setText("Date")

    index_button = QtWidgets.QToolButton()
    index_button.setText("Index")

    for button in (name_button, date_button, index_button):
        button.setObjectName("tokenButton")
        button.setToolButtonStyle(QtCore.Qt.ToolButtonStyle.ToolButtonTextOnly)
        button.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
        pattern_row.addWidget(button)

    root.addLayout(pattern_row)

    # Find / Replace rules
    replace_header = QtWidgets.QHBoxLayout()
    replace_header.setContentsMargins(0, 0, 0, 0)
    replace_header.setSpacing(8)
    replace_header.addWidget(section_label("Find & Replace"))
    replace_header.addStretch(1)

    add_rule_button = QtWidgets.QToolButton()
    add_rule_button.setObjectName("addRuleButton")
    add_rule_button.setText("+")
    add_rule_button.setToolTip("Add replacement rule")
    add_rule_button.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
    replace_header.addWidget(add_rule_button)
    root.addLayout(replace_header)

    replacement_rows_layout = QtWidgets.QVBoxLayout()
    replacement_rows_layout.setSpacing(8)
    root.addLayout(replacement_rows_layout)

    replacement_rows: list[dict[str, object]] = []
    state = {"plan": None}

    def current_rules() -> tuple[ReplacementRule, ...]:
        return tuple(
            ReplacementRule(
                row["find"].text(),
                row["replace"].text(),
            )
            for row in replacement_rows
        )

    def schedule_resize() -> None:
        QtCore.QTimer.singleShot(0, dialog.adjustSize)

    def remove_rule(row) -> None:
        if row not in replacement_rows or len(replacement_rows) <= 1:
            return
        replacement_rows.remove(row)
        row["widget"].deleteLater()
        refresh_preview()
        schedule_resize()

    def add_rule(find_text: str = "", replace_text: str = "") -> None:
        row_widget = QtWidgets.QWidget()
        row_layout = QtWidgets.QHBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(10)

        find_edit = QtWidgets.QLineEdit(find_text)
        find_edit.setPlaceholderText("Find")
        find_edit.setClearButtonEnabled(True)

        arrow_label = QtWidgets.QLabel("→")
        arrow_label.setObjectName("arrowLabel")
        arrow_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

        replace_edit = QtWidgets.QLineEdit(replace_text)
        replace_edit.setPlaceholderText("Replace with")
        replace_edit.setClearButtonEnabled(True)

        remove_button = QtWidgets.QToolButton()
        remove_button.setObjectName("removeRuleButton")
        remove_button.setText("×")
        remove_button.setToolTip("Remove replacement rule")
        remove_button.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)

        row = {
            "widget": row_widget,
            "find": find_edit,
            "replace": replace_edit,
            "remove": remove_button,
        }
        replacement_rows.append(row)

        row_layout.addWidget(find_edit, 1)
        row_layout.addWidget(arrow_label)
        row_layout.addWidget(replace_edit, 1)
        row_layout.addWidget(remove_button)

        replacement_rows_layout.addWidget(row_widget)

        # The first rule always remains available. Additional rules can be removed.
        remove_button.setVisible(len(replacement_rows) > 1)
        find_edit.textChanged.connect(refresh_preview)
        replace_edit.textChanged.connect(refresh_preview)
        remove_button.clicked.connect(lambda checked=False, value=row: remove_rule(value))

        refresh_preview()
        schedule_resize()

    # Preview label follows the same hierarchy as Pattern / Find & Replace.
    root.addWidget(section_label("Preview"))

    preview_card = QtWidgets.QFrame()
    preview_card.setObjectName("previewCard")
    preview_layout = QtWidgets.QVBoxLayout(preview_card)
    preview_layout.setContentsMargins(16, 12, 16, 12)
    preview_layout.setSpacing(6)

    current_preview = QtWidgets.QLabel()
    current_preview.setObjectName("previewName")
    current_preview.setTextInteractionFlags(
        QtCore.Qt.TextInteractionFlag.TextSelectableByMouse
    )
    preview_layout.addWidget(current_preview)

    new_preview = QtWidgets.QLabel()
    new_preview.setObjectName("previewNameNew")
    new_preview.setTextInteractionFlags(
        QtCore.Qt.TextInteractionFlag.TextSelectableByMouse
    )
    preview_layout.addWidget(new_preview)

    root.addWidget(preview_card)

    error_label = QtWidgets.QLabel()
    error_label.setWordWrap(True)
    error_label.setObjectName("errorLabel")
    root.addWidget(error_label)

    footer = QtWidgets.QHBoxLayout()
    footer.setSpacing(10)

    summary_label = QtWidgets.QLabel()
    summary_label.setObjectName("summaryLabel")
    footer.addWidget(summary_label)
    footer.addStretch(1)

    cancel_button = QtWidgets.QPushButton("Cancel")
    cancel_button.setObjectName("secondaryButton")
    cancel_button.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)

    rename_button = QtWidgets.QPushButton("Rename")
    rename_button.setObjectName("primaryButton")
    rename_button.setDefault(True)
    rename_button.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)

    footer.addWidget(cancel_button)
    footer.addWidget(rename_button)
    root.addLayout(footer)

    def insert_token(token: str) -> None:
        template_edit.insert(token)
        template_edit.setFocus()

    def add_menu_item(menu, label: str, token: str) -> None:
        action = menu.addAction(label)
        action.triggered.connect(
            lambda checked=False, value=token: insert_token(value)
        )

    name_button.clicked.connect(lambda: insert_token("{name}"))

    date_menu = QtWidgets.QMenu(date_button)
    add_menu_item(date_menu, "YYYYMMDD  ·  20261002", "{date:%Y%m%d}")
    add_menu_item(date_menu, "YYYY-MM-DD  ·  2026-10-02", "{date:%Y-%m-%d}")
    add_menu_item(date_menu, "YYMMDD  ·  261002", "{date:%y%m%d}")
    date_button.setMenu(date_menu)
    date_button.setPopupMode(
        QtWidgets.QToolButton.ToolButtonPopupMode.InstantPopup
    )

    index_menu = QtWidgets.QMenu(index_button)
    add_menu_item(index_menu, "1, 2, 3…", "{index}")
    add_menu_item(index_menu, "01, 02, 03…", "{index:##}")
    add_menu_item(index_menu, "001, 002, 003…", "{index:###}")
    add_menu_item(index_menu, "0001, 0002, 0003…", "{index:####}")
    index_menu.addSeparator()
    custom_index_action = index_menu.addAction("Custom…")
    index_button.setMenu(index_menu)
    index_button.setPopupMode(
        QtWidgets.QToolButton.ToolButtonPopupMode.InstantPopup
    )

    def insert_custom_index() -> None:
        helper = QtWidgets.QDialog(dialog)
        helper.setWindowTitle("Index Token")
        helper.setStyleSheet(STYLESHEET)
        helper.resize(360, 210)

        helper_layout = QtWidgets.QVBoxLayout(helper)
        helper_layout.setContentsMargins(20, 18, 20, 18)
        helper_layout.setSpacing(12)

        helper_form = QtWidgets.QFormLayout()
        helper_form.setSpacing(10)

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
        for button in helper_buttons.buttons():
            button.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
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

    custom_index_action.triggered.connect(insert_custom_index)

    def refresh_preview() -> None:
        try:
            plan = build_plan(
                selected,
                template_edit.text(),
                now=frozen_now,
                replacements=current_rules(),
            )
        except TemplateError as error:
            state["plan"] = None
            current_preview.setText("—")
            new_preview.setText("—")
            error_label.setText(str(error))
            summary_label.setText("")
            rename_button.setEnabled(False)
            return

        state["plan"] = plan
        error_label.setText("")

        changes = sum(row.status == "ready" for row in plan.rows)
        unsupported = sum(row.status == "unsupported" for row in plan.rows)
        representative = _representative_row(plan)

        if representative is None:
            current_preview.setText("No renameable items")
            new_preview.setText("—")
        else:
            current_preview.setText(representative.original_name or "")
            new_preview.setText(representative.new_name or "")

        item_count = len(plan.rows)
        item_label = "item" if item_count == 1 else "items"
        change_label = "change" if changes == 1 else "changes"
        parts = [f"{item_count} {item_label}", f"{changes} {change_label}"]
        if unsupported:
            parts.append(f"{unsupported} unsupported")
        summary_label.setText("  •  ".join(parts))

        rename_button.setEnabled(bool(plan.ready_rows))

    def apply_current_plan() -> None:
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
    add_rule_button.clicked.connect(lambda: add_rule())
    cancel_button.clicked.connect(dialog.reject)
    rename_button.clicked.connect(apply_current_plan)

    add_rule()
    refresh_preview()
    template_edit.setFocus()
    dialog.exec()
