"""System probing utilities for Linux hosts."""

from __future__ import annotations

import json
import os
import pathlib
import re
import shlex
import socket
from typing import Any, Dict, Iterable, List, Optional

from . import schema
from .util import now_iso, run_cmd, safe_json_dump, which

RAW_DIR_NAME = "artifacts"


class Collector:
    """Helper object to orchestrate command execution and parsing."""

    def __init__(self, debug: bool, raw_dir: str | None, timeout: int | None) -> None:
        self.debug = debug
        self.timeout = timeout
        self.raw_dir = pathlib.Path(raw_dir or RAW_DIR_NAME)
        self.raw_dir_path: Optional[pathlib.Path] = None
        if self.debug:
            self.raw_dir_path = self.raw_dir.resolve()
            self.raw_dir_path.mkdir(parents=True, exist_ok=True)

    def run(self, name: str, argv: Iterable[str]) -> tuple[int, str, str]:
        rc, out, err = run_cmd(list(argv), timeout=self.timeout)
        if self.debug and self.raw_dir_path is not None:
            base = self.raw_dir_path / f"{name}.log"
            safe_json_dump(
                {
                    "argv": list(argv),
                    "returncode": rc,
                    "stdout": out,
                    "stderr": err,
                },
                base,
            )
        return rc, out, err


def _parse_os_release(path: str = "/etc/os-release") -> Dict[str, str | None]:
    data: Dict[str, str | None] = {
        "name": None,
        "version": None,
        "id": None,
        "pretty_name": None,
    }
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                value = value.strip().strip('"')
                key = key.lower()
                if key == "name":
                    data["name"] = value
                elif key == "version" or key == "version_id":
                    if not data["version"]:
                        data["version"] = value
                elif key == "id":
                    data["id"] = value
                elif key == "pretty_name":
                    data["pretty_name"] = value
    except OSError:
        pass
    return data


def _parse_lscpu(output: str) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    try:
        payload = json.loads(output)
        for entry in payload.get("lscpu", []):
            field = entry.get("field", "").strip().strip(":")
            data = entry.get("data")
            if field:
                result[field] = data
    except json.JSONDecodeError:
        pass
    return result


def _parse_cpuinfo(output: str) -> Dict[str, Any]:
    info: Dict[str, Any] = {}
    if not output:
        return info
    processors = [block for block in output.strip().split("\n\n") if block.strip()]
    if processors:
        first = processors[0]
        for line in first.splitlines():
            if ":" not in line:
                continue
            key, value = [part.strip() for part in line.split(":", 1)]
            info[key] = value
    info["processor_count"] = len(processors)
    return info


def _parse_meminfo(output: str) -> Dict[str, int]:
    result: Dict[str, int] = {}
    pattern = re.compile(r"^(\w+):\s+(\d+)\s*(\w+)?")
    for line in output.splitlines():
        match = pattern.match(line)
        if not match:
            continue
        key, value, unit = match.groups()
        value = int(value)
        unit = (unit or "B").upper()
        if unit == "KB":
            value *= 1024
        elif unit == "MB":
            value *= 1024 * 1024
        elif unit == "GB":
            value *= 1024 * 1024 * 1024
        result[key] = value
    return result


def _parse_dmidecode_baseboard(output: str) -> Dict[str, Optional[str]]:
    vendor = product = serial = None
    for line in output.splitlines():
        line = line.strip()
        if line.startswith("Manufacturer:"):
            vendor = line.split(":", 1)[1].strip() or None
        elif line.startswith("Product Name:"):
            product = line.split(":", 1)[1].strip() or None
        elif line.startswith("Serial Number:"):
            serial = line.split(":", 1)[1].strip() or None
    return {"vendor": vendor, "product": product, "serial": serial}


def _parse_dmidecode_bios(output: str) -> Dict[str, Optional[str]]:
    vendor = version = date = None
    for line in output.splitlines():
        line = line.strip()
        if line.startswith("Vendor:"):
            vendor = line.split(":", 1)[1].strip() or None
        elif line.startswith("Version:"):
            version = line.split(":", 1)[1].strip() or None
        elif line.startswith("Release Date:"):
            date = line.split(":", 1)[1].strip() or None
    return {"bios_vendor": vendor, "bios_version": version, "bios_date": date}


