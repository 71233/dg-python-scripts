"""One-shot status collectors used to validate the Status HUD data sources."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import glob
import os
import platform
import plistlib
import re
import shutil
import socket
import subprocess
import time
from typing import Any, Iterable


STONE_WIRE_CONFIG = Path("/opt/Autodesk/sw/cfg/stone+wire.cfg")
CLIP_ROOT = Path("/opt/Autodesk/clip")


@dataclass(frozen=True)
class ProbeField:
    value: str
    source: str
    detail: str = ""


@dataclass(frozen=True)
class FlameProbe:
    flame_version: ProbeField
    project: ProbeField


@dataclass(frozen=True)
class SystemProbe:
    platform: ProbeField
    host: ProbeField
    media: ProbeField
    cpu: ProbeField
    ram: ProbeField
    gpu: ProbeField
    gpu_memory: ProbeField
    gpu_temp: ProbeField


def _clean_error(error: BaseException) -> str:
    return " ".join(str(error).split())


def _field(value: str, source: str, detail: str = "") -> ProbeField:
    return ProbeField(value=value or "—", source=source, detail=detail)


def _unavailable(source: str, detail: str = "") -> ProbeField:
    return ProbeField(value="—", source=source, detail=detail)


def _flame_value(value: Any) -> Any:
    getter = getattr(value, "get_value", None)
    return getter() if callable(getter) else value


def collect_flame_probe() -> FlameProbe:
    """Collect only lightweight Flame API values; call this on Flame's main thread."""
    try:
        import flame
    except Exception as error:
        detail = _clean_error(error)
        return FlameProbe(
            flame_version=_unavailable("flame.get_version()", detail),
            project=_unavailable("flame.projects.current_project.name", detail),
        )

    try:
        flame_version = _field(str(flame.get_version()), "flame.get_version()")
    except Exception as error:
        flame_version = _unavailable("flame.get_version()", _clean_error(error))

    try:
        project = flame.projects.current_project
        project_name = str(_flame_value(project.name))
        project_field = _field(project_name, "flame.projects.current_project.name")
    except Exception as error:
        project_field = _unavailable(
            "flame.projects.current_project.name",
            _clean_error(error),
        )

    return FlameProbe(flame_version=flame_version, project=project_field)


def format_bytes(value: int | float) -> str:
    number = float(value)
    for unit in ("B", "KB", "MB", "GB", "TB", "PB"):
        if abs(number) < 1024.0 or unit == "PB":
            precision = 0 if unit in {"B", "KB", "MB"} else 1
            return f"{number:.{precision}f} {unit}"
        number /= 1024.0
    return f"{number:.1f} PB"


def parse_stone_wire_partitions(text: str) -> dict[int, dict[str, str]]:
    partitions: dict[int, dict[str, str]] = {}
    current: int | None = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith(("#", ";")):
            continue
        match = re.fullmatch(r"\[Partition(\d+)\]", line, re.IGNORECASE)
        if match:
            current = int(match.group(1))
            partitions.setdefault(current, {})
            continue
        if current is None or "=" not in line:
            continue
        key, value = (part.strip() for part in line.split("=", 1))
        partitions[current][key.lower()] = value
    return partitions


def _project_partition_candidates(
    project_name: str,
    clip_root: Path = CLIP_ROOT,
) -> list[tuple[int, Path]]:
    if not project_name or project_name == "—":
        return []
    escaped = glob.escape(project_name)
    pattern = str(clip_root / "stonefs*" / f"{escaped}.prj")
    candidates: list[tuple[int, Path]] = []
    for value in glob.glob(pattern):
        path = Path(value)
        match = re.fullmatch(r"stonefs(\d+)", path.parent.name)
        if match:
            candidates.append((int(match.group(1)), path))
    return sorted(candidates)


