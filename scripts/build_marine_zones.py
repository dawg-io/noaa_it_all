#!/usr/bin/env python3
"""Regenerate ``marine_zones.py``, the marine zones offered when adding a marine entry.

A marine entry reads its zone's forecast from the office's Nearshore Marine Forecast (NSH), so the
zones worth offering are exactly the ones the NSH products cover. This script asks NWS which
offices issue NSH, expands the zone headers of each office's latest product with the
integration's own parser, and looks each zone up for its name, office and outline. The outline's
centre is kept so setup can put the zones nearest to Home Assistant's home location first.

Usage::

    python3 scripts/build_marine_zones.py            # rewrite marine_zones.py
    python3 scripts/build_marine_zones.py --check    # exit 1 if NWS no longer matches the file

NWS changes marine zones rarely, and announces it in advance. ``--check`` regenerates into memory
and diffs against the committed file, so a run shows whether the table needs updating.
"""

from __future__ import annotations

import argparse
import difflib
import json
import sys
import textwrap
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "custom_components" / "noaa_it_all" / "marine_zones.py"

sys.path.insert(0, str(OUTPUT.parent))
from parsers import _UGC_START_RE, expand_ugc  # noqa: E402

API = "https://api.weather.gov"
USER_AGENT = "(NOAA It All marine zone table, https://github.com/dawg-io/noaa_it_all)"

#: Zone ID prefixes (the first two letters) and the water they are on, west to east.
LAKES = {
    "LS": "Lake Superior",
    "LM": "Lake Michigan",
    "LH": "Lake Huron",
    "LC": "Lake St. Clair",
    "LE": "Lake Erie",
    "LO": "Lake Ontario",
    "SL": "St. Lawrence River",
}


def fetch_json(path: str) -> dict:
    """GET an api.weather.gov path as JSON, retrying briefly on a failure."""
    request = urllib.request.Request(
        API + path, headers={"User-Agent": USER_AGENT, "Accept": "application/geo+json"}
    )
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return json.load(response)
        except Exception:  # noqa: BLE001 - retried, then raised
            if attempt == 2:
                raise
            time.sleep(2 * (attempt + 1))
    raise AssertionError("unreachable")


def nsh_zones(office: str) -> list:
    """Return the zone IDs in an office's latest Nearshore Marine Forecast."""
    product = fetch_json(f"/products/types/NSH/locations/{office}/latest")
    zones = []
    for line in (product.get("productText") or "").splitlines():
        if _UGC_START_RE.match(line.strip()):
            zones.extend(expand_ugc(line))
    return zones


def centre(geometry: dict) -> tuple:
    """Return (lat, lon) of the centroid of a zone's largest polygon."""
    if geometry["type"] == "Polygon":
        polygons = [geometry["coordinates"]]
    else:
        polygons = geometry["coordinates"]
    best = None
    for polygon in polygons:
        ring = polygon[0]
        area = cx = cy = 0.0
        for (x0, y0), (x1, y1) in zip(ring, ring[1:]):
            cross = x0 * y1 - x1 * y0
            area += cross
            cx += (x0 + x1) * cross
            cy += (y0 + y1) * cross
        if area and (best is None or abs(area) > abs(best[0])):
            best = (area, cx / (3 * area), cy / (3 * area))
    if best is None:
        points = [p for polygon in polygons for p in polygon[0]]
        return (sum(p[1] for p in points) / len(points), sum(p[0] for p in points) / len(points))
    return (best[2], best[1])


def build() -> list:
    """Return the table rows: (zone, name, office, lat, lon), sorted by lake then zone."""
    offices = sorted(fetch_json("/products/types/NSH/locations").get("locations") or {})
    zones = sorted({zone for office in offices for zone in nsh_zones(office)})
    rows = []
    for zone in zones:
        if zone[:2] not in LAKES:
            raise SystemExit(f"{zone}: unknown lake prefix {zone[:2]!r}; add it to LAKES")
        feature = fetch_json(f"/zones/marine/{zone}")
        props = feature.get("properties") or {}
        lat, lon = centre(feature["geometry"])
        office = (props.get("cwa") or [""])[0]
        name = " ".join((props.get("name") or zone).split())
        rows.append((zone, name, office, round(lat, 3), round(lon, 3)))
    order = list(LAKES)
    rows.sort(key=lambda row: (order.index(row[0][:2]), row[0]))
    return rows


def render_row(row: tuple) -> str:
    """Render one table row, wrapping a long zone name to stay within 120 columns."""
    line = f"    {row!r},"
    if len(line) <= 120:
        return line
    zone, name, office, lat, lon = row
    pieces = textwrap.wrap(name, 90)
    parts = [f"        {piece + ' '!r}" for piece in pieces[:-1]] + [f"        {pieces[-1]!r},"]
    return "\n".join(
        ["    (", f"        {zone!r},", *parts, f"        {office!r}, {lat!r}, {lon!r},", "    ),"]
    )


def render(rows: list) -> str:
    """Render marine_zones.py."""
    lakes = "\n".join(f"    {prefix!r}: {name!r}," for prefix, name in LAKES.items())
    zones = "\n".join(render_row(row) for row in rows)
    return f'''"""Marine zones covered by NWS Nearshore Marine Forecasts -- generated, do not edit by hand.

Regenerate with ``python3 scripts/build_marine_zones.py``. The zones are the ones in the latest
Nearshore Marine Forecast (NSH) of every office that issues one; names, offices and outlines come
from api.weather.gov/zones/marine. ``lat``/``lon`` are the centre of the zone's outline, used to
offer the nearest lake and zone first when adding a marine entry.
"""

#: Zone ID prefix -> the water the zone is on, west to east.
LAKES = {{
{lakes}
}}

#: (zone, name, office, lat, lon), sorted by lake then zone ID.
MARINE_ZONES = (
{zones}
)
'''


def main(argv: list | None = None) -> int:
    """Regenerate the table, or with --check compare it with the committed one."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="diff against the committed file")
    args = parser.parse_args(argv)

    text = render(build())
    if args.check:
        current = OUTPUT.read_text(encoding="utf-8")
        if current == text:
            print(f"{OUTPUT.name} is up to date")
            return 0
        sys.stdout.writelines(difflib.unified_diff(
            current.splitlines(True), text.splitlines(True), str(OUTPUT.name), "NWS now"
        ))
        return 1
    OUTPUT.write_text(text, encoding="utf-8")
    print(f"Wrote {OUTPUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