def _parse_lspci(output: str) -> List[Dict[str, Optional[str]]]:
    entries: List[Dict[str, Optional[str]]] = []
    for line in output.splitlines():
        if not line.strip():
            continue
        parts = shlex.split(line)
        if len(parts) < 3:
            continue
        slot = parts[0]
        class_name = parts[1].strip('"') if len(parts) > 1 else None
        vendor = parts[2].strip('"') if len(parts) > 2 else None
        device = parts[3].strip('"') if len(parts) > 3 else None
        entries.append(
            {
                "slot": slot,
                "class": class_name,
                "vendor": vendor,
                "device": device,
            }
        )
    return entries


def _parse_lsusb(output: str) -> List[Dict[str, Optional[str]]]:
    entries: List[Dict[str, Optional[str]]] = []
    pattern = re.compile(r"Bus (\d{3}) Device (\d{3}): ID ([0-9a-fA-F]{4}:[0-9a-fA-F]{4}) (.+)")
    for line in output.splitlines():
        match = pattern.match(line.strip())
        if not match:
            continue
        bus, dev, ident, rest = match.groups()
        entries.append(
            {
                "bus": bus,
                "device": dev,
                "id": ident,
                "description": rest.strip() or None,
            }
        )
    return entries


def _parse_lsblk(output: str) -> List[Dict[str, Any]]:
    try:
        data = json.loads(output)
    except json.JSONDecodeError:
        return []

    devices = data.get("blockdevices", [])

    def flatten(device: Dict[str, Any]) -> List[Dict[str, Any]]:
        entries: List[Dict[str, Any]] = []
        entry = {
            "name": device.get("name"),
            "size_bytes": device.get("size"),
            "rota": device.get("rota"),
            "tran": device.get("tran"),
            "model": device.get("model"),
            "serial": device.get("serial"),
            "mountpoints": [],
        }
        if isinstance(device.get("mountpoints"), list):
            for mp in device["mountpoints"]:
                if mp:
                    entry["mountpoints"].append(mp)
        if device.get("children"):
            for child in device["children"]:
                entries.extend(flatten(child))
        entries.append(entry)
        return entries

    all_entries: List[Dict[str, Any]] = []
    for dev in devices:
        all_entries.extend(flatten(dev))
    return all_entries


def _parse_dmidecode_slots(output: str) -> List[Dict[str, Any]]:
    slots: List[Dict[str, Any]] = []
    current: Dict[str, Any] | None = None
    for line in output.splitlines():
        line = line.rstrip()
        if not line:
            continue
        if not line.startswith("\t") and line.strip().startswith("Slot"):  # new section
            if current:
                slots.append(current)
            current = {"slot": line.strip()}
            continue
        if current is None:
            continue
        stripped = line.strip()
        if stripped.startswith("Type:"):
            current["type"] = stripped.split(":", 1)[1].strip() or None
        elif stripped.startswith("Length:"):
            length_value = stripped.split(":", 1)[1].strip().lower()
            if "long" in length_value or "full" in length_value:
                current["length"] = "full"
            elif "short" in length_value or "half" in length_value:
                current["length"] = "short"
            else:
                current["length"] = "unknown"
        elif stripped.startswith("Bus Address:"):
            current["bus_address"] = stripped.split(":", 1)[1].strip() or None
        elif stripped.startswith("Current Usage:"):
            usage = stripped.split(":", 1)[1].strip().lower()
            current["occupied"] = usage not in {"available", "unavailable"}
        elif stripped.startswith("Data Bus Width:"):
            current["lanes"] = stripped.split(":", 1)[1].strip() or None
        elif stripped.startswith("Designation:"):
            current["designation"] = stripped.split(":", 1)[1].strip() or None
        elif stripped.startswith("Installed Device:"):
            current["device"] = stripped.split(":", 1)[1].strip() or None
    if current:
        slots.append(current)
    return slots


def _detect_init_system() -> Optional[str]:
    comm = pathlib.Path("/proc/1/comm")
    try:
        return comm.read_text(encoding="utf-8").strip()
    except OSError:
        return None


def _collect_packages(collector: Collector, limit: int = 2000) -> Dict[str, Any]:
    managers = [
        ("dpkg", ["dpkg", "-l"]),
        ("rpm", ["rpm", "-qa"]),
        ("pacman", ["pacman", "-Q"]),
    ]
    for name, argv in managers:
        if which(argv[0]) is None:
            continue
        rc, out, _ = collector.run(f"packages_{name}", argv)
        if rc != 0 or not out:
            continue
        lines = [line.strip() for line in out.splitlines() if line.strip()]
        if name == "dpkg" and lines:
            cleaned: List[str] = []
            for line in lines:
                if line.startswith("Desired=") or line.startswith("||/") or line.startswith("+++"):
                    continue
                cleaned.append(line)
            items = []
            for line in cleaned:
                parts = line.split()
                if len(parts) >= 3:
                    items.append(f"{parts[1]} {parts[2]}")
        else:
            items = lines
        truncated = False
        if len(items) > limit:
            truncated = True
            items = items[:limit]
        return {"manager": name, "items": items, "truncated": truncated}
    return {"manager": None, "items": [], "truncated": False}


