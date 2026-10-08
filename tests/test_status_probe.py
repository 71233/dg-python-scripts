"""Exercise Status HUD probe parsers without Flame, Qt, or system commands."""

from pathlib import Path
import plistlib
import tempfile
import unittest

from dg_python_scripts.status.probe import (
    _cpu_percent_from_samples,
    collect_media_probe,
    parse_apple_gpu_plist,
    parse_linux_meminfo,
    parse_macos_top,
    parse_nvidia_smi,
    parse_stone_wire_partitions,
)


class StatusProbeTests(unittest.TestCase):
    def test_linux_cpu_percent(self):
        value = _cpu_percent_from_samples((100, 60), (200, 100))
        self.assertAlmostEqual(value, 60.0)

    def test_linux_meminfo(self):
        total, used = parse_linux_meminfo(
            "MemTotal: 1000 kB\nMemAvailable: 250 kB\n"
        )
        self.assertEqual(total, 1000 * 1024)
        self.assertEqual(used, 750 * 1024)

    def test_stone_wire_parser(self):
        partitions = parse_stone_wire_partitions(
            """
# comment
[Partition0]
Name=p0
Path=/mnt/media0

[Partition7]
Name = Media
Path = /Volumes/Media
"""
        )
        self.assertEqual(partitions[0]["name"], "p0")
        self.assertEqual(partitions[7]["path"], "/Volumes/Media")

    def test_media_probe_maps_project_stonefs_to_partition(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            clip_root = root / "clip"
            project_path = clip_root / "stonefs3" / "TEST.prj"
            project_path.mkdir(parents=True)
            media_path = root / "media"
            media_path.mkdir()
            config = root / "stone+wire.cfg"
            config.write_text(
                f"[Partition3]\nName=TestMedia\nPath={media_path}\n",
                encoding="utf-8",
            )

            field = collect_media_probe(
                "TEST",
                clip_root=clip_root,
                config_path=config,
            )

            self.assertNotEqual(field.value, "—")
            self.assertIn("FREE /", field.value)
            self.assertIn("Partition3", field.detail)
            self.assertIn(str(media_path), field.detail)

    def test_media_probe_refuses_ambiguous_project_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            clip_root = root / "clip"
            (clip_root / "stonefs1" / "TEST.prj").mkdir(parents=True)
            (clip_root / "stonefs2" / "TEST.prj").mkdir(parents=True)
            config = root / "stone+wire.cfg"
            config.write_text("", encoding="utf-8")

            field = collect_media_probe(
                "TEST",
                clip_root=clip_root,
                config_path=config,
            )

            self.assertEqual(field.value, "—")
            self.assertIn("Multiple project metadata matches", field.detail)

    def test_macos_top_parser_uses_last_sample(self):
        cpu, used, total = parse_macos_top(
            """
CPU usage: 10.0% user, 5.0% sys, 85.0% idle
PhysMem: 12G used (1G wired), 4G unused.
CPU usage: 20.0% user, 7.0% sys, 73.0% idle
PhysMem: 13G used (1G wired), 3G unused.
"""
        )
        self.assertAlmostEqual(cpu, 27.0)
        self.assertEqual(used, 13 * 1024**3)
        self.assertEqual(total, 16 * 1024**3)

    def test_nvidia_smi_parser(self):
        gpu, memory, temp = parse_nvidia_smi(
            "0, NVIDIA RTX, 63, 12288, 49152, 61\n"
        )
        self.assertIn("63 %", gpu)
        self.assertIn("12.0 GB / 48.0 GB", memory)
        self.assertIn("61 °C", temp)

    def test_apple_gpu_plist_parser(self):
        data = plistlib.dumps(
            [
                {
                    "PerformanceStatistics": {
                        "Device Utilization %": 42,
                        "In use system memory": 123456789,
                        "Alloc system memory": 234567890,
                    }
                }
            ]
        )
        usage, memory, detail = parse_apple_gpu_plist(data)
        self.assertEqual(usage, "42 %")
        self.assertEqual(memory, 123456789)
        self.assertIn("Alloc system memory", detail)


if __name__ == "__main__":
    unittest.main()
