"""Astronomical calculations for NOAA Integration — pure functions, no Home Assistant dependency.

This module implements the small set of positional-astronomy routines needed by the meteor
shower forecast. It follows the same contract as ``parsers.py``: **standard library only, no
relative imports**, so the test-suite can import it directly as ``from astro import ...``.

Algorithms are the low-precision series from Jean Meeus, *Astronomical Algorithms* (2nd ed.),
verified against his worked examples 7.a, 12.a, 13.b, 25.a, 47.a and 48.a (see
``tests/test_astro.py``). Accuracy is deliberately modest:

* solar longitude  — better than 0.01 deg
* lunar position   — roughly 0.03 deg, far below the noise in any sky-brightness model
* altitudes        — better than 0.01 deg

**Computed shower peaks are good to about +/-11 minutes.** Because 0.01 deg of solar longitude is
roughly 15 minutes of time, the series truncation dominates: measured against published
equinox and solstice times for 2025-2026 the error ranges from -10.6 to +4.2 minutes. That is
entirely acceptable here, because published shower maxima are themselves quoted to +/-0.05-0.2 deg
of solar longitude (1-5 hours), and real maxima wander by hours from year to year. The systematic
error is well over an order of magnitude smaller than the physical uncertainty it sits inside.

Two things were tried and deliberately rejected. Adding the Meeus-1988 planetary perturbation
terms makes the fit *worse*, because those coefficients are keyed to different mean elements than
the ch. 25 series used here. Modelling the TT-UT offset (delta-T, currently about 69 s) would be
false precision an order of magnitude below the truncation error. Julian Days are treated as UT
throughout. For the same reason VSOP87 / ELP2000 are avoided: they would buy precision that the
rest of the model cannot use.

All datetimes crossing this module's boundary are timezone-aware. Naive datetimes are rejected
rather than silently assumed to be UTC, because a silent assumption here would shift every
computed peak by the observer's UTC offset.
"""

from __future__ import annotations

import math
from datetime import date, datetime, timedelta, timezone
from typing import List, Optional, Tuple

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Julian Day of the J2000.0 epoch (2000-01-01 12:00:00 UTC).
J2000_JD = 2451545.0

