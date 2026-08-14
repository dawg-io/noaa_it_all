"""Meteor shower forecasting for NOAA Integration — pure functions, no Home Assistant dependency.

Turns the solar-longitude catalog in ``meteor_catalog.py`` into an observer-specific forecast:
which showers are active, when each peaks, how high its radiant climbs tonight, how much the Moon
washes the sky out, and how many meteors an hour that adds up to.

Like ``astro.py`` this module needs nothing beyond the standard library, and it takes its catalog
as a **parameter** rather than importing it — mirroring how ``parsers.calculate_aurora_visibility``
receives ``AURORA_KP_THRESHOLDS``. That keeps the data separable from the maths and lets the
test-suite exercise the whole model without touching Home Assistant.

The one sibling it does need is ``astro``, imported through a small shim. Inside Home Assistant
this module is part of a package and the relative import applies; the test-suite loads it as a
bare module via ``pytest.ini``'s ``pythonpath``, where the absolute import applies. Without the
shim one of those two contexts always breaks.

The scoring model
-----------------

The standard meteor-observing relation corrects an observed rate to the zenithal hourly rate::

    HR = ZHR * sin(h_radiant) / r ** (6.5 - LM)

where ``h_radiant`` is the radiant's altitude, ``r`` the population index and ``LM`` the naked-eye
limiting magnitude. Run forward, it predicts what an observer actually sees.

The viewing score is that same relation divided by the ideal case — radiant at the zenith under a
6.5-magnitude sky::

    score = 100 * HR / ZHR = 100 * sin(h_radiant) * r ** (LM - 6.5)

ZHR cancels, and that is the point: **the score measures sky conditions, not shower strength.** A
minor shower riding high under a new moon scores well; the Perseids behind a full moon score
badly. Shower strength is reported separately as ``expected_per_hour``.

This module models sky *geometry* only — radiant altitude, moonlight and darkness. It knows
nothing about cloud, and deliberately so.
"""

from __future__ import annotations

import math
from datetime import date, datetime, timedelta, timezone, tzinfo
from typing import Any, Dict, List, Optional, Sequence

try:  # imported as part of the integration package (Home Assistant)
    from . import astro
except ImportError:  # pragma: no cover - imported as a bare module (test-suite)
    import astro

# ---------------------------------------------------------------------------
# Model constants
# ---------------------------------------------------------------------------

#: Naked-eye limiting magnitude under a pristine, moonless sky. The reference point for ZHR.
IDEAL_LIMITING_MAGNITUDE = 6.5

#: Magnitudes lost to a full Moon at the zenith. Empirical: full-moon skies reach roughly
#: magnitude 4, which is what this value reproduces.
MOON_MAX_PENALTY = 2.5

#: Magnitudes lost when the night never gets darker than nautical twilight.
NAUTICAL_TWILIGHT_PENALTY = 1.0

#: Floor applied to the limiting magnitude so the rate model cannot run away.
MIN_LIMITING_MAGNITUDE = 1.0

#: Step used when scanning the dark window for the best viewing moment.
BEST_WINDOW_STEP_MINUTES = 10

#: Fraction of the peak rate that still counts as being inside the "best window".
BEST_WINDOW_RATE_FRACTION = 0.5

#: Floor for a slope derived from the activity window rather than taken from the catalog.
#: Roughly a two-day full-width-half-maximum, which is already broad for a minor shower.
MIN_DERIVED_SLOPE = 0.15

#: Score thresholds, highest first. Hardcoded here rather than in ``const.py``, mirroring
#: ``parsers.get_visibility_class``.
_SCORE_RATINGS = (
    (80, "Excellent"),
    (60, "Very Good"),
    (40, "Good"),
    (20, "Fair"),
    (0, "Poor"),
)

#: Labels returned by :func:`limiting_factor`.
FACTOR_RADIANT = "radiant altitude"
FACTOR_MOON = "moonlight"
FACTOR_DARKNESS = "darkness"


# ---------------------------------------------------------------------------
# Activity profile
# ---------------------------------------------------------------------------

