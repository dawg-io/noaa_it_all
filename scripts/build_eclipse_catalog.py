#!/usr/bin/env python3
"""Regenerate ``eclipse_catalog.py`` from NASA's Five Millennium Canon of Solar Eclipses.

Solar eclipses are the one part of this integration's astronomy that cannot be derived from
first principles at the precision users care about. Where a meteor shower recurs at the same
solar longitude every year -- which is why ``meteor_catalog.py`` never needs a date edit --
every solar eclipse is a one-off geometric accident of the Moon's orbit, and predicting where
its shadow lands needs Besselian elements computed from full VSOP87/ELP2000-82 ephemerides.
Those are published, so they are bundled rather than recomputed.

Source: the machine-readable mirror of the Canon's Besselian elements at
https://github.com/gmiller123456/FiveMillenniumCanonOfSolarEclipses-Besselian-Elements

The ``Extra`` variant is the one fetched here because it carries the eclipse type, gamma,
magnitude, path width and central-line duration alongside the elements themselves, so one file
covers everything the catalog needs.

Usage::

    python3 scripts/build_eclipse_catalog.py                    # 2025-2075, the shipped span
    python3 scripts/build_eclipse_catalog.py --start 2025 --end 2100
    python3 scripts/build_eclipse_catalog.py --source local.json --check

``--check`` regenerates into memory and diffs against the committed file instead of writing,
which is what a CI job would run to prove the catalog has not been hand-edited.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path

SOURCE_URL = (
    "https://raw.githubusercontent.com/gmiller123456/"
    "FiveMillenniumCanonOfSolarEclipses-Besselian-Elements/master/"
    "FiveMillenniumCanonOfSolarEclipsesExtra.json"
)

DEFAULT_START = 2025
DEFAULT_END = 2075

OUTPUT = (
    Path(__file__).resolve().parent.parent
    / "custom_components" / "noaa_it_all" / "eclipse_catalog.py"
)

#: NASA's redistribution terms require this line to travel with the data.
ACKNOWLEDGEMENT = "Eclipse Predictions by Fred Espenak, NASA's GSFC"

_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
           "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")

#: Canon type letters mapped to the vocabulary the rest of the integration speaks. The Canon
#: appends a qualifier to some letters -- ``Pb``/``Pe`` mark a partial eclipse beginning or
#: ending a Saros series, ``As``/``Tm`` mark a non-central annular or total -- none of which
#: changes what an observer sees, so only the leading letter is significant.
_TYPES = {"T": "total", "A": "annular", "H": "hybrid", "P": "partial"}


def eclipse_type(raw: str) -> str:
    """Return the plain-language eclipse type for a Canon type code."""
    letter = (raw or "").strip()[:1].upper()
    if letter not in _TYPES:
        raise ValueError(f"unrecognised eclipse type code {raw!r}")
    return _TYPES[letter]


def coefficients(entry: dict, prefix: str, count: int = 4) -> tuple:
    """Return the polynomial coefficients ``prefix1..prefixN`` as a tuple of floats.

    Trailing zeros are kept rather than trimmed: a fixed arity means ``eclipse.py`` can evaluate
    every polynomial through one helper without carrying a per-element degree.
    """
    return tuple(float(entry[f"{prefix}{index}"]) for index in range(1, count + 1))


def julian_day(year: int, month: int, day: int, hours: float) -> float:
    """Return the Julian Day for a Gregorian date and a fractional hour (Meeus ch. 7)."""
    if month <= 2:
        year, month = year - 1, month + 12
    a = year // 100
    b = 2 - a + a // 4
    return (
        int(365.25 * (year + 4716)) + int(30.6001 * (month + 1))
        + day + hours / 24.0 + b - 1524.5
    )


def clock_hours(stamp: str) -> float:
    """Return the fractional hour from one of the Canon's ``HH:MM:SS SCALE`` strings."""
    hh, mm, ss = (float(part) for part in str(stamp).split()[0].split(":"))
    return hh + mm / 60.0 + ss / 3600.0


