"""Tests for marker target discovery and deletion."""

import unittest

from dg_python_scripts.markers import (
    MarkerApplyError,
    apply_delete_plan,
    build_delete_plan,
    can_delete_markers_selection,
    collect_marker_targets,
)


class FakeName:
    def __init__(self, value):
        self.value = value

    def get_value(self):
        return self.value


class PyMarker:
    pass


class PyClip:
    def __init__(self, name, markers=()):
        self.name = FakeName(name)
        self.markers = list(markers)


class PySequence(PyClip):
    pass


class _Container:
    def __init__(self, name, children=()):
        self.name = FakeName(name)
        self.children = list(children)


class PyReel(_Container):
    pass


class PyReelGroup(_Container):
    pass


class PyFolder(_Container):
    pass


class PyLibrary(_Container):
    pass


class PyNode:
    pass


class MarkerTests(unittest.TestCase):
    def test_predicate_accepts_direct_targets_and_supported_root_containers(self):
        self.assertTrue(can_delete_markers_selection((PyClip("A"),)))
        self.assertTrue(can_delete_markers_selection((PySequence("S"),)))
        self.assertTrue(can_delete_markers_selection((PyReel("R"),)))
        self.assertTrue(can_delete_markers_selection((PyFolder("F"),)))
        self.assertTrue(can_delete_markers_selection((PyLibrary("L"),)))
        self.assertFalse(can_delete_markers_selection((PyReelGroup("G"),)))
        self.assertFalse(can_delete_markers_selection((PyNode(),)))

    def test_children_recursion_collects_clip_and_sequence_targets(self):
        clip = PyClip("A")
        sequence = PySequence("S")
        nested = PyFolder(
            "Folder",
            (
                PyReel("Reel", (clip,)),
                PyReelGroup("Group", (PyReel("Nested", (sequence,)),)),
            ),
        )

        self.assertEqual(collect_marker_targets((nested,)), (clip, sequence))

    def test_direct_and_nested_duplicate_target_is_deduplicated(self):
        clip = PyClip("A")
        reel = PyReel("R", (clip,))
        self.assertEqual(collect_marker_targets((clip, reel)), (clip,))

    def test_unsupported_children_are_ignored(self):
        clip = PyClip("A")
        folder = PyFolder("F", (PyNode(), clip))
        self.assertEqual(collect_marker_targets((folder,)), (clip,))

    def test_plan_counts_markers_per_target(self):
        clip = PyClip("A", (PyMarker(), PyMarker()))
        sequence = PySequence("S", (PyMarker(),))
        plan = build_delete_plan((PyReel("R", (clip, sequence)),))

        self.assertEqual(len(plan.targets), 2)
        self.assertEqual(plan.total_markers, 3)
        self.assertEqual(len(plan.marked_targets), 2)

    def test_apply_deletes_and_verifies_readback(self):
        markers = [PyMarker(), PyMarker()]
        clip = PyClip("A", markers)
        plan = build_delete_plan((clip,))

        def delete_marker(marker):
            clip.markers.remove(marker)

        result = apply_delete_plan(plan, delete_marker)

        self.assertEqual(result.deleted, 2)
        self.assertEqual(result.changed_targets, 1)
        self.assertEqual(clip.markers, [])

    def test_apply_reports_incomplete_deletion(self):
        markers = [PyMarker(), PyMarker()]
        clip = PyClip("A", markers)
        plan = build_delete_plan((clip,))

        with self.assertRaises(MarkerApplyError) as ctx:
            apply_delete_plan(plan, lambda marker: None)

        self.assertEqual(ctx.exception.deleted, 0)
        self.assertIn("2 marker(s) remain", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