def activity_slope(shower: Dict[str, Any]) -> float:
    """Return the activity-profile slope ``B`` for *shower*.

    A published ``b`` from the catalog always wins. Only when none is available is the slope
    derived from the activity window, by assuming activity has decayed to roughly the naked-eye
    detection threshold of about one meteor per hour at the nearer window edge.

    That derivation is a weak substitute and is deliberately floored. An activity window records
    where a shower is detectable *at all*, which for a sharp shower is far wider than its peak:
    deriving the Quadrantid slope from its window gives 0.145 against a published 2.2, which
    stretches a fourteen-hour peak across a fortnight. The floor stops the fallback from ever
    producing a profile that broad, at the cost of being too sharp for a genuinely wide minor
    shower — the safer direction, since it under-reports rather than crying wolf.
    """
    published = shower.get("b")
    if published is not None:
        return float(published)

    to_start = abs(astro.wrap180(shower["sol_lon_max"] - shower["sol_lon_start"]))
    to_end = abs(astro.wrap180(shower["sol_lon_end"] - shower["sol_lon_max"]))
    half_width = max(min(to_start, to_end), 0.5)
    decades = math.log10(max(shower["zhr"], 2.0))
    return max(decades / half_width, MIN_DERIVED_SLOPE)


def zhr_at(shower: Dict[str, Any], solar_longitude: float) -> float:
    """Return the shower's zenithal hourly rate at *solar_longitude*.

    Uses the standard exponential profile ``ZHR = ZHR_max * 10 ** (-B * |delta|)``, with *delta*
    the signed shortest angular distance so the 360/0 degree wraparound is handled.
    """
    delta = abs(astro.wrap180(solar_longitude - shower["sol_lon_max"]))
    return shower["zhr"] * 10.0 ** (-activity_slope(shower) * delta)


def is_active(shower: Dict[str, Any], solar_longitude: float) -> bool:
    """Return whether *shower* is inside its activity window at *solar_longitude*."""
    offset = astro.normalize_degrees(solar_longitude - shower["sol_lon_start"])
    width = astro.normalize_degrees(shower["sol_lon_end"] - shower["sol_lon_start"])
    return offset <= width


# ---------------------------------------------------------------------------
# Sky brightness
# ---------------------------------------------------------------------------

def moon_penalty(moon_illumination: float, moon_alt: float) -> float:
    """Return magnitudes of limiting-magnitude loss caused by the Moon.

    *moon_illumination* is a fraction ``0.0``-``1.0``. A Moon below the horizon costs nothing;
    otherwise the penalty scales with phase and with how high the Moon rides.

    This is an explicitly empirical approximation, not photometry. It reproduces the two anchors
    that matter — a new or set Moon costs nothing, a full Moon overhead costs about 2.5 magnitudes
    — and interpolates smoothly between them.
    """
    if moon_alt <= 0.0:
        return 0.0
    phase_term = max(0.0, min(1.0, moon_illumination)) ** 1.5
    altitude_term = math.sqrt(math.sin(math.radians(min(moon_alt, 90.0))))
    return MOON_MAX_PENALTY * phase_term * altitude_term


def twilight_penalty(darkness: str) -> float:
    """Return magnitudes of loss caused by the sky never reaching astronomical darkness."""
    return NAUTICAL_TWILIGHT_PENALTY if darkness == astro.DARKNESS_NAUTICAL else 0.0


def limiting_magnitude(moon_illumination: float, moon_alt: float, darkness: str) -> float:
    """Return the naked-eye limiting magnitude for the given sky conditions."""
    magnitude = (
        IDEAL_LIMITING_MAGNITUDE
        - moon_penalty(moon_illumination, moon_alt)
        - twilight_penalty(darkness)
    )
    return max(MIN_LIMITING_MAGNITUDE, magnitude)


# ---------------------------------------------------------------------------
# Rates and scoring
# ---------------------------------------------------------------------------

def observed_rate(
    zhr: float,
    radiant_alt: float,
    population_index: float,
    limiting_mag: float,
) -> float:
    """Return the meteors per hour a single observer should actually see."""
    if radiant_alt <= 0.0:
        return 0.0
    geometry = math.sin(math.radians(radiant_alt))
    sky = population_index ** (limiting_mag - IDEAL_LIMITING_MAGNITUDE)
    return zhr * geometry * sky


