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
    def __init__(self, name, clips=(), sequences=()):
        self.name = FakeName(name)
        self.clips = list(clips)
        self.sequences = list(sequences)


class PyReel(_Container):
    pass


class PyFolder(_Container):
    pass


class PyLibrary(_Container):
    pass


class PyReelGroup(_Container):
    pass


class PyNode:
    pass


class MarkerTests(unittest.TestCase):
    def test_predicate_accepts_direct_targets_and_supported_parents(self):
        self.assertTrue(can_delete_markers_selection((PyClip("A"),)))
        self.assertTrue(can_delete_markers_selection((PySequence("S"),)))
        self.assertTrue(can_delete_markers_selection((PyReel("R"),)))
        self.assertFalse(can_delete_markers_selection((PyFolder("F"),)))
        self.assertFalse(can_delete_markers_selection((PyLibrary("L"),)))
        self.assertFalse(can_delete_markers_selection((PyReelGroup("G"),)))
        self.assertFalse(can_delete_markers_selection((PyNode(),)))

    def test_parent_collects_only_direct_clips_and_sequences(self):
        clip = PyClip("A")
        sequence = PySequence("S")
        parent = PyReel("Reel", clips=(clip,), sequences=(sequence,))

        self.assertEqual(collect_marker_targets((parent,)), (clip, sequence))

    def test_parent_does_not_recurse_into_nested_containers(self):
        nested_clip = PyClip("Nested")
        nested_reel = PyReel("Nested Reel", clips=(nested_clip,))
        folder = PyFolder("Folder")
        folder.reels = [nested_reel]

        self.assertEqual(collect_marker_targets((folder,)), ())

    def test_direct_and_parent_duplicate_target_is_deduplicated(self):
        clip = PyClip("A")
        reel = PyReel("R", clips=(clip,))
        self.assertEqual(collect_marker_targets((clip, reel)), (clip,))

    def test_duplicate_between_clips_and_sequences_is_deduplicated(self):
        sequence = PySequence("S")
        reel = PyReel("R", clips=(sequence,), sequences=(sequence,))
        self.assertEqual(collect_marker_targets((reel,)), (sequence,))

    def test_plan_counts_markers_per_target(self):
        clip = PyClip("A", (PyMarker(), PyMarker()))
        sequence = PySequence("S", (PyMarker(),))
        plan = build_delete_plan(
            (PyReel("R", clips=(clip,), sequences=(sequence,)),)
        )

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