def collect_media_probe(
    project_name: str,
    *,
    clip_root: Path = CLIP_ROOT,
    config_path: Path = STONE_WIRE_CONFIG,
) -> ProbeField:
    source = "project stonefs metadata + /opt/Autodesk/sw/cfg/stone+wire.cfg"
    candidates = _project_partition_candidates(project_name, clip_root)
    if not candidates:
        return _unavailable(
            source,
            f"No {clip_root}/stonefs*/{project_name}.prj match",
        )
    if len(candidates) > 1:
        detail = "Multiple project metadata matches: " + ", ".join(
            str(path) for _, path in candidates
        )
        return _unavailable(source, detail)

    partition_id, project_path = candidates[0]
    try:
        config_text = config_path.read_text(encoding="utf-8", errors="replace")
    except OSError as error:
        return _unavailable(
            source,
            f"Project metadata: {project_path}; config error: {_clean_error(error)}",
        )

    partitions = parse_stone_wire_partitions(config_text)
    partition = partitions.get(partition_id, {})
    media_path_text = partition.get("path", "").strip()
    if not media_path_text:
        return _unavailable(
            source,
            f"Project metadata: {project_path}; Partition{partition_id} has no Path",
        )

    media_path = Path(os.path.expandvars(os.path.expanduser(media_path_text)))
    try:
        usage = shutil.disk_usage(media_path)
    except OSError as error:
        return _unavailable(
            source,
            (
                f"Partition{partition_id}: {media_path}; "
                f"disk usage error: {_clean_error(error)}"
            ),
        )

    name = partition.get("name", "").strip()
    label = f"{format_bytes(usage.free)} FREE / {format_bytes(usage.total)}"
    detail_parts = [
        f"Partition{partition_id}",
        str(media_path),
        f"project metadata: {project_path}",
    ]
    if name:
        detail_parts.insert(1, f"name={name}")
    return _field(label, source, "; ".join(detail_parts))


def _read_linux_cpu_sample(path: Path = Path("/proc/stat")) -> tuple[int, int]:
    line = path.read_text(encoding="utf-8").splitlines()[0]
    fields = line.split()
    if not fields or fields[0] != "cpu":
        raise ValueError("Unexpected /proc/stat format")
    values = [int(value) for value in fields[1:]]
    if len(values) < 4:
        raise ValueError("Incomplete /proc/stat CPU fields")
    idle = values[3] + (values[4] if len(values) > 4 else 0)
    total = sum(values)
    return total, idle


def _cpu_percent_from_samples(
    first: tuple[int, int],
    second: tuple[int, int],
) -> float:
    total_delta = second[0] - first[0]
    idle_delta = second[1] - first[1]
    if total_delta <= 0:
        raise ValueError("CPU counters did not advance")
    value = (total_delta - idle_delta) * 100.0 / total_delta
    return max(0.0, min(100.0, value))


def collect_linux_cpu() -> ProbeField:
    source = "/proc/stat (120 ms sample)"
    try:
        first = _read_linux_cpu_sample()
        time.sleep(0.12)
        second = _read_linux_cpu_sample()
        value = _cpu_percent_from_samples(first, second)
        return _field(f"{value:.0f} %", source)
    except Exception as error:
        return _unavailable(source, _clean_error(error))


def parse_linux_meminfo(text: str) -> tuple[int, int]:
    values: dict[str, int] = {}
    for line in text.splitlines():
        if ":" not in line:
            continue
        key, raw = line.split(":", 1)
        match = re.search(r"(\d+)", raw)
        if match:
            values[key] = int(match.group(1)) * 1024
    total = values["MemTotal"]
    available = values.get("MemAvailable")
    if available is None:
        available = (
            values.get("MemFree", 0)
            + values.get("Buffers", 0)
            + values.get("Cached", 0)
        )
    return total, max(0, total - available)


def collect_linux_ram() -> ProbeField:
    source = "/proc/meminfo"
    try:
        total, used = parse_linux_meminfo(
            Path("/proc/meminfo").read_text(encoding="utf-8")
        )
        return _field(
            f"{format_bytes(used)} / {format_bytes(total)}",
            source,
        )
    except Exception as error:
        return _unavailable(source, _clean_error(error))


def _run_command(command: list[str], timeout: float = 3.0) -> str:
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
    )
    if result.returncode != 0:
        stderr = " ".join(result.stderr.split())
        raise RuntimeError(
            f"{command[0]} exited {result.returncode}"
            + (f": {stderr}" if stderr else "")
        )
    return result.stdout


def _parse_size_token(token: str) -> int:
    match = re.fullmatch(r"([\d.]+)\s*([KMGTP])?", token.strip(), re.IGNORECASE)
    if not match:
        raise ValueError(f"Unsupported size token: {token}")
    value = float(match.group(1))
    unit = (match.group(2) or "").upper()
    multipliers = {
        "": 1,
        "K": 1024,
        "M": 1024**2,
        "G": 1024**3,
        "T": 1024**4,
        "P": 1024**5,
    }
    return int(value * multipliers[unit])