def viewing_score(radiant_alt: float, population_index: float, limiting_mag: float) -> int:
    """Return a 0-100 sky-conditions score, independent of how strong the shower is."""
    if radiant_alt <= 0.0:
        return 0
    geometry = math.sin(math.radians(radiant_alt))
    sky = population_index ** (limiting_mag - IDEAL_LIMITING_MAGNITUDE)
    return int(round(max(0.0, min(1.0, geometry * sky)) * 100))


def score_rating(score: int) -> str:
    """Return a human-readable rating band for a viewing *score*."""
    for threshold, label in _SCORE_RATINGS:
        if score >= threshold:
            return label
    return _SCORE_RATINGS[-1][1]


def limiting_factor(
    radiant_alt: float,
    population_index: float,
    moon_illumination: float,
    moon_alt: float,
    darkness: str,
) -> str:
    """Return whichever condition is costing the most meteors right now.

    Each effect is expressed as the fraction of the ideal rate it removes, so they compare
    directly: a radiant at 30 degrees loses 50%, and so does a Moon costing enough magnitudes to
    halve the visible population.
    """
    if darkness == astro.DARKNESS_NONE:
        return FACTOR_DARKNESS

    altitude_loss = 1.0 - math.sin(math.radians(max(0.0, min(90.0, radiant_alt))))
    moon_loss = 1.0 - population_index ** (-moon_penalty(moon_illumination, moon_alt))
    twilight_loss = 1.0 - population_index ** (-twilight_penalty(darkness))

    ranked = (
        (altitude_loss, FACTOR_RADIANT),
        (moon_loss, FACTOR_MOON),
        (twilight_loss, FACTOR_DARKNESS),
    )
    return max(ranked, key=lambda item: item[0])[1]


# ---------------------------------------------------------------------------
# Night sampling
# ---------------------------------------------------------------------------

class SkySample:
    """One instant during the dark window, with the Moon state already resolved.

    The Moon's position is the expensive part of the calculation and does not depend on which
    shower is being considered, so it is computed once per instant and shared across every
    candidate shower.
    """

    __slots__ = ("when", "lst", "moon_alt", "moon_illumination", "limiting_mag")

    def __init__(self, when: datetime, lst: float, moon_alt: float,
                 moon_illumination: float, limiting_mag: float) -> None:
        self.when = when
        self.lst = lst
        self.moon_alt = moon_alt
        self.moon_illumination = moon_illumination
        self.limiting_mag = limiting_mag


