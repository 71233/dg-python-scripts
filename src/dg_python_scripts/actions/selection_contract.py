"""Pure, opt-in Flame 2026 Custom UI callback-selection contract.

Only assesses callback arguments. It never imports Flame/Qt, reads global
selection, registers menus, stores snapshots, executes actions, or changes
host state. A PREVIEW_ONLY result is not an execution authorization.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any


# Verified from Flame 2026 Custom UI Actions documentation. These are the
# seven entry points already present in DGpy's thin bootstrap and hooks.py.
HOOK_TO_CONTEXT = MappingProxyType({
    "get_main_menu_custom_ui_actions": "main_menu",
    "get_media_panel_custom_ui_actions": "media_panel",
    "get_mediahub_files_custom_ui_actions": "mediahub_files",
    "get_mediahub_archives_custom_ui_actions": "mediahub_archives",
    "get_timeline_custom_ui_actions": "timeline",
    "get_batch_custom_ui_actions": "batch",
    "get_action_custom_ui_actions": "action",
})
CALLBACK_PHASES = frozenset({"isVisible", "isEnabled", "execute"})
_MAX_ITEMS = 256
_PRIMITIVES = frozenset({
    type(None), bool, int, float, complex, str, bytes, bytearray,
    memoryview, list, tuple, dict, set, frozenset, range,
})


@dataclass(frozen=True)
class SelectionPolicy:
    """Opt-in, action-specific limits; not Flame object authentication.

    The default accepts opaque Python objects, including mixed types.
    When supplied, allowed_type_names matches only type metadata; spoofable
    Python class names must not be mistaken for a trusted Flame type check.
    """

    min_items: int = 0
    max_items: int = _MAX_ITEMS
    allowed_type_names: frozenset[str] | None = None
    allow_mixed_types: bool = True


@dataclass(frozen=True)
class SelectionReview:
    """Sanitized finding. Opaque user objects are intentionally not repr'ed."""

    findings: tuple[str, ...]
    context: str | None = None
    phase: str | None = None
    count: int = 0
    items: tuple[Any, ...] = field(default=(), repr=False, compare=False)

    @property
    def status(self) -> str:
        return "BLOCKED" if self.findings else "PREVIEW_ONLY"

    @property
    def next_step(self) -> str:
        return "MANUAL_RECONCILIATION" if self.findings else "NO_CHANGE"


def _blocked(code: str, context: str | None = None,
             phase: str | None = None) -> SelectionReview:
    return SelectionReview((code,), context, phase)


def _policy_valid(policy: object) -> bool:
    if type(policy) is not SelectionPolicy:
        return False
    if type(policy.min_items) is not int or type(policy.max_items) is not int:
        return False
    if not 0 <= policy.min_items <= policy.max_items <= _MAX_ITEMS:
        return False
    if type(policy.allow_mixed_types) is not bool:
        return False
    allowed = policy.allowed_type_names
    if allowed is None:
        return True
    if type(allowed) is not frozenset or not allowed:
        return False
    return all(type(name) is str and name.isascii() and name.isidentifier()
               and 1 <= len(name) <= 128 for name in allowed)


def selection_item_is_primitive(value: object) -> bool:
    # Read only class metadata, not a Flame object's __class__, __bool__,
    # selected/name properties, or any other instance attribute.
    cls = type(value)
    bases = type.__getattribute__(cls, "__mro__")
    return any(base is primitive for base in bases for primitive in _PRIMITIVES)


def inspect_hook_selection(
    *,
    hook_name: object,
    phase: object,
    selection: object,
    policy: SelectionPolicy = SelectionPolicy(),
    expected_context: str | None = None,
) -> SelectionReview:
    """Review a single callback tuple; never cache or reinterpret targets.

    Autodesk documents a tuple of selected Flame objects passed to
    isVisible/isEnabled/execute. We reject anything else rather than
    consuming unknown iterators or reading a global selection. No claim is
    made that predicate and execute arguments are identical in Flame 2026.
    """
    if type(hook_name) is not str or hook_name not in HOOK_TO_CONTEXT:
        return _blocked("unsupported_hook")
    context = HOOK_TO_CONTEXT[hook_name]
    if type(phase) is not str or phase not in CALLBACK_PHASES:
        return _blocked("unsupported_callback_phase", context)
    if expected_context is not None and (
        type(expected_context) is not str or expected_context != context
    ):
        return _blocked("context_mismatch", context, phase)
    if not _policy_valid(policy):
        return _blocked("invalid_selection_policy", context, phase)
    if type(selection) is not tuple:
        return _blocked("selection_not_plain_tuple", context, phase)
    size = len(selection)
    if size < policy.min_items:
        return _blocked("selection_below_minimum", context, phase)
    if size > policy.max_items:
        return _blocked("selection_above_maximum", context, phase)

    seen_ids: set[int] = set()
    seen_names: set[str] = set()
    for item in selection:
        if selection_item_is_primitive(item):
            return _blocked("invalid_selection_item", context, phase)
        key = id(item)
        if key in seen_ids:
            return _blocked("duplicate_selection_item", context, phase)
        seen_ids.add(key)
        # Class metadata only. No instance properties/methods are accessed.
        cls = type(item)
        name = type.__getattribute__(cls, "__name__")
        if type(name) is not str:
            return _blocked("invalid_type_metadata", context, phase)
        if policy.allowed_type_names is not None and name not in policy.allowed_type_names:
            return _blocked("unsupported_selection_type", context, phase)
        seen_names.add(name)
        if not policy.allow_mixed_types and len(seen_names) > 1:
            return _blocked("mixed_selection_types", context, phase)

    return SelectionReview((), context, phase, size, selection)