def parse_macos_top(text: str) -> tuple[float, int | None, int | None]:
    cpu_matches = re.findall(
        r"CPU usage:\s*([\d.]+)% user,\s*([\d.]+)% sys,\s*([\d.]+)% idle",
        text,
        flags=re.IGNORECASE,
    )
    if not cpu_matches:
        raise ValueError("CPU usage line not found in top output")
    user, system, idle = (float(value) for value in cpu_matches[-1])
    cpu = max(0.0, min(100.0, 100.0 - idle))

    phys_matches = re.findall(
        r"PhysMem:\s*([0-9.]+[KMGTP]?) used.*?,\s*([0-9.]+[KMGTP]?) unused",
        text,
        flags=re.IGNORECASE,
    )
    if not phys_matches:
        return cpu, None, None
    used_token, unused_token = phys_matches[-1]
    used = _parse_size_token(used_token)
    unused = _parse_size_token(unused_token)
    return cpu, used, used + unused


def collect_macos_cpu_ram() -> tuple[ProbeField, ProbeField]:
    source = "/usr/bin/top -l 2 -n 0"
    try:
        output = _run_command(
            ["/usr/bin/top", "-l", "2", "-n", "0", "-F", "-R"],
            timeout=4.0,
        )
        cpu, used, total = parse_macos_top(output)
        cpu_field = _field(f"{cpu:.0f} %", source)
        if used is None or total is None:
            ram_field = _unavailable(source, "PhysMem line not found")
        else:
            ram_field = _field(
                f"{format_bytes(used)} / {format_bytes(total)}",
                source,
            )
        return cpu_field, ram_field
    except Exception as error:
        detail = _clean_error(error)
        return _unavailable(source, detail), _unavailable(source, detail)


def parse_nvidia_smi(text: str) -> tuple[str, str, str]:
    gpu_values: list[str] = []
    memory_values: list[str] = []
    temp_values: list[str] = []
    for raw_line in text.splitlines():
        if not raw_line.strip():
            continue
        fields = [part.strip() for part in raw_line.split(",")]
        if len(fields) != 6:
            raise ValueError(f"Unexpected nvidia-smi row: {raw_line}")
        index, name, usage, used, total, temp = fields
        prefix = f"GPU {index} {name}"
        gpu_values.append(f"{prefix}: {float(usage):.0f} %")
        memory_values.append(
            f"GPU {index}: {format_bytes(float(used) * 1024**2)} / "
            f"{format_bytes(float(total) * 1024**2)}"
        )
        temp_values.append(f"GPU {index}: {float(temp):.0f} °C")
    if not gpu_values:
        raise ValueError("nvidia-smi returned no GPUs")
    return "; ".join(gpu_values), "; ".join(memory_values), "; ".join(temp_values)


def collect_nvidia_gpu() -> tuple[ProbeField, ProbeField, ProbeField]:
    source = "nvidia-smi query"
    executable = shutil.which("nvidia-smi")
    if not executable:
        unavailable = _unavailable(source, "nvidia-smi not found")
        return unavailable, unavailable, unavailable
    try:
        output = _run_command(
            [
                executable,
                "--query-gpu=index,name,utilization.gpu,memory.used,memory.total,temperature.gpu",
                "--format=csv,noheader,nounits",
            ],
            timeout=3.0,
        )
        gpu, memory, temp = parse_nvidia_smi(output)
        return (
            _field(gpu, source),
            _field(memory, source),
            _field(temp, source),
        )
    except Exception as error:
        detail = _clean_error(error)
        unavailable = _unavailable(source, detail)
        return unavailable, unavailable, unavailable