def _collect_runtimes(collector: Collector) -> Dict[str, Optional[str]]:
    runtimes: Dict[str, Optional[str]] = {}
    commands = {
        "python": ["python3", "--version"],
        "python_fallback": ["python", "--version"],
        "node": ["node", "-v"],
        "java": ["java", "-version"],
        "docker": ["docker", "--version"],
        "podman": ["podman", "--version"],
    }
    for key, argv in commands.items():
        if which(argv[0]) is None:
            continue
        rc, out, err = collector.run(key, argv)
        if rc != 0:
            continue
        text = out.strip() or err.strip()
        if not text:
            continue
        logical_key = key.replace("_fallback", "")
        if logical_key not in runtimes:
            runtimes[logical_key] = text.splitlines()[0]
    return runtimes


def _detect_tpm() -> bool:
    sys_path = pathlib.Path("/sys/class/tpm")
    if sys_path.exists() and any(sys_path.iterdir()):
        return True
    rc, out, _ = run_cmd(["dmesg", "--ctime"], timeout=2)
    if rc == 0 and "tpm" in out.lower():
        return True
    return False


def _detect_secure_boot() -> str:
    if which("mokutil") is None:
        return "unknown"
    rc, out, _ = run_cmd(["mokutil", "--sb-state"], timeout=2)
    if rc != 0:
        return "unknown"
    text = out.lower()
    if "enabled" in text:
        return "enabled"
    if "disabled" in text:
        return "disabled"
    return "unknown"


def _extras_collection(collector: Collector, extras: List[str]) -> Dict[str, Any]:
    payload: Dict[str, Any] = {}
    for item in extras:
        if item == "docker" and which("docker") is not None:
            rc, out, _ = collector.run("docker_ps", ["docker", "ps", "-a", "--format", "{{json .}}"])
            if rc == 0:
                payload["docker_containers"] = [line for line in out.splitlines() if line.strip()]
            rc, out, _ = collector.run("docker_images", ["docker", "images", "--format", "{{json .}}"])
            if rc == 0:
                payload["docker_images"] = [line for line in out.splitlines() if line.strip()]
        elif item == "systemd" and which("systemctl") is not None:
            rc, out, _ = collector.run("systemctl", ["systemctl", "list-unit-files"])
            if rc == 0:
                payload["systemd_unit_files"] = out.splitlines()
        elif item == "kvm" and which("virsh") is not None:
            rc, out, _ = collector.run("virsh", ["virsh", "list", "--all"])
            if rc == 0:
                payload["kvm_guests"] = out.splitlines()
    return payload


