"""G2-only selection previews for the *existing* built-in DGpy actions.

This module does not authorize action execution, inspect Flame object
capabilities, register Hooks, load Qt, or change production state.
Its static profiles are reviewed against existing registrations by tests.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType

from .selection_contract import (
    HOOK_TO_CONTEXT,
    SelectionPolicy,
    inspect_hook_selection,
)


@dataclass(frozen=True)
class BuiltinSelectionProfile:
    """Conservative structural policy, not an authenticated host API type."""

    contexts: frozenset[str]
    policy: SelectionPolicy
    candidate_type_hints: frozenset[str] | None = None
    requires_host_capability_check: bool = False


# These action IDs/contexts come from the existing ActionRegistry registrations.
# Do not use this static table as a second registry or dispatch table.
# Rename capability is dynamic (name.get_value/set_value), so type names
# cannot establish rename availability. Marker type names are only hints.
BUILTIN_SELECTION_PROFILES = MappingProxyType({
    "dgpy.about": BuiltinSelectionProfile(
        contexts=frozenset({"main_menu"}),
        policy=SelectionPolicy(),
    ),
    "dgpy.rename": BuiltinSelectionProfile(
        contexts=frozenset({"media_panel", "timeline", "batch", "action"}),
        policy=SelectionPolicy(min_items=1),
        requires_host_capability_check=True,
    ),
    "dgpy.delete_markers": BuiltinSelectionProfile(
        contexts=frozenset({"media_panel"}),
        policy=SelectionPolicy(min_items=1),
        candidate_type_hints=frozenset({"PyClip", "PySequence", "PyReel"}),
        requires_host_capability_check=True,
    ),
})


@dataclass(frozen=True)
class BuiltinSelectionReview:
    """No object refs or private names; status never means 'execute'."""

    findings: tuple[str, ...]
    context: str | None = None
    phase: str | None = None
    selection_count: int = 0
    candidate_type_hint_count: int | None = None
    requires_host_capability_check: bool = False

    @property
    def status(self) -> str:
        return "BLOCKED" if self.findings else "PREVIEW_ONLY"

    @property
    def next_step(self) -> str:
        return "MANUAL_RECONCILIATION" if self.findings else "NO_CHANGE"


def _blocked(code: str, context: str | None = None,
             phase: str | None = None) -> BuiltinSelectionReview:
    return BuiltinSelectionReview((code,), context, phase)


def inspect_builtin_selection(
    *,
    action_id: object,
    hook_name: object,
    phase: object,
    selection: object,
) -> BuiltinSelectionReview:
    """Review one callback's structure against a known built-in action.

    This cannot prove that a PyClip name is a Flame Clip, that an object
    exposes a writable name, or that markers exist or may be deleted.
    A matched result is *still not* permission to call Action.execute.
    """
    if type(action_id) is not str or action_id not in BUILTIN_SELECTION_PROFILES:
        return _blocked("unsupported_builtin_action")
    if type(hook_name) is not str or hook_name not in HOOK_TO_CONTEXT:
        return _blocked("unsupported_hook")
    profile = BUILTIN_SELECTION_PROFILES[action_id]
    context = HOOK_TO_CONTEXT[hook_name]
    # Reject an inapplicable context *before* inspecting host objects.
    if context not in profile.contexts:
        return _blocked("action_context_mismatch", context)

    basic = inspect_hook_selection(
        hook_name=hook_name,
        phase=phase,
        selection=selection,
        policy=profile.policy,
        expected_context=context,
    )
    if basic.findings:
        return BuiltinSelectionReview(basic.findings, basic.context, basic.phase)

    if profile.candidate_type_hints is None:
        # About: Selection is ignored. Rename: a host capability test is
        # essential, and this module deliberately does not call it.
        count = 0 if action_id == "dgpy.about" else None
    else:
        # This is only a hint. It deliberately does not read .markers, .name,
        # .selected, or any object method. Mixed types are not dropped.
        count = sum(
            type.__getattribute__(type(item), "__name__")
            in profile.candidate_type_hints
            for item in basic.items
        )
        if count == 0:
            return _blocked("no_matching_type_hint", context, basic.phase)

    return BuiltinSelectionReview(
        (), basic.context, basic.phase, basic.count, count,
        profile.requires_host_capability_check,
    )