def _walk_mapping(value: Any) -> Iterable[tuple[str, Any]]:
    if isinstance(value, dict):
        for key, child in value.items():
            key_text = str(key)
            yield key_text, child
            yield from _walk_mapping(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            yield from _walk_mapping(child)


def parse_apple_gpu_plist(data: bytes) -> tuple[str | None, int | None, str]:
    root = plistlib.loads(data)
    metrics = list(_walk_mapping(root))
    usage_keys = (
        "Device Utilization %",
        "Renderer Utilization %",
    )
    usage: float | None = None
    for preferred in usage_keys:
        for key, value in metrics:
            if key == preferred and isinstance(value, (int, float)):
                usage = float(value)
                break
        if usage is not None:
            break

    memory: int | None = None
    for key, value in metrics:
        if key == "In use system memory" and isinstance(value, (int, float)):
            memory = int(value)
            break

    found = []
    interesting = {
        "Device Utilization %",
        "Renderer Utilization %",
        "Tiler Utilization %",
        "In use system memory",
        "Alloc system memory",
    }
    for key, value in metrics:
        if key in interesting and isinstance(value, (int, float)):
            found.append(f"{key}={value}")
    detail = ", ".join(dict.fromkeys(found))
    usage_text = None if usage is None else f"{usage:.0f} %"
    return usage_text, memory, detail


def collect_apple_gpu() -> tuple[ProbeField, ProbeField, ProbeField]:
    source = "/usr/sbin/ioreg AGXAccelerator PerformanceStatistics"
    executable = "/usr/sbin/ioreg"
    try:
        output = subprocess.run(
            [executable, "-r", "-c", "AGXAccelerator", "-d", "2", "-a"],
            capture_output=True,
            check=False,
            timeout=3.0,
        )
        if output.returncode != 0:
            stderr = output.stderr.decode("utf-8", errors="replace")
            raise RuntimeError(
                f"ioreg exited {output.returncode}: {' '.join(stderr.split())}"
            )
        usage, memory, detail = parse_apple_gpu_plist(output.stdout)
        gpu = (
            _field(usage, source, detail)
            if usage is not None
            else _unavailable(source, detail or "No utilization key found")
        )
        gpu_memory = (
            _field(format_bytes(memory), source, detail)
            if memory is not None
            else _unavailable(source, detail or "No active-memory key found")
        )
        gpu_temp = _unavailable(
            "macOS",
            "No non-privileged temperature collector selected for v1",
        )
        return gpu, gpu_memory, gpu_temp
    except Exception as error:
        detail = _clean_error(error)
        unavailable = _unavailable(source, detail)
        return unavailable, unavailable, _unavailable(
            "macOS",
            "No non-privileged temperature collector selected for v1",
        )


def collect_system_probe(project_name: str) -> SystemProbe:
    system = platform.system()
    platform_detail = f"{system} {platform.release()} ({platform.machine()})"
    host = socket.gethostname() or "—"
    media = collect_media_probe(project_name)

    if system == "Linux":
        cpu = collect_linux_cpu()
        ram = collect_linux_ram()
        gpu, gpu_memory, gpu_temp = collect_nvidia_gpu()
    elif system == "Darwin":
        cpu, ram = collect_macos_cpu_ram()
        gpu, gpu_memory, gpu_temp = collect_apple_gpu()
    else:
        detail = f"Unsupported platform: {system or 'unknown'}"
        cpu = _unavailable("platform collector", detail)
        ram = _unavailable("platform collector", detail)
        gpu = _unavailable("platform collector", detail)
        gpu_memory = _unavailable("platform collector", detail)
        gpu_temp = _unavailable("platform collector", detail)

    return SystemProbe(
        platform=_field(platform_detail, "platform module"),
        host=_field(host, "socket.gethostname()"),
        media=media,
        cpu=cpu,
        ram=ram,
        gpu=gpu,
        gpu_memory=gpu_memory,
        gpu_temp=gpu_temp,
    )


def _report_field(label: str, field: ProbeField) -> list[str]:
    lines = [f"{label:<12} {field.value}", f"{'source':<12} {field.source}"]
    if field.detail:
        lines.append(f"{'detail':<12} {field.detail}")
    return lines


def format_probe_report(flame: FlameProbe, system: SystemProbe) -> str:
    sections = [
        ("RUNTIME", (
            ("Flame", flame.flame_version),
            ("Platform", system.platform),
            ("Host", system.host),
        )),
        ("PROJECT / MEDIA", (
            ("Project", flame.project),
            ("Media", system.media),
        )),
        ("SYSTEM", (
            ("CPU", system.cpu),
            ("RAM", system.ram),
        )),
        ("GPU", (
            ("GPU", system.gpu),
            ("GPU MEM", system.gpu_memory),
            ("GPU TEMP", system.gpu_temp),
        )),
    ]
    lines = ["DGpy Status HUD Probe", ""]
    for title, values in sections:
        lines.append(f"[{title}]")
        for label, field in values:
            lines.extend(_report_field(label, field))
        lines.append("")
    lines.append("— means the collector could not determine a reliable value.")
    return "\n".join(lines)