#: The J2000.0 epoch as an aware datetime, used to convert Julian Days back to datetimes.
J2000_EPOCH = datetime(2000, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

#: Days per Julian century.
DAYS_PER_CENTURY = 36525.0

#: Mean apparent motion of the Sun in ecliptic longitude, degrees per day. Used to seed and
#: to differentiate the solar-longitude inversion.
SUN_DEG_PER_DAY = 0.98564736

#: Sun altitude defining astronomical twilight / true darkness.
ASTRONOMICAL_TWILIGHT_DEG = -18.0

#: Sun altitude defining nautical twilight, the fallback when astronomical night never occurs.
NAUTICAL_TWILIGHT_DEG = -12.0

#: Darkness labels returned by :func:`find_dark_window`.
DARKNESS_ASTRONOMICAL = "astronomical night"
DARKNESS_NAUTICAL = "nautical twilight only"
DARKNESS_NONE = "no astronomical darkness"

#: Sampling step used when searching for the dark window.
_DARK_SCAN_STEP_MINUTES = 5

#: Iterations used to bisect a twilight boundary once the sampling has bracketed it.
_BISECT_ITERATIONS = 20


# ---------------------------------------------------------------------------
# Angle helpers
# ---------------------------------------------------------------------------

def normalize_degrees(angle: float) -> float:
    """Return *angle* wrapped into ``[0, 360)``."""
    return angle % 360.0


def wrap180(angle: float) -> float:
    """Return *angle* wrapped into ``(-180, 180]``.

    This is the signed shortest angular distance, and it is what makes every 360/0 degree
    wraparound in this module work — notably the Quadrantids (solar longitude 283 deg, peaking
    in early January) and the Ursids (270 deg, peaking in late December), which straddle the
    year boundary.
    """
    wrapped = (angle + 180.0) % 360.0 - 180.0
    # ``%`` maps exactly -180 to -180; canonicalise to +180 so the range is (-180, 180].
    return 180.0 if wrapped == -180.0 else wrapped


def angular_separation_degrees(ra1: float, dec1: float, ra2: float, dec2: float) -> float:
    """Return the great-circle angle between two equatorial positions, in degrees."""
    ra1_r, dec1_r = math.radians(ra1), math.radians(dec1)
    ra2_r, dec2_r = math.radians(ra2), math.radians(dec2)
    cos_sep = (
        math.sin(dec1_r) * math.sin(dec2_r)
        + math.cos(dec1_r) * math.cos(dec2_r) * math.cos(ra1_r - ra2_r)
    )
    return math.degrees(math.acos(max(-1.0, min(1.0, cos_sep))))


# ---------------------------------------------------------------------------
# Time
# ---------------------------------------------------------------------------

def _require_aware(dt: datetime) -> datetime:
    """Return *dt* converted to UTC, rejecting naive datetimes."""
    if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
        raise ValueError("astro requires timezone-aware datetimes; got a naive datetime")
    return dt.astimezone(timezone.utc)


def julian_day(dt: datetime) -> float:
    """Return the Julian Day for an aware *dt* (Meeus ch. 7, Gregorian calendar)."""
    dt = _require_aware(dt)

    year, month = dt.year, dt.month
    day = (
        dt.day
        + (dt.hour + (dt.minute + (dt.second + dt.microsecond / 1e6) / 60.0) / 60.0) / 24.0
    )

    if month <= 2:
        year -= 1
        month += 12

    a = year // 100
    b = 2 - a + a // 4

    return (
        math.floor(365.25 * (year + 4716))
        + math.floor(30.6001 * (month + 1))
        + day + b - 1524.5
    )


def datetime_from_jd(jd: float) -> datetime:
    """Return the aware UTC datetime for Julian Day *jd*.

    Computed as an offset from :data:`J2000_EPOCH` rather than by inverting the calendar
    algorithm — exact, and free of the floating-point edge cases the classic inversion has
    around month boundaries.
    """
    return J2000_EPOCH + timedelta(days=jd - J2000_JD)


def julian_centuries(jd: float) -> float:
    """Return Julian centuries elapsed since J2000.0."""
    return (jd - J2000_JD) / DAYS_PER_CENTURY


# ---------------------------------------------------------------------------
# Sun
# ---------------------------------------------------------------------------

def _nutation_argument(t: float) -> float:
    """Return the longitude of the ascending node of the Moon's mean orbit, in degrees."""
    return 125.04 - 1934.136 * t


def obliquity_of_ecliptic(jd: float) -> float:
    """Return the true obliquity of the ecliptic in degrees (Meeus ch. 22)."""
    t = julian_centuries(jd)
    eps0 = (
        23.439291111
        - 0.0130041667 * t
        - 1.638889e-7 * t ** 2
        + 5.036111e-7 * t ** 3
    )
    return eps0 + 0.00256 * math.cos(math.radians(_nutation_argument(t)))


def sun_apparent_longitude(jd: float) -> float:
    """Return the Sun's apparent ecliptic longitude in degrees ``[0, 360)`` (Meeus ch. 25).

    This is the "solar longitude" that meteor astronomers use to pin shower activity: it is a
    direct measure of where Earth sits in its orbit, and so is stable from year to year in a way
    calendar dates are not.
    """
    t = julian_centuries(jd)

    mean_longitude = 280.46646 + 36000.76983 * t + 0.0003032 * t ** 2
    mean_anomaly = 357.52911 + 35999.05029 * t - 0.0001537 * t ** 2
    m_rad = math.radians(mean_anomaly)

    center = (
        (1.914602 - 0.004817 * t - 0.000014 * t ** 2) * math.sin(m_rad)
        + (0.019993 - 0.000101 * t) * math.sin(2 * m_rad)
        + 0.000289 * math.sin(3 * m_rad)
    )

    true_longitude = mean_longitude + center
    omega = _nutation_argument(t)
    apparent = true_longitude - 0.00569 - 0.00478 * math.sin(math.radians(omega))
    return normalize_degrees(apparent)


def sun_equatorial(jd: float) -> Tuple[float, float]:
    """Return the Sun's apparent ``(right_ascension, declination)`` in degrees."""
    lam = math.radians(sun_apparent_longitude(jd))
    eps = math.radians(obliquity_of_ecliptic(jd))

    ra = math.degrees(math.atan2(math.cos(eps) * math.sin(lam), math.cos(lam)))
    dec = math.degrees(math.asin(math.sin(eps) * math.sin(lam)))
    return normalize_degrees(ra), dec


def sun_altitude(jd: float, latitude: float, longitude: float) -> float:
    """Return the Sun's altitude above the horizon in degrees (negative below)."""
    ra, dec = sun_equatorial(jd)
    lst = local_sidereal_time(jd, longitude)
    altitude, _ = equatorial_to_horizontal(ra, dec, latitude, lst)
    return altitude


def next_solar_longitude_after(target_longitude: float, after: datetime) -> datetime:
    """Return the first UTC instant strictly after *after* when the Sun reaches *target_longitude*.

    This is the heart of the "computed peak" design. A meteor shower catalog stores the solar
    longitude of maximum — never a date — and this inversion turns it into the actual instant for
    whatever year is being asked about. That is why the catalog stays correct indefinitely.

    Seeded from the current solar longitude, then refined by Newton's method on
    ``f(t) = wrap180(sun_apparent_longitude(t) - target)``. The Sun's motion is close enough to
    uniform that the constant derivative :data:`SUN_DEG_PER_DAY` converges in three or four steps.
    """
    return datetime_from_jd(_solve_solar_longitude(target_longitude, julian_day(after), forward=True))


def previous_solar_longitude_before(target_longitude: float, before: datetime) -> datetime:
    """Return the last UTC instant strictly before *before* when the Sun reached *target_longitude*."""
    return datetime_from_jd(_solve_solar_longitude(target_longitude, julian_day(before), forward=False))


def _solve_solar_longitude(target_longitude: float, jd_ref: float, forward: bool) -> float:
    """Return the Julian Day of the solar-longitude crossing adjacent to *jd_ref*."""
    target = normalize_degrees(target_longitude)
    current = sun_apparent_longitude(jd_ref)

    if forward:
        delta = normalize_degrees(target - current)
        # A delta of zero means we are sitting exactly on the crossing; the *next* one is a
        # full revolution away, not this instant.
        if delta < 1e-9:
            delta = 360.0
        jd = jd_ref + delta / SUN_DEG_PER_DAY
    else:
        delta = normalize_degrees(current - target)
        if delta < 1e-9:
            delta = 360.0
        jd = jd_ref - delta / SUN_DEG_PER_DAY

    for _ in range(10):
        diff = wrap180(sun_apparent_longitude(jd) - target)
        if abs(diff) < 1e-8:
            break
        jd -= diff / SUN_DEG_PER_DAY

    # Newton can nudge the root a hair across the reference instant; push it a whole revolution
    # if that happened so the "strictly after/before" contract always holds.
    if forward and jd <= jd_ref:
        jd += 360.0 / SUN_DEG_PER_DAY
    elif not forward and jd >= jd_ref:
        jd -= 360.0 / SUN_DEG_PER_DAY

    return jd


# ---------------------------------------------------------------------------
# Sidereal time and coordinate transforms
# ---------------------------------------------------------------------------

def gmst_degrees(jd: float) -> float:
    """Return Greenwich Mean Sidereal Time in degrees ``[0, 360)`` (Meeus eq. 12.4)."""
    t = julian_centuries(jd)
    theta = (
        280.46061837
        + 360.98564736629 * (jd - J2000_JD)
        + 0.000387933 * t ** 2
        - t ** 3 / 38710000.0
    )
    return normalize_degrees(theta)


def local_sidereal_time(jd: float, longitude: float) -> float:
    """Return Local Mean Sidereal Time in degrees for an east-positive *longitude*."""
    return normalize_degrees(gmst_degrees(jd) + longitude)


def equatorial_to_horizontal(
    right_ascension: float,
    declination: float,
    latitude: float,
    local_sidereal: float,
) -> Tuple[float, float]:
    """Convert equatorial coordinates to ``(altitude, azimuth)`` in degrees.

    Azimuth is measured **from north, increasing eastward** — the convention users expect. Meeus
    measures it from south, so his published example values are 180 degrees away from these
    (his 68.03 for example 13.b is 248.03 here). *longitude* feeding ``local_sidereal`` is
    east-positive, matching how Home Assistant stores it; Meeus uses west-positive.

    The transform is latitude-general, so southern-hemisphere observers need no special-casing.
    """
    hour_angle = math.radians(local_sidereal - right_ascension)
    dec = math.radians(declination)
    lat = math.radians(latitude)

    sin_alt = (
        math.sin(dec) * math.sin(lat)
        + math.cos(dec) * math.cos(lat) * math.cos(hour_angle)
    )
    altitude = math.degrees(math.asin(max(-1.0, min(1.0, sin_alt))))

    azimuth = math.degrees(math.atan2(
        math.sin(hour_angle),
        math.cos(hour_angle) * math.sin(lat) - math.tan(dec) * math.cos(lat),
    ))
    # Meeus measures azimuth from south; rotate to the conventional from-north reading.
    return altitude, normalize_degrees(azimuth + 180.0)


def max_altitude(declination: float, latitude: float) -> float:
    """Return the highest altitude *declination* can ever reach from *latitude*, in degrees.

    Used to detect radiants that never rise for an observer — for example the Quadrantid radiant
    at declination +49 deg is permanently below the horizon south of roughly 41 deg south.
    """
    return 90.0 - abs(latitude - declination)


# ---------------------------------------------------------------------------
# Moon
# ---------------------------------------------------------------------------

# Truncated periodic terms from Meeus ch. 47, retaining every term above ~0.01 deg. Each entry is
# (coefficient in degrees, multipliers of D, M, M', F).
_MOON_LONGITUDE_TERMS = (
    (6.288774, 0, 0, 1, 0),
    (1.274027, 2, 0, -1, 0),
    (0.658314, 2, 0, 0, 0),
    (0.213618, 0, 0, 2, 0),
    (-0.185116, 0, 1, 0, 0),
    (-0.114332, 0, 0, 0, 2),
    (0.058793, 2, 0, -2, 0),
    (0.057066, 2, -1, -1, 0),
    (0.053322, 2, 0, 1, 0),
    (0.045758, 2, -1, 0, 0),
    (-0.040923, 0, 1, -1, 0),
    (-0.034720, 1, 0, 0, 0),
    (-0.030383, 0, 1, 1, 0),
    (0.015327, 2, 0, 0, -2),
    (-0.012528, 0, 0, 1, 2),
    (0.010980, 0, 0, 1, -2),
)

_MOON_LATITUDE_TERMS = (
    (5.128122, 0, 0, 0, 1),
    (0.280602, 0, 0, 1, 1),
    (0.277693, 0, 0, 1, -1),
    (0.173237, 2, 0, 0, -1),
    (0.055413, 2, 0, -1, 1),
    (0.046271, 2, 0, -1, -1),
    (0.032573, 2, 0, 0, 1),
    (0.017198, 0, 0, 2, 1),
    (0.009266, 2, 0, 1, -1),
    (0.008822, 0, 0, 2, -1),
    (0.008216, 2, -1, 0, -1),
)


def _moon_arguments(t: float) -> Tuple[float, float, float, float, float]:
    """Return the Moon's fundamental arguments ``(L', D, M, M', F)`` in degrees."""
    mean_longitude = (
        218.3164477 + 481267.88123421 * t - 0.0015786 * t ** 2
        + t ** 3 / 538841.0 - t ** 4 / 65194000.0
    )
    elongation = (
        297.8501921 + 445267.1114034 * t - 0.0018819 * t ** 2
        + t ** 3 / 545868.0 - t ** 4 / 113065000.0
    )
    sun_anomaly = (
        357.5291092 + 35999.0502909 * t - 0.0001536 * t ** 2 + t ** 3 / 24490000.0
    )
    moon_anomaly = (
        134.9633964 + 477198.8675055 * t + 0.0087414 * t ** 2
        + t ** 3 / 69699.0 - t ** 4 / 14712000.0
    )
    latitude_argument = (
        93.2720950 + 483202.0175233 * t - 0.0036539 * t ** 2
        - t ** 3 / 3526000.0 + t ** 4 / 863310000.0
    )
    return mean_longitude, elongation, sun_anomaly, moon_anomaly, latitude_argument


def moon_ecliptic(jd: float) -> Tuple[float, float]:
    """Return the Moon's apparent ``(ecliptic_longitude, ecliptic_latitude)`` in degrees."""
    t = julian_centuries(jd)
    mean_longitude, d, m, m_prime, f = _moon_arguments(t)

    longitude_sum = 0.0
    for coefficient, cd, cm, cmp_, cf in _MOON_LONGITUDE_TERMS:
        longitude_sum += coefficient * math.sin(math.radians(cd * d + cm * m + cmp_ * m_prime + cf * f))

    latitude_sum = 0.0
    for coefficient, cd, cm, cmp_, cf in _MOON_LATITUDE_TERMS:
        latitude_sum += coefficient * math.sin(math.radians(cd * d + cm * m + cmp_ * m_prime + cf * f))

    return normalize_degrees(mean_longitude + longitude_sum), latitude_sum


def moon_equatorial(jd: float) -> Tuple[float, float]:
    """Return the Moon's apparent ``(right_ascension, declination)`` in degrees."""
    lam_deg, beta_deg = moon_ecliptic(jd)
    lam = math.radians(lam_deg)
    beta = math.radians(beta_deg)
    eps = math.radians(obliquity_of_ecliptic(jd))

    ra = math.degrees(math.atan2(
        math.sin(lam) * math.cos(eps) - math.tan(beta) * math.sin(eps),
        math.cos(lam),
    ))
    dec = math.degrees(math.asin(
        math.sin(beta) * math.cos(eps) + math.cos(beta) * math.sin(eps) * math.sin(lam)
    ))
    return normalize_degrees(ra), dec


def moon_illuminated_fraction_from(jd: float, moon_ra: float, moon_dec: float) -> float:
    """Return the illuminated fraction given an already-computed lunar position.

    :func:`moon_equatorial` is the most expensive routine in this module, so callers that already
    have the Moon's position — such as the night sampler, which also needs its altitude — pass it
    in here rather than paying for it twice per sample.
    """
    sun_ra, sun_dec = sun_equatorial(jd)
    elongation = angular_separation_degrees(sun_ra, sun_dec, moon_ra, moon_dec)
    return (1.0 - math.cos(math.radians(elongation))) / 2.0


def moon_illuminated_fraction(jd: float) -> float:
    """Return the fraction of the Moon's disc that is illuminated, ``0.0``–``1.0``.

    Uses ``k = (1 - cos(elongation)) / 2``. The rigorous form corrects the elongation to a phase
    angle using the Earth-Sun and Earth-Moon distances, but since the Sun is roughly 390 times
    further away that correction stays under a percent — irrelevant against the accuracy of any
    sky-brightness model.
    """
    moon_ra, moon_dec = moon_equatorial(jd)
    return moon_illuminated_fraction_from(jd, moon_ra, moon_dec)


def moon_altitude(jd: float, latitude: float, longitude: float) -> float:
    """Return the Moon's altitude above the horizon in degrees (negative below)."""
    ra, dec = moon_equatorial(jd)
    lst = local_sidereal_time(jd, longitude)
    altitude, _ = equatorial_to_horizontal(ra, dec, latitude, lst)
    return altitude


# ---------------------------------------------------------------------------
# Darkness
# ---------------------------------------------------------------------------

def _bisect_twilight(
    jd_dark: float,
    jd_light: float,
    latitude: float,
    longitude: float,
    threshold: float,
) -> float:
    """Return the Julian Day where sun altitude crosses *threshold* between two bracketing times."""
    for _ in range(_BISECT_ITERATIONS):
        midpoint = (jd_dark + jd_light) / 2.0
        if sun_altitude(midpoint, latitude, longitude) < threshold:
            jd_dark = midpoint
        else:
            jd_light = midpoint
    return (jd_dark + jd_light) / 2.0


def solar_noon_utc(day: date, longitude: float) -> datetime:
    """Return the approximate instant of local *solar* noon on *day*, in UTC.

    Local solar time runs ahead of UTC by ``longitude / 15`` hours, so solar noon falls that
    much earlier in UTC. This deliberately ignores the equation of time (up to ~16 minutes),
    which is irrelevant when the value is only used to centre a 24-hour search window.
    """
    utc_midnight = datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc)
    return utc_midnight + timedelta(hours=12.0 - longitude / 15.0)


