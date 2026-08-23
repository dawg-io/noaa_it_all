#!/usr/bin/env python3
"""Rename existing NOAA It All entities to the IDs a fresh install would create.

Home Assistant keys the entity registry on ``unique_id``, so entities keep whatever
``entity_id`` they were first assigned. Installations that predate the 0.5.x naming
changes therefore keep the old IDs, while the documentation describes the new ones.

This script recomputes each NOAA entity's ``entity_id`` the same way Home Assistant
would for a fresh install -- ``slugify(f"{device_name} {name}")`` when the entity sets
``has_entity_name``, otherwise ``slugify(name)`` -- and rewrites the registry.

Usage:
    # 1. Stop Home Assistant first. The registry is cached in memory and will be
    #    overwritten on shutdown if HA is still running.
    # 2. Dry run (prints the rename plan, writes nothing):
    python3 rename_noaa_entities.py /config/.storage
    # 3. Apply (writes a timestamped .bak alongside the registry first):
    python3 rename_noaa_entities.py /config/.storage --apply
    # 4. Start Home Assistant.

Pass --domain to limit the blast radius, e.g. --domain sensor binary_sensor.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import time
from pathlib import Path

PLATFORM = "noaa_it_all"


def slugify(text: str) -> str:
    """Approximate homeassistant.util.slugify for ASCII entity and device names."""
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", text or "").strip("_").lower()
    return re.sub(r"_+", "_", slug)


def load(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def device_names(storage: Path) -> dict[str, str]:
    """Map device_id -> the name Home Assistant uses when building entity IDs."""
    path = storage / "core.device_registry"
    if not path.exists():
        return {}
    data = load(path)["data"]
    names = {}
    for device in data.get("devices", []):
        names[device["id"]] = device.get("name_by_user") or device.get("name") or ""
    return names


def strip_prefix(entity_name: str | None, prefix: str | None) -> str | None:
    """Port of entity_registry._async_strip_prefix_from_entity_name (ASCII path).

    Returns None when the prefix does not meaningfully match.
    """
    if not entity_name or not prefix:
        return None
    if not entity_name[: len(prefix)].casefold().startswith(prefix.casefold()):
        return None
    new_name = entity_name[len(prefix):].lstrip(" -:")
    if not new_name:
        return ""
    if len(new_name) == len(entity_name) - len(prefix):
        return None  # no separator between the prefix and the remainder
    return new_name


def target_entity_id(entry: dict, devices: dict[str, str]) -> str | None:
    """Return the entity_id a fresh install would assign, or None if undeterminable.

    Mirrors homeassistant/helpers/entity_registry._async_get_full_entity_name: the
    device name is ALWAYS prepended when the entity belongs to a device.
    ``has_entity_name`` does NOT control that -- it only decides whether a redundant
    device-name prefix is stripped off the entity's own name first.
    """
    domain = entry["entity_id"].split(".", 1)[0]
    name = entry.get("original_name") or ""
    device_name = devices.get(entry.get("device_id") or "", "")

    entity_name = name
    if not entry.get("has_entity_name"):
        stripped = strip_prefix(name, device_name)
        if stripped is not None:
            entity_name = stripped

    full = " ".join(part for part in (device_name, entity_name) if part)
    if not full:
        return None
    return f"{domain}.{slugify(full)}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("storage", type=Path,
                        help="path to Home Assistant's .storage directory, e.g. /config/.storage")
    parser.add_argument("--apply", action="store_true",
                        help="write the changes (default is a dry run)")
    parser.add_argument("--domain", nargs="*", default=None,
                        help="only rename these domains (default: all)")
    args = parser.parse_args()

    reg_path = args.storage / "core.entity_registry"
    if not reg_path.exists():
        print(f"error: {reg_path} not found", file=sys.stderr)
        return 1

    registry = load(reg_path)
    entities = registry["data"]["entities"]
    devices = device_names(args.storage)

    # Every entity_id currently in use, so we never rename onto an occupied ID.
    taken = {e["entity_id"] for e in entities}

    planned: list[tuple[dict, str]] = []
    skipped: list[tuple[str, str]] = []

    for entry in entities:
        if entry.get("platform") != PLATFORM:
            continue
        domain = entry["entity_id"].split(".", 1)[0]
        if args.domain and domain not in args.domain:
            continue
        want = target_entity_id(entry, devices)
        if want is None:
            skipped.append((entry["entity_id"], "cannot determine target name"))
            continue
        if want == entry["entity_id"]:
            continue
        if want in taken:
            skipped.append((entry["entity_id"], f"target {want} already exists"))
            continue
        taken.discard(entry["entity_id"])
        taken.add(want)
        planned.append((entry, want))

    if not planned and not skipped:
        print("Nothing to do -- every NOAA entity already uses its expected ID.")
        return 0

    width = max((len(e["entity_id"]) for e, _ in planned), default=0)
    for entry, want in planned:
        print(f"  {entry['entity_id']:<{width}}  ->  {want}")
    for entity_id, why in skipped:
        print(f"  SKIP {entity_id}: {why}")

    print(f"\n{len(planned)} to rename, {len(skipped)} skipped.")

    if not args.apply:
        print("\nDry run -- nothing written. Re-run with --apply to make these changes.")
        print("Stop Home Assistant first, or it will overwrite the file on shutdown.")
        return 0

    # NB: not Path.with_suffix() -- it would treat ".entity_registry" as the suffix
    # and replace it, producing "core.bak-...".
    stamp = time.strftime("%Y%m%d-%H%M%S")
    backup = reg_path.with_name(f"{reg_path.name}.bak-{stamp}")
    shutil.copy2(reg_path, backup)
    print(f"\nBacked up registry to {backup}")

    for entry, want in planned:
        entry["entity_id"] = want

    tmp = reg_path.with_name(f"{reg_path.name}.tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        json.dump(registry, handle, indent=2)
    tmp.replace(reg_path)
    print(f"Wrote {len(planned)} renames to {reg_path}")
    print("Start Home Assistant, then update any automations, scripts and dashboards "
          "that referenced the old IDs.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