def snap_to_same_day(jd: float, reference: float) -> float:
    """Return *jd* shifted by whole days until it is within twelve hours of *reference*.

    The Canon dates each row by greatest eclipse in Terrestrial Time, but ``t0`` is an integer
    hour that can belong to the neighbouring day -- the 2045-02-16 annular eclipse peaks at
    23:56 TDT and carries ``t0 = 0.000``, meaning midnight on the *17th*. Building the reference
    instant from the row's date alone puts that eclipse a full day out, and the error is
    invisible in every other field.
    """
    while jd - reference > 0.5:
        jd -= 1.0
    while jd - reference < -0.5:
        jd += 1.0
    return jd


def convert(entry: dict) -> dict:
    """Return one catalog record built from a Canon entry.

    NASA's own circumstances at greatest eclipse -- position, time, Sun altitude, duration --
    are carried through deliberately. They are not displayed anywhere; they exist so the
    test-suite can run the solver at that position and check it reproduces them, giving 114
    independent regression cases with no hand-entered numbers and nothing that rots.
    """
    year, month, day = int(entry["year"]), int(entry["month"]), int(entry["day"])
    # ``t0`` arrives as e.g. "17.000 TDT"; the scale is implied and always TDT.
    t0_hours = float(str(entry["t0"]).split()[0])
    # The row's date is the date of greatest eclipse in TDT, so the TDT stamp pins the day
    # unambiguously and everything else is measured from it.
    greatest_tdt_jd = julian_day(year, month, day, clock_hours(entry["instantOfGreatestEclipse"]))
    return {
        "date": (year, month, day),
        "type": eclipse_type(entry["eclipse_type"]),
        # Stored as a Julian Day rather than rebuilt at runtime from date + hour: t0 is an
        # integer hour on the date of greatest eclipse, so an eclipse whose elements straddle
        # midnight UT would otherwise need a day-boundary special case at every call site.
        "t0_jd": round(snap_to_same_day(
            julian_day(year, month, day, t0_hours), greatest_tdt_jd), 6),
        "delta_t": float(entry["deltat"]),
        "gamma": float(entry["gamma"]),
        "magnitude": float(entry["magnitude"]),
        "x": coefficients(entry, "x"),
        "y": coefficients(entry, "y"),
        "d": coefficients(entry, "d"),
        "mu": coefficients(entry, "mu"),
        "l1": coefficients(entry, "l1"),
        "l2": coefficients(entry, "l2"),
        "tanf1": float(entry["tanf1"]),
        "tanf2": float(entry["tanf2"]),
        "path_width_km": float(entry["greatestpathwidth"]),
        "central_duration_s": int(entry["greatestduration"]),
        # NASA's ground truth at greatest eclipse -- test fixtures, not display data.
        "greatest_jd": round(greatest_tdt_jd - float(entry["deltat"]) / 86400.0, 6),
        "greatest_latitude": float(entry["greatestlatitude"]),
        "greatest_longitude": float(entry["greatestlongitude"]),
        "greatest_altitude": float(entry["greatestalt"]),
    }


def format_tuple(values: tuple) -> str:
    """Return a tuple literal with each coefficient at its published precision."""
    return "(" + ", ".join(repr(value) for value in values) + ")"


def format_record(record: dict) -> str:
    """Return one catalog entry as source text.

    Nine lines per entry, pairing the polynomials up rather than giving each field a line of
    its own the way ``meteor_catalog.py`` does. At 114 entries the airier style would run to
    two thousand lines, and unlike the meteor catalog nobody reads or edits this one by hand
    -- it is regenerated wholesale -- so the density costs nothing that matters.
    """
    year, month, day = record["date"]
    return "\n".join([
        "    {",
        f'        "date": ({year}, {month}, {day}), "type": "{record["type"]}",'
        f' "t0_jd": {record["t0_jd"]!r}, "delta_t": {record["delta_t"]!r},',
        f'        "gamma": {record["gamma"]!r}, "magnitude": {record["magnitude"]!r},'
        f' "tanf1": {record["tanf1"]!r}, "tanf2": {record["tanf2"]!r},',
        f'        "x": {format_tuple(record["x"])}, "y": {format_tuple(record["y"])},',
        f'        "d": {format_tuple(record["d"])}, "mu": {format_tuple(record["mu"])},',
        f'        "l1": {format_tuple(record["l1"])}, "l2": {format_tuple(record["l2"])},',
        f'        "path_width_km": {record["path_width_km"]!r},'
        f' "central_duration_s": {record["central_duration_s"]!r},',
        f'        "greatest_jd": {record["greatest_jd"]!r},'
        f' "greatest_latitude": {record["greatest_latitude"]!r},',
        f'        "greatest_longitude": {record["greatest_longitude"]!r},'
        f' "greatest_altitude": {record["greatest_altitude"]!r},',
        "    },",
    ])