def sample_night(
    dark_start: datetime,
    dark_end: datetime,
    latitude: float,
    longitude: float,
    darkness: str,
    step_minutes: int = BEST_WINDOW_STEP_MINUTES,
) -> List[SkySample]:
    """Return evenly spaced :class:`SkySample` instants spanning the dark window."""
    total_minutes = (dark_end - dark_start).total_seconds() / 60.0
    steps = max(1, int(total_minutes // step_minutes))

    samples: List[SkySample] = []
    for index in range(steps + 1):
        when = dark_start + timedelta(minutes=index * step_minutes)
        if when > dark_end:
            when = dark_end
        jd = astro.julian_day(when)
        sidereal = astro.local_sidereal_time(jd, longitude)
        # moon_equatorial is the most expensive routine in astro; compute it once and derive
        # both the altitude and the illuminated fraction from it.
        moon_ra, moon_dec = astro.moon_equatorial(jd)
        altitude, _ = astro.equatorial_to_horizontal(moon_ra, moon_dec, latitude, sidereal)
        illumination = astro.moon_illuminated_fraction_from(jd, moon_ra, moon_dec)
        samples.append(SkySample(
            when=when,
            lst=sidereal,
            moon_alt=altitude,
            moon_illumination=illumination,
            limiting_mag=limiting_magnitude(illumination, altitude, darkness),
        ))
    return samples


# ---------------------------------------------------------------------------
# Peak timing
# ---------------------------------------------------------------------------

def nearest_peak(shower: Dict[str, Any], now: datetime) -> datetime:
    """Return the peak instant closest to *now*, which may be slightly in the past.

    A shower that peaked last night is still the interesting one tonight, so for active showers
    the nearer peak matters more than the next one a year away.
    """
    upcoming = astro.next_solar_longitude_after(shower["sol_lon_max"], now)
    previous = astro.previous_solar_longitude_before(shower["sol_lon_max"], now)
    return previous if (now - previous) < (upcoming - now) else upcoming


def _local_noon(day: date, tz: tzinfo) -> datetime:
    """Return local noon on *day*, the instant an observing night is labelled from."""
    return datetime.combine(day, datetime.min.time(), tzinfo=tz) + timedelta(hours=12)


def _observing_night(now_local: datetime) -> date:
    """Return the date the current observing night belongs to.

    Nights are labelled by the evening they begin, so 02:00 belongs to the night that started the
    previous calendar day. Local noon is the changeover.
    """
    if now_local.hour < 12:
        return (now_local - timedelta(days=1)).date()
    return now_local.date()


# ---------------------------------------------------------------------------
# Forecast assembly
# ---------------------------------------------------------------------------

def _local_iso(when: Optional[datetime], tz: tzinfo) -> Optional[str]:
    """Return *when* as a local ISO-8601 string trimmed to minutes."""
    if when is None:
        return None
    return when.astimezone(tz).isoformat(timespec="minutes")


def _evaluate_shower(
    shower: Dict[str, Any],
    samples: Sequence[SkySample],
    solar_longitude: float,
    latitude: float,
    darkness: str,
    now: datetime,
    tz: tzinfo,
    night_start_local: datetime,
) -> Dict[str, Any]:
    """Return the full tonight-specific evaluation of a single active shower."""
    zhr_now = zhr_at(shower, solar_longitude)
    peak = nearest_peak(shower, now)
    highest_possible = astro.max_altitude(shower["dec"], latitude)

    rates: List[float] = []
    altitudes: List[float] = []
    for sample in samples:
        altitude, _ = astro.equatorial_to_horizontal(
            shower["ra"], shower["dec"], latitude, sample.lst
        )
        altitudes.append(altitude)
        rates.append(observed_rate(zhr_now, altitude, shower["r"], sample.limiting_mag))

    if not rates:
        best_index = None
    elif max(rates) > 0.0:
        best_index = max(range(len(rates)), key=lambda i: rates[i])
    else:
        # The radiant never clears the horizon tonight. Report the moment it comes closest
        # rather than an arbitrary first sample, so the altitude attribute stays meaningful.
        best_index = max(range(len(altitudes)), key=lambda i: altitudes[i])
    best_rate = rates[best_index] if best_index is not None else 0.0

    window_start = window_end = None
    if best_index is not None and best_rate > 0.0:
        floor = best_rate * BEST_WINDOW_RATE_FRACTION
        first = last = best_index
        while first > 0 and rates[first - 1] >= floor:
            first -= 1
        while last < len(rates) - 1 and rates[last + 1] >= floor:
            last += 1
        window_start, window_end = samples[first].when, samples[last].when

    if best_index is None:
        best_altitude = 0.0
        best_sample_moon_alt = 0.0
        best_sample_illumination = 0.0
        best_limiting_mag = IDEAL_LIMITING_MAGNITUDE
    else:
        best_altitude = altitudes[best_index]
        best_sample_moon_alt = samples[best_index].moon_alt
        best_sample_illumination = samples[best_index].moon_illumination
        best_limiting_mag = samples[best_index].limiting_mag

    score = viewing_score(best_altitude, shower["r"], best_limiting_mag)

    return {
        "code": shower["code"],
        "name": shower["name"],
        "zhr_now": round(zhr_now, 1),
        "zhr_max": shower["zhr"],
        "peak_utc": peak.isoformat(timespec="minutes"),
        "peak_local": _local_iso(peak, tz),
        "days_until": round((peak - now).total_seconds() / 86400.0, 2),
        "is_peak_night": night_start_local <= peak.astimezone(tz) < night_start_local + timedelta(days=1),
        "radiant_altitude": round(best_altitude, 1),
        "max_radiant_altitude": round(highest_possible, 1),
        "radiant_never_rises": highest_possible <= 0.0,
        "expected_per_hour": int(round(best_rate)),
        "viewing_score": score,
        "rating": score_rating(score),
        "limiting_factor": limiting_factor(
            best_altitude, shower["r"], best_sample_illumination, best_sample_moon_alt, darkness,
        ),
        "limiting_magnitude": round(best_limiting_mag, 2),
        "moon_illumination": int(round(best_sample_illumination * 100)),
        "moon_altitude": round(best_sample_moon_alt, 1),
        "best_window_start": _local_iso(window_start, tz),
        "best_window_end": _local_iso(window_end, tz),
        "constellation": shower["constellation"],
        "parent_body": shower["parent"],
        "velocity_kms": shower["v_geo"],
        "variable": shower["variable"],
    }


def build_meteor_forecast(
    now: datetime,
    latitude: float,
    longitude: float,
    tz: tzinfo,
    catalog: Sequence[Dict[str, Any]],
    upcoming_count: int = 5,
) -> Dict[str, Any]:
    """Return the complete meteor forecast payload for one observer.

    This is the single entry point the coordinator calls. Everything the entities render is
    pre-computed and pre-formatted here — including local-time strings — so the entity classes
    stay simple property readers and never need Home Assistant's datetime helpers.
    """
    jd_now = astro.julian_day(now)
    solar_longitude = astro.sun_apparent_longitude(jd_now)

    night_of = _observing_night(now.astimezone(tz))
    dark_start, dark_end, darkness = astro.find_dark_window(night_of, latitude, longitude)

    # Once tonight's darkness has run out, look ahead to the next night rather than keep
    # reporting a window that has already closed. Without this the forecast spends every morning
    # advertising a "best viewing" window that ended hours earlier, in daylight.
    if dark_end is not None and now > dark_end:
        night_of = night_of + timedelta(days=1)
        dark_start, dark_end, darkness = astro.find_dark_window(night_of, latitude, longitude)

    night_start_local = _local_noon(night_of, tz)

    if dark_start is not None and dark_end is not None:
        samples = sample_night(dark_start, dark_end, latitude, longitude, darkness)
        dark_hours = round((dark_end - dark_start).total_seconds() / 3600.0, 2)
    else:
        samples = []
        dark_hours = 0.0

    active = [
        _evaluate_shower(
            shower, samples, solar_longitude, latitude, darkness, now, tz, night_start_local,
        )
        for shower in catalog
        if is_active(shower, solar_longitude)
    ]
    active.sort(key=lambda item: (item["expected_per_hour"], item["zhr_now"]), reverse=True)

    # Only a shower whose radiant actually clears the horizon during the dark window can be the
    # one worth watching. Without this check the headline sensor happily names a shower whose
    # radiant sits tens of degrees below the horizon all night — the Quadrantids seen from
    # Sydney, for instance, which is true of roughly a quarter of the year there.
    observable = [item for item in active if item["radiant_altitude"] > 0.0]

    upcoming = []
    for shower in catalog:
        peak = astro.next_solar_longitude_after(shower["sol_lon_max"], now)
        upcoming.append({
            "code": shower["code"],
            "name": shower["name"],
            "peak_utc": peak.isoformat(timespec="minutes"),
            "peak_local": _local_iso(peak, tz),
            "days_until": round((peak - now).total_seconds() / 86400.0, 1),
            "zhr_max": shower["zhr"],
            "constellation": shower["constellation"],
        })
    upcoming.sort(key=lambda item: item["days_until"])

    # Mid-window Moon state, used when no shower is active and there is no "best" to report.
    if samples:
        midpoint = samples[len(samples) // 2]
        moon_illumination = int(round(midpoint.moon_illumination * 100))
        moon_alt = round(midpoint.moon_alt, 1)
    else:
        moon_illumination = int(round(astro.moon_illuminated_fraction(jd_now) * 100))
        moon_alt = round(astro.moon_altitude(jd_now, latitude, longitude), 1)

    return {
        "generated_utc": now.astimezone(timezone.utc).isoformat(timespec="seconds"),
        "latitude": latitude,
        "longitude": longitude,
        "solar_longitude": round(solar_longitude, 2),
        "night_of": night_of.isoformat(),
        "darkness": darkness,
        "dark_window_start": _local_iso(dark_start, tz),
        "dark_window_end": _local_iso(dark_end, tz),
        "dark_hours": dark_hours,
        "moon_illumination": moon_illumination,
        "moon_altitude": moon_alt,
        "active": active,
        "best": observable[0] if observable else None,
        "upcoming": upcoming[:upcoming_count],
    }
