"""JSON schema helpers for system inventory documents."""

from __future__ import annotations

import copy
from typing import Any, Dict, List, Tuple

from .version import __version__

SCHEMA_VERSION = "0.1.0"

BASE_DOC: Dict[str, Any] = {
    "meta": {
        "schema_version": SCHEMA_VERSION,
        "generated_at": None,
        "host": {
            "hostname": None,
            "os": {
                "name": None,
                "version": None,
                "id": None,
                "pretty_name": None,
                "kernel": None,
                "architecture": None,
            },
        },
        "collector": {
            "tool": "spektor",
            "version": __version__,
        },
    },
    "cpu": {
        "model": None,
        "vendor": None,
        "sockets": None,
        "cores": None,
        "threads_per_core": None,
        "logical_processors": None,
        "flags": [],
    },
    "memory": {
        "total_bytes": None,
        "swap_bytes": None,
        "modules": [],
    },
    "motherboard": {
        "vendor": None,
        "product": None,
        "serial": None,
    },
    "firmware": {
        "bios_vendor": None,
        "bios_version": None,
        "bios_date": None,
        "tpm_present": None,
        "secure_boot": "unknown",
    },
    "gpu": [],
    "storage": [],
    "network": [],
    "slots": {
        "pcie": [],
    },
    "buses": {
        "pci": [],
        "usb": [],
    },
    "software": {
        "init": None,
        "packages": {
            "manager": None,
            "items": [],
            "truncated": False,
        },
        "runtimes": {},
        "extras": {},
    },
    "debug": {},
}


REQUIRED_TOP_LEVEL = {
    "meta": dict,
    "cpu": dict,
    "memory": dict,
    "motherboard": dict,
    "firmware": dict,
    "gpu": list,
    "storage": list,
    "network": list,
    "slots": dict,
    "buses": dict,
    "software": dict,
}


def new_document() -> Dict[str, Any]:
    """Return a deep copy of :data:`BASE_DOC`."""

    return copy.deepcopy(BASE_DOC)


def _require_keys(data: Dict[str, Any], keys: Dict[str, type], prefix: str, errors: List[str]) -> None:
    for key, expected in keys.items():
        if key not in data:
            errors.append(f"Missing key: {prefix}{key}")
            continue
        if expected is not None and not isinstance(data[key], expected):
            errors.append(
                f"Incorrect type for {prefix}{key}: expected {expected.__name__}, got {type(data[key]).__name__}"
            )


META_REQUIRED = {
    "schema_version": str,
    "host": dict,
}

OS_REQUIRED = {
    "name": (str, type(None)),
    "version": (str, type(None)),
    "id": (str, type(None)),
    "pretty_name": (str, type(None)),
    "kernel": (str, type(None)),
    "architecture": (str, type(None)),
}


def validate(doc: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """Validate *doc* returning ``(is_valid, errors)``."""

    errors: List[str] = []
    if not isinstance(doc, dict):
        return False, ["Document must be a mapping"]

    _require_keys(doc, REQUIRED_TOP_LEVEL, "", errors)

    meta = doc.get("meta", {})
    if not isinstance(meta, dict):
        errors.append("meta must be a mapping")
    else:
        for key, expected in META_REQUIRED.items():
            if key not in meta:
                errors.append(f"Missing key: meta.{key}")
                continue
            if not isinstance(meta[key], expected if isinstance(expected, type) else expected):
                errors.append(f"Invalid type for meta.{key}")
        host = meta.get("host", {})
        if isinstance(host, dict):
            hostname = host.get("hostname")
            if hostname is not None and not isinstance(hostname, str):
                errors.append("meta.host.hostname must be a string or null")
            os_data = host.get("os", {})
            if isinstance(os_data, dict):
                for field, exp in OS_REQUIRED.items():
                    value = os_data.get(field)
                    if value is not None and not isinstance(value, exp[0]):
                        errors.append(f"meta.host.os.{field} must be a string or null")
            else:
                errors.append("meta.host.os must be a mapping")
        else:
            errors.append("meta.host must be a mapping")

    schema_version = meta.get("schema_version") if isinstance(meta, dict) else None
    if schema_version and schema_version != SCHEMA_VERSION:
        errors.append(
            f"Unsupported schema version: {schema_version} (expected {SCHEMA_VERSION})"
        )

    for section in ("cpu", "memory", "motherboard", "firmware", "software"):
        value = doc.get(section)
        if value is not None and not isinstance(value, dict):
            errors.append(f"{section} must be a mapping")

    for section in ("gpu", "storage", "network"):
        value = doc.get(section)
        if value is not None and not isinstance(value, list):
            errors.append(f"{section} must be a list")

    slots = doc.get("slots")
    if isinstance(slots, dict):
        pcie = slots.get("pcie")
        if pcie is not None and not isinstance(pcie, list):
            errors.append("slots.pcie must be a list")
    else:
        errors.append("slots must be a mapping")

    buses = doc.get("buses")
    if isinstance(buses, dict):
        for key in ("pci", "usb"):
            value = buses.get(key)
            if value is not None and not isinstance(value, list):
                errors.append(f"buses.{key} must be a list")
    else:
        errors.append("buses must be a mapping")

    return len(errors) == 0, errors