def find_dark_window(
    night_of: date,
    latitude: float,
    longitude: float,
) -> Tuple[Optional[datetime], Optional[datetime], str]:
    """Return ``(start_utc, end_utc, darkness_label)`` for the night beginning on *night_of*.

    The window is searched across the 24 hours following local **solar** noon, derived from
    *longitude*. Anchoring on the observer's longitude rather than on a civil timezone means the
    search always brackets exactly one night even when Home Assistant's configured timezone
    disagrees with the configured coordinates — an instance left on UTC while pointed at
    California would otherwise have the night clipped at the window edge and report a short night.

    Darkness is found by **sampling**, not by the closed-form sunset equation. The closed form has
    no solution when the Sun never reaches the twilight altitude, which is the normal state of
    affairs at high latitude in summer; sampling degrades gracefully instead of raising. The
    fallback ladder is astronomical night, then nautical twilight, then nothing at all.
    """
    anchor = solar_noon_utc(night_of, longitude)
    jd_start = julian_day(anchor)
    jd_end = julian_day(anchor + timedelta(days=1))

    step_days = _DARK_SCAN_STEP_MINUTES / (24.0 * 60.0)
    sample_count = int(round((jd_end - jd_start) / step_days)) + 1
    samples = [jd_start + index * step_days for index in range(sample_count)]
    altitudes = [sun_altitude(jd, latitude, longitude) for jd in samples]

    for threshold, label in (
        (ASTRONOMICAL_TWILIGHT_DEG, DARKNESS_ASTRONOMICAL),
        (NAUTICAL_TWILIGHT_DEG, DARKNESS_NAUTICAL),
    ):
        run = _longest_run_below(altitudes, threshold)
        if run is None:
            continue
        first, last = run

        if first == 0:
            start_jd = samples[0]
        else:
            start_jd = _bisect_twilight(samples[first], samples[first - 1], latitude, longitude, threshold)

        if last == len(samples) - 1:
            end_jd = samples[-1]
        else:
            end_jd = _bisect_twilight(samples[last], samples[last + 1], latitude, longitude, threshold)

        return datetime_from_jd(start_jd), datetime_from_jd(end_jd), label

    return None, None, DARKNESS_NONE


def _longest_run_below(values: List[float], threshold: float) -> Optional[Tuple[int, int]]:
    """Return the ``(first, last)`` indices of the longest run of *values* below *threshold*."""
    best: Optional[Tuple[int, int]] = None
    best_length = 0
    run_start: Optional[int] = None

    for index, value in enumerate(values):
        if value < threshold:
            if run_start is None:
                run_start = index
        elif run_start is not None:
            length = index - run_start
            if length > best_length:
                best, best_length = (run_start, index - 1), length
            run_start = None

    if run_start is not None:
        length = len(values) - run_start
        if length > best_length:
            best = (run_start, len(values) - 1)

    return best