def collect(debug: bool = False, raw_dir: str | None = None, timeout: int = 5) -> Dict[str, Any]:
    """Collect system information returning a schema compliant document."""

    doc = schema.new_document()
    collector = Collector(debug, raw_dir, timeout)

    meta = doc["meta"]
    meta["generated_at"] = now_iso()
    hostname = socket.gethostname()
    meta["host"]["hostname"] = hostname

    os_release = _parse_os_release()
    meta["host"]["os"].update(os_release)

    rc, kernel, _ = collector.run("uname_r", ["uname", "-r"])
    if rc == 0:
        meta["host"]["os"]["kernel"] = kernel.strip() or None
    rc, arch, _ = collector.run("uname_m", ["uname", "-m"])
    if rc == 0:
        meta["host"]["os"]["architecture"] = arch.strip() or None

    rc, out, _ = collector.run("lscpu", ["lscpu", "-J"])
    cpu_data = {}
    if rc == 0 and out:
        cpu_data = _parse_lscpu(out)
    if not cpu_data:
        rc, out, _ = collector.run("cpuinfo", ["cat", "/proc/cpuinfo"])
        if rc == 0:
            cpu_data = _parse_cpuinfo(out)
    cpu_section = doc["cpu"]
    if cpu_data:
        cpu_section["model"] = cpu_data.get("Model name") or cpu_data.get("model name")
        cpu_section["vendor"] = cpu_data.get("Vendor ID") or cpu_data.get("vendor_id")

        def _int_from(value: Any) -> Optional[int]:
            if value is None:
                return None
            try:
                return int(str(value).split()[0])
            except (ValueError, TypeError):
                return None

        sockets = _int_from(cpu_data.get("Socket(s)"))
        cores_per_socket = _int_from(cpu_data.get("Core(s) per socket"))
        threads_per_core = _int_from(cpu_data.get("Thread(s) per core"))
        logical = _int_from(cpu_data.get("CPU(s)")) or _int_from(cpu_data.get("processor_count"))

        cpu_section["sockets"] = sockets
        cpu_section["threads_per_core"] = threads_per_core
        cpu_section["logical_processors"] = logical

        if sockets and cores_per_socket:
            cpu_section["cores"] = sockets * cores_per_socket
        else:
            cpu_section["cores"] = cores_per_socket or logical
        if "Flags" in cpu_data:
            cpu_section["flags"] = [flag.strip() for flag in str(cpu_data["Flags"]).split()] if cpu_data["Flags"] else []

    rc, out, _ = collector.run("meminfo", ["cat", "/proc/meminfo"])
    if rc == 0:
        meminfo = _parse_meminfo(out)
        if "MemTotal" in meminfo:
            doc["memory"]["total_bytes"] = meminfo["MemTotal"]
        if "SwapTotal" in meminfo:
            doc["memory"]["swap_bytes"] = meminfo["SwapTotal"]

    rc, out, _ = collector.run("dmidecode_baseboard", ["dmidecode", "-t", "baseboard"])
    if rc == 0:
        doc["motherboard"].update(_parse_dmidecode_baseboard(out))
    rc, out, _ = collector.run("dmidecode_bios", ["dmidecode", "-t", "bios"])
    if rc == 0:
        doc["firmware"].update(_parse_dmidecode_bios(out))

    rc, out, _ = collector.run("lspci", ["lspci", "-mm"])
    if rc == 0:
        doc["buses"]["pci"] = _parse_lspci(out)
    rc, out, _ = collector.run("lsusb", ["lsusb"])
    if rc == 0:
        doc["buses"]["usb"] = _parse_lsusb(out)

    gpu_entries: List[Dict[str, Any]] = []
    for entry in doc["buses"]["pci"]:
        class_name = (entry.get("class") or "").lower()
        if "vga" in class_name or "3d" in class_name:
            gpu_entries.append(
                {
                    "name": entry.get("device"),
                    "vendor": entry.get("vendor"),
                    "bus": entry.get("slot"),
                }
            )
    doc["gpu"] = gpu_entries

    rc, out, _ = collector.run("lsblk", ["lsblk", "-J", "-O"])
    if rc == 0:
        doc["storage"] = _parse_lsblk(out)

    # Network information via ip -j address if available
    if which("ip") is not None:
        rc, out, _ = collector.run("ip_addr", ["ip", "-j", "address"])
        if rc == 0:
            try:
                entries = json.loads(out)
            except json.JSONDecodeError:
                entries = []
            networks: List[Dict[str, Any]] = []
            for item in entries:
                networks.append(
                    {
                        "ifname": item.get("ifname"),
                        "addresses": [addr.get("local") for addr in item.get("addr_info", []) if addr.get("local")],
                        "mac": item.get("address"),
                        "state": item.get("operstate"),
                    }
                )
            doc["network"] = networks

    doc["software"]["init"] = _detect_init_system()
    doc["software"]["packages"] = _collect_packages(collector)
    doc["software"]["runtimes"] = _collect_runtimes(collector)

    extras_env = os.environ.get("SPEKTOR_EXTRAS", "")
    extras = [item.strip().lower() for item in extras_env.split(",") if item.strip()]
    if extras:
        doc["software"]["extras"] = _extras_collection(collector, extras)

    doc["firmware"]["tpm_present"] = _detect_tpm()
    doc["firmware"]["secure_boot"] = _detect_secure_boot()

    rc, out, _ = collector.run("dmidecode_slots", ["dmidecode", "-t", "slot"])
    if rc == 0:
        doc["slots"]["pcie"] = _parse_dmidecode_slots(out)

    if collector.raw_dir_path is not None:
        doc.setdefault("debug", {})["artifacts_dir"] = str(collector.raw_dir_path)

    valid, errors = schema.validate(doc)
    if not valid:
        doc.setdefault("debug", {})["validation_errors"] = errors
    return doc