HEADER = '''"""Solar eclipse catalog for NOAA It All -- generated, do not edit by hand.

Regenerate with ``python3 scripts/build_eclipse_catalog.py``. Every value here comes from NASA's
*Five Millennium Canon of Solar Eclipses*, and NASA's redistribution terms require the
acknowledgment carried in :data:`ACKNOWLEDGEMENT` to travel with it.

Why this file exists at all, when ``meteor_catalog.py`` argues so hard for computing things
locally: a meteor shower recurs at the same solar longitude every year, so a handful of orbital
constants predicts it forever. A solar eclipse does not recur in any usefully simple way, and
working out *where on Earth* the shadow falls needs Besselian elements derived from full
VSOP87/ELP2000-82 ephemerides -- an order of magnitude more machinery than ``astro.py`` carries,
bought for a precision the rest of this integration would have no use for. Lunar eclipses are
the opposite case and are computed in ``eclipse.py`` with no catalog at all.

This module is standard library only with no relative imports, like ``astro.py``, ``meteor.py``
and ``meteor_catalog.py``, so the test-suite can load it directly via ``pytest.ini``'s
``pythonpath``.

The span is deliberately finite and the code must cope with running past the end of it: see
``CATALOG_START_YEAR`` / ``CATALOG_END_YEAR``, which ``eclipse.py`` reports through the
``catalog_exhausted`` flag rather than raising.

Besselian elements, in brief
----------------------------

The Moon's shadow is described in a coordinate system whose origin is Earth's centre and whose
z-axis points at the Moon. ``x`` and ``y`` place the shadow axis in that plane, ``d`` and ``mu``
give the axis's declination and Greenwich hour angle, ``l1`` and ``l2`` are the penumbral and
umbral cone radii, and ``tanf1``/``tanf2`` are the cone half-angles. Each is a polynomial in
hours from ``t0``, which is Terrestrial Dynamical Time -- hence ``delta_t``, needed to get back
to the UT a clock shows.

Field reference:

======================  =========================================================
``date``                ``(year, month, day)`` of greatest eclipse, UT
``type``                ``total`` / ``annular`` / ``hybrid`` / ``partial``
``t0_jd``               Julian Day of the elements' reference instant, TDT
``delta_t``             TDT - UT at the eclipse, seconds
``gamma``               Least distance of the shadow axis from Earth's centre
``magnitude``           Greatest eclipse magnitude, globally (not for any observer)
``x``, ``y``            Shadow-axis position polynomials, Earth radii
``d``                   Shadow-axis declination polynomial, degrees
``mu``                  Shadow-axis Greenwich hour angle polynomial, degrees
``l1``, ``l2``          Penumbral / umbral cone radius polynomials, Earth radii
``tanf1``, ``tanf2``    Tangents of the penumbral / umbral cone half-angles
``path_width_km``       Width of the central path at greatest eclipse, 0 if partial
``central_duration_s``  Duration of totality/annularity at greatest eclipse
``greatest_*``          NASA's own circumstances at greatest eclipse -- see below
======================  =========================================================

The ``greatest_jd`` / ``greatest_latitude`` / ``greatest_longitude`` / ``greatest_altitude``
fields are never rendered. They are NASA's published answer for the one point on Earth where the
shadow axis passes closest to the centre, and they exist so that ``tests/test_eclipse_catalog.py``
can run this integration's own solver at that point and check it reproduces them. That turns the
catalog into 114 independent regression cases containing no hand-typed expected values and
nothing that goes stale with the passage of time.

``l2`` is negative for a total eclipse. That sign is not a quirk to be normalised away: it is
what says the Moon's disc is the larger of the two, and ``eclipse.py`` depends on it.

"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

#: Required by NASA's terms of use for this data.
ACKNOWLEDGEMENT = "{acknowledgement}"

#: Where the elements came from, for anyone regenerating this file.
SOURCE_URL = (
{source_url}
)

#: First and last year covered. ``eclipse.py`` reports running past the end rather than raising.
CATALOG_START_YEAR = {start}
CATALOG_END_YEAR = {end}

#: Fields every catalog entry must define.
REQUIRED_FIELDS: Tuple[str, ...] = (
    "date", "type", "t0_jd", "delta_t", "gamma", "magnitude",
    "x", "y", "d", "mu", "l1", "l2", "tanf1", "tanf2",
    "path_width_km", "central_duration_s",
    "greatest_jd", "greatest_latitude", "greatest_longitude", "greatest_altitude",
)

#: Eclipse types that may appear in ``type``.
ECLIPSE_TYPES: Tuple[str, ...] = ("total", "annular", "hybrid", "partial")

SOLAR_ECLIPSES: List[Dict[str, Any]] = [
'''

