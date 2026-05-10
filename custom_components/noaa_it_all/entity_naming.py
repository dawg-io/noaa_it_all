"""Entity naming helpers for NOAA Integration.

This module centralizes entity object-ID generation so that NOAA
entities never end up with duplicated office/device prefixes such as
``noaa_ilm_weather_noaa_ilm_extended_forecast``.

The helper is intentionally defensive: it works on whatever object_id
string Home Assistant would otherwise assign and removes any duplicate
``noaa_{office}_{group}_noaa_{office}_`` prefix that a combination of
``has_entity_name`` plus an already-prefixed entity ``name`` could
produce. It is safe to call on already-clean object_ids and on global
entities (e.g. ``noaa_weather_hurricane_activity`` or
``noaa_space_planetary_k_index``), which it leaves untouched.
"""

from __future__ import annotations

# Device-group identifiers used by office-scoped NOAA devices. Add new
# group names here if a future device groups office entities under a
# different second segment (e.g. "noaa_{office}_marine_…").
_OFFICE_DEVICE_GROUPS = ("weather", "surf", "space")


def normalize_noaa_entity_object_id(
    object_id: str,
    office_code: str | None = None,
) -> str:
    """Return ``object_id`` with any duplicated office prefix removed.

    Examples:
        ``noaa_ilm_weather_noaa_ilm_extended_forecast``
            -> ``noaa_ilm_weather_extended_forecast``
        ``noaa_sgx_surf_noaa_sgx_rip_current_risk``
            -> ``noaa_sgx_surf_rip_current_risk``
        ``noaa_weather_hurricane_activity``
            -> ``noaa_weather_hurricane_activity`` (unchanged)
        ``noaa_ilm_temperature``
            -> ``noaa_ilm_temperature`` (unchanged)

    The function lower-cases the ``object_id`` because Home Assistant
    entity IDs are always lower-case. ``office_code`` is also
    lower-cased before comparison. When ``office_code`` is ``None`` the
    helper still strips duplicates for every supported device group by
    pattern-matching on the office segment.
    """
    if not object_id:
        return object_id

    object_id = object_id.lower()

    if office_code:
        offices = (office_code.lower(),)
    else:
        # Pattern-match: locate any ``noaa_{office}_{group}_noaa_{office}_``
        # occurrence and use that office for replacement. Multiple
        # different offices in a single string are unlikely but supported.
        offices = _detect_offices(object_id)

    for office in offices:
        for group in _OFFICE_DEVICE_GROUPS:
            duplicate = f"noaa_{office}_{group}_noaa_{office}_"
            correct = f"noaa_{office}_{group}_"
            # ``while`` guards against pathological inputs like a triple
            # repetition; in practice one pass is enough.
            while duplicate in object_id:
                object_id = object_id.replace(duplicate, correct)

    return object_id


def _detect_offices(object_id: str) -> tuple[str, ...]:
    """Return distinct office codes that appear in a duplicated prefix.

    Scans for the ``noaa_<office>_<group>_noaa_<office>_`` pattern and
    returns every unique office code found. Used when no explicit
    ``office_code`` is supplied to :func:`normalize_noaa_entity_object_id`.

    The office segment is delimited by the surrounding ``noaa_`` and
    ``_<group>_noaa_<office>_`` markers (not by a single underscore), so
    multi-segment office codes are matched correctly.
    """
    found: list[str] = []
    for group in _OFFICE_DEVICE_GROUPS:
        marker = f"_{group}_noaa_"
        start = 0
        while True:
            idx = object_id.find(marker, start)
            if idx == -1:
                break
            # The candidate office spans from the preceding ``noaa_``
            # boundary up to ``idx``.
            office_end = idx
            noaa_prefix = object_id.rfind("noaa_", 0, office_end)
            if noaa_prefix == -1:
                start = idx + 1
                continue
            office_start = noaa_prefix + len("noaa_")
            if office_start >= office_end:
                start = idx + 1
                continue
            candidate = object_id[office_start:office_end]
            # The repeated office (after ``_noaa_``) must match the
            # candidate exactly for this to be a true duplicated prefix.
            repeat_start = idx + len(marker)
            repeat_end = repeat_start + len(candidate)
            if (
                repeat_end <= len(object_id)
                and object_id[repeat_start:repeat_end] == candidate
                and (repeat_end == len(object_id) or object_id[repeat_end] == "_")
                and candidate not in found
            ):
                found.append(candidate)
            start = idx + 1
    return tuple(found)