FOOTER = ''']


def eclipses_in_year(year: int) -> List[Dict[str, Any]]:
    """Return every catalogued solar eclipse falling in *year*."""
    return [entry for entry in SOLAR_ECLIPSES if entry["date"][0] == year]


def find_eclipse(year: int, month: int, day: int) -> Optional[Dict[str, Any]]:
    """Return the catalog entry for a given date, or ``None`` if there is no eclipse then."""
    target = (year, month, day)
    for entry in SOLAR_ECLIPSES:
        if entry["date"] == target:
            return entry
    return None
'''


def wrapped_source_url() -> str:
    """Return ``SOURCE_URL`` as indented string fragments that fit inside the line limit."""
    parts = [
        "https://raw.githubusercontent.com/gmiller123456/",
        "FiveMillenniumCanonOfSolarEclipses-Besselian-Elements/master/",
        "FiveMillenniumCanonOfSolarEclipsesExtra.json",
    ]
    assert "".join(parts) == SOURCE_URL
    return "\n".join(f'    "{part}"' for part in parts)


def render(records: list, start: int, end: int) -> str:
    """Return the full source text of ``eclipse_catalog.py``."""
    header = HEADER.format(
        acknowledgement=ACKNOWLEDGEMENT,
        source_url=wrapped_source_url(),
        start=start,
        end=end,
    )
    body = "\n".join(format_record(record) for record in records)
    return header + body + "\n" + FOOTER


def load(source: str | None) -> list:
    """Return the Canon's entries, from a local path or the upstream URL."""
    if source:
        with open(source, "r", encoding="utf-8") as handle:
            return json.load(handle)["data"]
    with urllib.request.urlopen(SOURCE_URL, timeout=120) as response:
        return json.loads(response.read().decode("utf-8"))["data"]


def main(argv: list | None = None) -> int:
    """Regenerate the catalog, or verify the committed one still matches."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--start", type=int, default=DEFAULT_START)
    parser.add_argument("--end", type=int, default=DEFAULT_END)
    parser.add_argument("--source", help="local copy of the Canon JSON; fetched if omitted")
    parser.add_argument("--check", action="store_true",
                        help="compare against the committed file instead of writing it")
    args = parser.parse_args(argv)

    if args.start > args.end:
        parser.error("--start must not be after --end")

    entries = [entry for entry in load(args.source)
               if args.start <= int(entry["year"]) <= args.end]
    entries.sort(key=lambda entry: (entry["year"], entry["month"], entry["day"]))
    if not entries:
        parser.error(f"no eclipses found between {args.start} and {args.end}")

    text = render([convert(entry) for entry in entries], args.start, args.end)

    if args.check:
        current = OUTPUT.read_text(encoding="utf-8") if OUTPUT.exists() else ""
        if current == text:
            print(f"{OUTPUT.name} is up to date ({len(entries)} eclipses)")
            return 0
        print(f"{OUTPUT.name} differs from a fresh generation", file=sys.stderr)
        return 1

    OUTPUT.write_text(text, encoding="utf-8")
    print(f"wrote {OUTPUT} with {len(entries)} eclipses ({args.start}-{args.end})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
