"""Solar and lunar eclipse forecasting for NOAA It All -- pure functions, no Home Assistant.

Answers one question for one observer: **if you walk outside, what will you actually see?**

Like ``meteor.py`` this module needs nothing beyond the standard library, takes its catalog as a
**parameter** rather than importing it, and reaches ``astro`` through a small import shim so it
works both as part of the integration package and as a bare module under the test-suite.

Two eclipses, two entirely different problems
---------------------------------------------

A **lunar** eclipse is the Moon falling into Earth's shadow. Everybody on the night side sees the
same thing at the same instant, so "local circumstances" reduce to whether the Moon is above your
horizon -- and the eclipse itself can be computed from scratch with Meeus ch. 54. No catalog, no
horizon date, correct forever.

A **solar** eclipse is a shadow a few hundred kilometres wide sweeping across a rotating planet.
What you see depends on where you stand to within a few kilometres, and computing that needs
Besselian elements derived from full VSOP87/ELP2000-82 ephemerides -- far beyond what ``astro.py``
carries. Those are published, so ``eclipse_catalog.py`` bundles them and this module does the
observer-specific geometry. That is the whole reason the solar side has a finite horizon and the
lunar side does not.

The Besselian frame, in one paragraph
-------------------------------------

Put the origin at Earth's centre and point the z-axis down the shadow axis at the Moon. The
catalog's ``x``/``y`` polynomials place the axis in the remaining plane, ``d`` and ``mu`` give its
declination and Greenwich hour angle, and ``l1``/``l2`` are the radii of the penumbral and umbral
cones where they cut that plane. Project the observer into the same frame as ``(xi, eta, zeta)``,
and the distance ``m`` between observer and axis against those two radii is the entire eclipse.

Three details in that projection are load-bearing, and each was verified against NASA's own
published circumstances for all 114 catalogued eclipses rather than taken on trust:

* **Earth is an ellipsoid.** Using a spherical observer misplaces you by up to 11 arcminutes of
  latitude, which is about 20 km of shadow path -- the difference between totality and 99.4%.
* **Delta-T rotates the Earth.** The elements are polynomials in TT; a clock reads UT. The
  observer's hour angle therefore needs ``- 0.0041780 * delta_t`` degrees. Omitting it looks
  harmless and costs up to **129 seconds** of contact time; including it holds every one of the
  114 to within 20 seconds.
* **``l2`` is negative during totality.** That sign is not noise to be stripped: it is what says
  the Moon's disc is the larger one. See :func:`obscuration`.

Magnitude means two different things
------------------------------------

Eclipse *magnitude* is the covered fraction of the body's **diameter**; *obscuration* is the
covered fraction of its **area**. They are far apart -- magnitude 0.5 is only 39% obscuration --
and it is obscuration that matches what people mean by "how much of it will I see", so that is
the headline number here. Both are reported.

For solar eclipses the magnitude formula also switches at the moment you enter the shadow:
outside it, magnitude is ``(L1' - m) / (L1' + L2')``; once inside, the discs fully overlap and
magnitude becomes the ratio of their apparent diameters, ``(L1' - L2') / (L1' + L2')``. Using the
first formula throughout reproduces NASA's published magnitudes for partial eclipses exactly and
is wrong by up to 0.04 for every central one.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone, tzinfo
from typing import Any, Dict, List, Optional, Sequence, Tuple

try:  # imported as part of the integration package (Home Assistant)
    from . import astro
except ImportError:  # pragma: no cover - imported as a bare module (test-suite)
    import astro

# ---------------------------------------------------------------------------
# Vocabulary
# ---------------------------------------------------------------------------

KIND_SOLAR = "solar"
KIND_LUNAR = "lunar"

TYPE_TOTAL = "total"
TYPE_ANNULAR = "annular"
TYPE_HYBRID = "hybrid"
TYPE_PARTIAL = "partial"
TYPE_PENUMBRAL = "penumbral"
TYPE_NONE = "none"

#: Why the viewing score is not higher. Mirrors ``meteor.FACTOR_*``.
FACTOR_COVERAGE = "how little is covered"
FACTOR_ALTITUDE = "low altitude"
FACTOR_BELOW_HORIZON = "below the horizon"
FACTOR_TWILIGHT = "twilight"
FACTOR_NONE = "nothing"

#: Score bands, highest first. Defined here rather than shared with ``meteor.py``: these pure
#: modules stay independent of each other by convention, the same way ``meteor._SCORE_RATINGS``
#: and ``parsers.get_visibility_class`` already keep their own copies of the same idea.
_SCORE_RATINGS = (
    (80, "Excellent"),
    (60, "Very Good"),
    (40, "Good"),
    (20, "Fair"),
    (0, "Poor"),
)

# ---------------------------------------------------------------------------
# Model constants
# ---------------------------------------------------------------------------

#: Earth's polar/equatorial axis ratio, ``sqrt(1 - e^2)`` for the IAU 1976 ellipsoid.
_AXIS_RATIO = 0.99664719

#: Earth's equatorial radius in metres, the unit ``zeta`` and observer elevation are scaled by.
_EARTH_RADIUS_M = 6378140.0

#: Degrees of Earth rotation per second of delta-T. ``1.002738 * 15 / 3600``: sidereal rate,
#: because what is being corrected is the planet's orientation, not a clock face.
_ROTATION_DEG_PER_DELTA_T_SECOND = 0.0041780

#: Altitude at which the Sun's upper limb is on the horizon, allowing for refraction. Below this
#: an eclipse is happening but you cannot watch it.
_HORIZON_DEG = -0.833

#: The same threshold for the Moon, which is not the same number. The Moon is close enough to
#: have about 0.95 degrees of horizontal parallax, so an observer on the surface sees it roughly a
#: degree lower than a geocentric calculation puts it -- and ``astro.moon_equatorial`` is
#: geocentric. Meeus gives the standard altitude as ``h0 = 0.7275 * parallax - 0.5667``, which
#: comes out just *above* zero rather than below it, because parallax outweighs refraction and
#: semidiameter combined. Using the Sun's -0.833 here counts about five minutes per eclipse as
#: watchable while the Moon is really below the horizon, and it is exactly at this threshold that
#: a fraction of a degree decides whether an eclipse is visible at all.
_MOON_HORIZON_DEG = 0.125

#: Half-width of the window scanned for solar contacts, in hours either side of the elements'
#: reference instant. No solar eclipse runs longer than about 5.5 hours end to end anywhere on
#: Earth, and ``t0`` sits near greatest eclipse, so four hours brackets every local case.
_SOLAR_SCAN_HOURS = 4.0

#: Sampling step for the contact scan, in minutes. Fine enough that no contact is missed and no
#: maximum is more than half a step off before refinement.
_SCAN_STEP_MINUTES = 1

#: Step of the fine pass used to bracket second and third contact, in seconds. The central phase
#: can be far shorter than the main scan step -- the 2049 hybrid eclipse is total for 38 seconds
#: and the 2067 one for 8 -- so a minute-by-minute scan steps clean over it and reports a total
#: eclipse with no totality. Only run when the observer is inside the shadow, so it is cheap.
_CENTRAL_STEP_SECONDS = 2
_CENTRAL_WINDOW_MINUTES = 20

#: Step of the coarse pass that decides whether the shadow comes near the observer at all, in
#: minutes, and the margin allowed for what the fine pass might still find between two coarse
#: samples. ``m`` changes by well under 0.05 in a quarter of an hour, so 0.1 is generous.
_COARSE_STEP_MINUTES = 15
_COARSE_MARGIN = 0.1

#: Bisection iterations used to pin a contact once the scan has bracketed it. Matches
#: ``astro._BISECT_ITERATIONS``; at this bracket width it resolves to well under a second.
_BISECT_ITERATIONS = 24

#: Altitude at which the altitude term of the viewing score saturates. Below this an eclipse is
#: in the trees and the rooftops even though the geometry is perfect.
_GOOD_ALTITUDE_DEG = 15.0

#: How much of a *central* eclipse's score survives it being right on the horizon. Totality and
#: annularity are worth going outside for at any altitude at all -- people cross oceans for a
#: low-Sun totality, and the low Sun is half the spectacle, because you can watch the shadow
#: itself come at you across the landscape. Only the risk of a tree being in the way remains, and
#: that is a property of where the observer is standing rather than of the eclipse.
_CENTRAL_ALTITUDE_FLOOR = 0.65

#: What the very deepest partial eclipse can score, as a fraction of totality. Even 99.8% is a
#: different event: no corona, no darkness, and the filters stay on throughout. Madrid sits just
#: outside the 2026 path and gets exactly that.
_PARTIAL_CEILING = 0.85

#: Coarse pre-filter on the Moon's argument of latitude; outside this no eclipse is possible
#: (Meeus ch. 54). It is deliberately generous and lets through near-misses, which are then
#: rejected on their computed penumbral magnitude.
_LUNAR_NODE_LIMIT = 0.36

#: Mean synodic month in days, used only to step the lunation scan.
_SYNODIC_MONTH = 29.530588861

#: The Moon's radius in the units Meeus ch. 54 works in, where Earth's umbral and penumbral
#: radii at the Moon's distance are ``0.7403 - u`` and ``1.2848 + u``.
_LUNAR_RADIUS = 0.2725

ISO_12312_2_NOTICE = (
    "Never look at a partially eclipsed Sun without ISO 12312-2 eclipse glasses or a certified "
    "solar filter. Sunglasses, exposed film and smoked glass are not safe."
)

TOTALITY_NOTICE = (
    "During totality only -- between second and third contact -- the Sun may be viewed with the "
    "naked eye. Put the filter back on the instant the first sliver of Sun reappears."
)


# ---------------------------------------------------------------------------
# Small shared helpers
# ---------------------------------------------------------------------------

def _poly(coefficients: Sequence[float], t: float) -> float:
    """Return the polynomial *coefficients* evaluated at *t*, lowest order first."""
    total = 0.0
    for power, coefficient in enumerate(coefficients):
        total += coefficient * t ** power
    return total


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    """Return *value* confined to ``[low, high]``."""
    return max(low, min(high, value))


def _local_iso(when: Optional[datetime], tz: tzinfo) -> Optional[str]:
    """Return *when* as a local ISO-8601 string trimmed to minutes, or ``None``."""
    if when is None:
        return None
    return when.astimezone(tz).isoformat(timespec="minutes")


def _utc_iso(when: Optional[datetime]) -> Optional[str]:
    """Return *when* as a UTC ISO-8601 string trimmed to seconds, or ``None``."""
    if when is None:
        return None
    return when.astimezone(timezone.utc).isoformat(timespec="seconds")


_COMPASS = ("N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
            "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW")


def compass_direction(azimuth: float) -> str:
    """Return the sixteen-point compass name for an azimuth measured from north."""
    return _COMPASS[int((astro.normalize_degrees(azimuth) / 22.5) + 0.5) % 16]


def disc_overlap_fraction(separation: float, covered_radius: float, coverer_radius: float) -> float:
    """Return how much of one disc's **area** another disc hides, ``0.0``-``1.0``.

    Plain circle-circle geometry, and the one piece of maths shared by both halves of this
    module: a solar eclipse is the Moon's disc over the Sun's, a lunar eclipse is Earth's umbra
    over the Moon's, and once the radii and centre separation are known neither case cares which
    it is.
    """
    if covered_radius <= 0.0:
        return 0.0
    if coverer_radius <= 0.0 or separation >= covered_radius + coverer_radius:
        return 0.0
    if separation <= coverer_radius - covered_radius:
        return 1.0                                    # covered disc entirely inside the coverer
    if separation <= covered_radius - coverer_radius:
        return (coverer_radius / covered_radius) ** 2  # coverer entirely inside, annular case
    cos_covered = _clamp(
        (separation ** 2 + covered_radius ** 2 - coverer_radius ** 2)
        / (2.0 * separation * covered_radius), -1.0, 1.0,
    )
    cos_coverer = _clamp(
        (separation ** 2 + coverer_radius ** 2 - covered_radius ** 2)
        / (2.0 * separation * coverer_radius), -1.0, 1.0,
    )
    lens_area = (
        covered_radius ** 2 * (math.acos(cos_covered)
                               - cos_covered * math.sqrt(max(0.0, 1.0 - cos_covered ** 2)))
        + coverer_radius ** 2 * (math.acos(cos_coverer)
                                 - cos_coverer * math.sqrt(max(0.0, 1.0 - cos_coverer ** 2)))
    )
    return _clamp(lens_area / (math.pi * covered_radius ** 2))


# ---------------------------------------------------------------------------
# Solar: the observer in the Besselian frame
# ---------------------------------------------------------------------------

def geocentric_observer(latitude: float, elevation_m: float = 0.0) -> Tuple[float, float]:
    """Return ``(rho_sin_phi_prime, rho_cos_phi_prime)`` for an observer on the ellipsoid.

    Geodetic latitude -- what a map and Home Assistant both give you -- is the angle of the local
    vertical, not the angle at Earth's centre. The two differ by up to 11 arcminutes, and in the
    Besselian frame that is roughly 20 km of ground: enough to move somebody across the edge of a
    path of totality, which is precisely the question this module exists to answer.
    """
    latitude_rad = math.radians(latitude)
    reduced = math.atan(_AXIS_RATIO * math.tan(latitude_rad))
    height = elevation_m / _EARTH_RADIUS_M
    return (
        _AXIS_RATIO * math.sin(reduced) + height * math.sin(latitude_rad),
        math.cos(reduced) + height * math.cos(latitude_rad),
    )


def besselian_elements_at(entry: Dict[str, Any], t_hours: float) -> Tuple[float, ...]:
    """Return ``(x, y, d, mu, l1, l2)`` for an eclipse, *t_hours* from its reference instant."""
    return (
        _poly(entry["x"], t_hours),
        _poly(entry["y"], t_hours),
        _poly(entry["d"], t_hours),
        _poly(entry["mu"], t_hours),
        _poly(entry["l1"], t_hours),
        _poly(entry["l2"], t_hours),
    )


class ShadowGeometry:
    """Where the observer sits relative to the Moon's shadow at one instant.

    ``m`` is the distance from the shadow axis, ``l1`` and ``l2`` the penumbral and umbral cone
    radii corrected for the observer's height above the fundamental plane, and ``zeta`` that
    height. ``l2`` keeps its sign: negative means the umbral cone has not yet closed, so the Moon
    covers more than the Sun and the eclipse is total rather than annular.
    """

    __slots__ = ("m", "l1", "l2", "zeta")

    def __init__(self, m: float, l1: float, l2: float, zeta: float) -> None:
        self.m = m
        self.l1 = l1
        self.l2 = l2
        self.zeta = zeta


def shadow_geometry_at(
    entry: Dict[str, Any],
    t_hours: float,
    latitude: float,
    longitude: float,
    elevation_m: float = 0.0,
) -> ShadowGeometry:
    """Return the observer's :class:`ShadowGeometry` *t_hours* from the elements' reference time.

    *longitude* is east-positive, matching how Home Assistant stores it; the classical treatments
    are west-positive, which is why the sign here looks the opposite way round from the textbook.
    """
    x, y, d_deg, mu_deg, l1, l2 = besselian_elements_at(entry, t_hours)
    rho_sin, rho_cos = geocentric_observer(latitude, elevation_m)

    d = math.radians(d_deg)
    # The elements are polynomials in Terrestrial Time, but the observer is carried round by an
    # Earth that turns on UT. Rotate the hour angle back by delta-T or every contact lands late.
    hour_angle = math.radians(
        mu_deg + longitude - _ROTATION_DEG_PER_DELTA_T_SECOND * entry["delta_t"]
    )

    xi = rho_cos * math.sin(hour_angle)
    eta = rho_sin * math.cos(d) - rho_cos * math.cos(hour_angle) * math.sin(d)
    zeta = rho_sin * math.sin(d) + rho_cos * math.cos(hour_angle) * math.cos(d)

    return ShadowGeometry(
        m=math.hypot(x - xi, y - eta),
        l1=l1 - zeta * entry["tanf1"],
        l2=l2 - zeta * entry["tanf2"],
        zeta=zeta,
    )


# ---------------------------------------------------------------------------
# Solar: what the geometry means
# ---------------------------------------------------------------------------

def solar_disc_radii(geometry: ShadowGeometry) -> Tuple[float, float]:
    """Return the ``(sun_radius, moon_radius)`` implied by the two cone radii.

    This is the subtle one. ``l1`` and ``l2`` are the penumbral and umbral cone radii, and the
    apparent radii of the two discs are their half-sum and half-difference. Because ``l2`` goes
    **negative** once the umbral cone reaches past the observer, the half-difference grows and the
    half-sum shrinks -- which is exactly the statement that the Moon now looks bigger than the Sun.

    Reaching for ``abs(l2)`` as the Moon's radius instead looks reasonable and quietly reports a
    total eclipse as about 0.1% obscured.
    """
    return (geometry.l1 + geometry.l2) / 2.0, (geometry.l1 - geometry.l2) / 2.0


def obscuration(geometry: ShadowGeometry) -> float:
    """Return the fraction of the Sun's **area** the Moon hides, ``0.0``-``1.0``."""
    sun_radius, moon_radius = solar_disc_radii(geometry)
    return disc_overlap_fraction(geometry.m, sun_radius, moon_radius)


def solar_magnitude(geometry: ShadowGeometry) -> float:
    """Return the fraction of the Sun's **diameter** the Moon hides.

    Two regimes, and the switch between them matters. While any part of the Sun is still showing,
    magnitude is how far the Moon has advanced across it. Once the observer is inside the shadow
    that number has reached exactly 1.0 and can go no further, so the convention changes: the
    magnitude quoted for a central eclipse is the ratio of the two apparent **diameters**, which
    is why a total eclipse is published as 1.06 rather than 1.00.

    The value therefore **steps** at second contact, and that is correct rather than a seam to be
    smoothed over -- the two regimes report different quantities that share a name. Checked
    against NASA's published figure for every central eclipse in the catalog: the diameter ratio
    reproduces them to about 0.00002, while carrying the partial-phase form through is wrong by
    up to 0.04 for each one.
    """
    span = geometry.l1 + geometry.l2
    if span <= 0.0:
        return 0.0
    if geometry.m < abs(geometry.l2):
        return (geometry.l1 - geometry.l2) / span
    return max(0.0, (geometry.l1 - geometry.m) / span)


def local_solar_type(geometry: ShadowGeometry) -> str:
    """Return the eclipse type **this observer** sees, which is often not the headline type.

    A "total" solar eclipse is total along a strip a couple of hundred kilometres wide and merely
    partial across a whole continent either side of it. Telling somebody who will see 43% that
    there is a Total Solar Eclipse is the most misleading thing this module could do, so the type
    is always re-derived from the local geometry and the catalog's global classification is kept
    separately.
    """
    if geometry.m > geometry.l1:
        return TYPE_NONE
    if geometry.m < abs(geometry.l2):
        # Inside the shadow. Whether that is totality or an annular ring is the sign of l2, and
        # nothing else -- which is also how a hybrid eclipse resolves itself along its own path.
        return TYPE_TOTAL if geometry.l2 < 0.0 else TYPE_ANNULAR
    return TYPE_PARTIAL


# ---------------------------------------------------------------------------
# Solar: scanning the eclipse for one observer
# ---------------------------------------------------------------------------

class _SolarSample:
    """One instant of a solar eclipse as one observer experiences it.

    The Sun's horizontal position is filled in lazily. Working out where the Sun is costs far
    more than working out where the shadow is, and for most eclipses at most locations the shadow
    never arrives at all -- so the altitude is only resolved for the samples that turn out to
    matter. That is the difference between this scan costing microseconds and costing
    milliseconds, forty times over, on Home Assistant's event loop.
    """

    __slots__ = ("t", "geometry", "obscuration", "_when", "_altitude", "_azimuth")

    def __init__(self, t: float, geometry: ShadowGeometry, covered: float) -> None:
        self.t = t
        self.geometry = geometry
        self.obscuration = covered
        self._when: Optional[datetime] = None
        self._altitude: Optional[float] = None
        self._azimuth: Optional[float] = None

    def resolve(self, entry: Dict[str, Any], latitude: float, longitude: float) -> "_SolarSample":
        """Compute this sample's time and the Sun's horizontal position, once."""
        if self._altitude is None:
            self._when = _entry_time(entry, self.t)
            jd = astro.julian_day(self._when)
            right_ascension, declination = astro.sun_equatorial(jd)
            self._altitude, self._azimuth = astro.equatorial_to_horizontal(
                right_ascension, declination, latitude,
                astro.local_sidereal_time(jd, longitude),
            )
        return self

    @property
    def when(self) -> datetime:
        """Return the sample's UTC instant; only valid after :meth:`resolve`."""
        return self._when

    @property
    def altitude(self) -> float:
        """Return the Sun's altitude in degrees; only valid after :meth:`resolve`."""
        return self._altitude

    @property
    def azimuth(self) -> float:
        """Return the Sun's azimuth in degrees; only valid after :meth:`resolve`."""
        return self._azimuth

    @property
    def above_horizon(self) -> bool:
        """Return whether the Sun's upper limb is clear of the horizon."""
        return self._altitude > _HORIZON_DEG


def _entry_time(entry: Dict[str, Any], t_hours: float) -> datetime:
    """Return the UTC instant *t_hours* from an entry's reference time.

    The elements are referenced to Terrestrial Time, so the entry's own delta-T converts back to
    the UT a clock shows. That is the same delta-T used to rotate the observer's hour angle, so
    the two can never drift apart.
    """
    jd_tt = entry["t0_jd"] + t_hours / 24.0
    return astro.datetime_from_jd(jd_tt - entry["delta_t"] / 86400.0)


def _sample_solar(entry: Dict[str, Any], t_hours: float, latitude: float, longitude: float,
                  elevation_m: float) -> _SolarSample:
    """Return one sample of a solar eclipse, with the Sun's position left unresolved."""
    geometry = shadow_geometry_at(entry, t_hours, latitude, longitude, elevation_m)
    return _SolarSample(t_hours, geometry, obscuration(geometry))


def _refine_contact(entry: Dict[str, Any], latitude: float, longitude: float, elevation_m: float,
                    inside: float, outside: float, radius) -> float:
    """Return the time in hours at which ``m`` crosses *radius*, bisecting a bracketed crossing."""
    for _ in range(_BISECT_ITERATIONS):
        middle = (inside + outside) / 2.0
        geometry = shadow_geometry_at(entry, middle, latitude, longitude, elevation_m)
        if geometry.m <= radius(geometry):
            inside = middle
        else:
            outside = middle
    return (inside + outside) / 2.0


def _miss_distance(geometry: ShadowGeometry) -> float:
    """Return how far outside the penumbra the observer is; zero or less means eclipsed."""
    return geometry.m - geometry.l1


def _penumbral_radius(geometry: ShadowGeometry) -> float:
    """Return the radius that bounds any eclipse at all -- first and last contact."""
    return geometry.l1


def _umbral_radius(geometry: ShadowGeometry) -> float:
    """Return the radius that bounds the central phase -- second and third contact."""
    return abs(geometry.l2)


def _find_contacts(entry: Dict[str, Any], samples: List[_SolarSample], radius,
                   latitude: float, longitude: float, elevation_m: float) -> List[float]:
    """Return the times, in hours, at which ``m`` crosses *radius*.

    Found by scanning and bisecting rather than by the classical iterative contact formula. That
    formula carries a square root which goes imaginary for a grazing eclipse -- exactly the case
    where somebody most wants to know whether they are inside the path -- and oscillates near the
    limit. ``astro.find_dark_window`` made the same trade for the same reason: sampling degrades
    into a slightly imprecise answer where the closed form degrades into an exception.
    """
    crossings: List[float] = []
    previous: Optional[Tuple[float, bool]] = None
    for sample in samples:
        inside = sample.geometry.m <= radius(sample.geometry)
        if previous is not None and previous[1] != inside:
            before, was_inside = previous
            crossings.append(_refine_contact(
                entry, latitude, longitude, elevation_m,
                before if was_inside else sample.t,
                sample.t if was_inside else before,
                radius,
            ))
        previous = (sample.t, inside)
    return crossings


def _central_contacts(entry: Dict[str, Any], peak: "_SolarSample", latitude: float,
                      longitude: float, elevation_m: float) -> List[float]:
    """Return second and third contact, scanned finely around the peak.

    Split out from the main scan because the central phase operates on a completely different
    timescale from the partial one. A partial phase runs for hours; totality can run for eight
    seconds. Sampling both at the same rate would either miss the short totalities or make every
    eclipse cost thirty times more, so the fine pass is confined to a few minutes either side of
    maximum and only runs when the observer is actually inside the shadow.
    """
    if local_solar_type(peak.geometry) not in (TYPE_TOTAL, TYPE_ANNULAR):
        return []
    step = _CENTRAL_STEP_SECONDS / 3600.0
    half = _CENTRAL_WINDOW_MINUTES / 60.0
    count = int(round(2.0 * half / step)) + 1
    fine = [
        _sample_solar(entry, peak.t - half + index * step, latitude, longitude, elevation_m)
        for index in range(count)
    ]
    return _find_contacts(entry, fine, _umbral_radius, latitude, longitude, elevation_m)


def _refine_maximum(entry: Dict[str, Any], latitude: float, longitude: float, elevation_m: float,
                    low: float, high: float) -> float:
    """Return the time of greatest eclipse, by ternary search on the distance from the axis.

    ``m`` is smooth and has a single minimum across the window, so a ternary search converges
    without needing a derivative -- and unlike a parabolic fit it cannot be thrown by the flat
    plateau of obscuration that a total eclipse produces.
    """
    for _ in range(_BISECT_ITERATIONS * 2):
        first = low + (high - low) / 3.0
        second = high - (high - low) / 3.0
        m_first = shadow_geometry_at(entry, first, latitude, longitude, elevation_m).m
        m_second = shadow_geometry_at(entry, second, latitude, longitude, elevation_m).m
        if m_first < m_second:
            high = second
        else:
            low = first
    return (low + high) / 2.0


def solar_local_circumstances(
    entry: Dict[str, Any],
    latitude: float,
    longitude: float,
    elevation_m: float = 0.0,
) -> Dict[str, Any]:
    """Return everything one observer needs to know about one solar eclipse.

    Always returns a dict, never ``None``: "you will see nothing" is an answer people need, and
    it needs to say *which* nothing. An eclipse can miss you because the shadow never comes near
    your longitude, or because it comes exactly to your longitude while the Sun is on the other
    side of the planet, and those are told apart here rather than collapsed into one silence.
    """
    missed = {
        "visible": False,
        "reason": "outside the shadow",
        "local_type": TYPE_NONE,
        "obscuration": 0.0,
        "magnitude": 0.0,
    }

    # Most eclipses miss most observers -- from a fixed site only about one catalogued solar
    # eclipse in three produces any obscuration at all -- so spend a coarse pass ruling that out
    # before paying for the fine one. Sixty samples instead of eight hundred, and the margin
    # covers anything the coarse step could have stepped over.
    coarse = _COARSE_STEP_MINUTES / 60.0
    coarse_count = int(round(2.0 * _SOLAR_SCAN_HOURS / coarse)) + 1
    nearest = min(
        _miss_distance(shadow_geometry_at(entry, -_SOLAR_SCAN_HOURS + index * coarse,
                                          latitude, longitude, elevation_m))
        for index in range(coarse_count)
    )
    if nearest > _COARSE_MARGIN:
        return missed

    step = _SCAN_STEP_MINUTES / 60.0
    count = int(round(2.0 * _SOLAR_SCAN_HOURS / step)) + 1
    samples = [
        _sample_solar(entry, -_SOLAR_SCAN_HOURS + index * step, latitude, longitude, elevation_m)
        for index in range(count)
    ]

    eclipsed = [sample for sample in samples if sample.geometry.m <= sample.geometry.l1]
    if not eclipsed:
        return missed

    peak_t = _refine_maximum(entry, latitude, longitude, elevation_m,
                             eclipsed[0].t, eclipsed[-1].t)
    peak = _sample_solar(entry, peak_t, latitude, longitude, elevation_m)
    peak.resolve(entry, latitude, longitude)

    outer = _find_contacts(entry, samples, _penumbral_radius, latitude, longitude, elevation_m)
    inner = _central_contacts(entry, peak, latitude, longitude, elevation_m)

    start_t = outer[0] if outer else eclipsed[0].t
    end_t = outer[-1] if len(outer) > 1 else eclipsed[-1].t
    central_start_t = inner[0] if inner else None
    central_end_t = inner[-1] if len(inner) > 1 else None

    # What is actually watchable: the geometry above, clipped to the Sun being up. Sampling the
    # altitude rather than solving for sunrise keeps one code path for the polar cases, where
    # sunrise may not exist at all -- the same reasoning as astro.find_dark_window.
    during = [s.resolve(entry, latitude, longitude)
              for s in eclipsed if start_t <= s.t <= end_t]
    watchable = [s for s in during if s.above_horizon]
    best = (max(watchable, key=lambda s: (round(s.obscuration, 4), s.altitude))
            if watchable else None)

    duration = (end_t - start_t) * 3600.0
    visible_fraction = (len(watchable) / len(during)) if during else 0.0

    result: Dict[str, Any] = {
        "visible": best is not None,
        "reason": None if best is not None else "below the horizon",
        "local_type": local_solar_type(peak.geometry),
        "global_type": entry["type"],
        "obscuration": peak.obscuration,
        "magnitude": solar_magnitude(peak.geometry),
        "start_utc": _entry_time(entry, start_t),
        "max_utc": peak.when,
        "end_utc": _entry_time(entry, end_t),
        "central_start_utc": _entry_time(entry, central_start_t) if central_start_t else None,
        "central_end_utc": _entry_time(entry, central_end_t) if central_end_t else None,
        "central_duration_s": (
            int(round((central_end_t - central_start_t) * 3600.0))
            if central_start_t is not None and central_end_t is not None else 0
        ),
        "duration_s": int(round(duration)),
        "altitude_at_max": peak.altitude,
        "azimuth_at_max": peak.azimuth,
        "above_horizon_at_max": peak.above_horizon,
        "visible_fraction": _clamp(visible_fraction),
        "gamma": entry["gamma"],
        "path_width_km": entry["path_width_km"],
    }

    if best is None:
        # The shadow does reach this longitude, but not while the Sun is up here. Report the
        # geometry honestly and zero out what the observer gets, rather than advertising a
        # percentage for an eclipse happening under their feet.
        result.update({
            "visible_obscuration": 0.0,
            "visible_type": TYPE_NONE,
            "visible_start_utc": None,
            "visible_end_utc": None,
            "visible_altitude": peak.altitude,
            "visible_azimuth": peak.azimuth,
        })
    else:
        # Where the Sun is already up at first contact the watchable window simply *is* the
        # eclipse, so it takes the precisely bisected contact time rather than the first sample
        # of the scan grid -- which is up to a minute late, and this is the instant the whole
        # point of which is telling somebody when to walk outside. Only a Sun that rises or sets
        # mid-eclipse falls back to the sampled crossing.
        result.update({
            "visible_obscuration": best.obscuration,
            # Classified from the refined peak whenever the peak is itself above the horizon,
            # because the central phase is centred on it. Reading the type off the nearest
            # one-minute sample instead loses any totality shorter than the sampling step -- the
            # 2049 hybrid is total for 38 seconds, the 2067 one for 8 -- and reports a partial
            # eclipse while still publishing the totality window as an attribute.
            "visible_type": local_solar_type(
                peak.geometry if peak.above_horizon else best.geometry
            ),
            "visible_start_utc": (
                watchable[0].when if during[0] is not watchable[0]
                else _entry_time(entry, start_t)
            ),
            "visible_end_utc": (
                watchable[-1].when if during[-1] is not watchable[-1]
                else _entry_time(entry, end_t)
            ),
            # See the note in lunar_local_circumstances: an eclipse that starts before sunrise or
            # runs past sunset has its best watchable moment somewhere other than its maximum.
            "visible_altitude": best.altitude,
            "visible_azimuth": best.azimuth,
        })
    result["in_progress_at_rise"] = bool(watchable) and not during[0].above_horizon
    result["in_progress_at_set"] = bool(watchable) and not during[-1].above_horizon
    return result


# ---------------------------------------------------------------------------
# Lunar: Meeus chapter 54, no catalog required
# ---------------------------------------------------------------------------

def _lunation_for(when: datetime) -> float:
    """Return an approximate lunation number for *when*, the seed for the eclipse scan."""
    return (astro.julian_day(when) - 2451550.09766) / _SYNODIC_MONTH


def lunar_eclipse_at_lunation(k: int) -> Optional[Dict[str, Any]]:
    """Return the lunar eclipse at full moon *k*, or ``None`` if that full moon has none.

    Meeus ch. 54. Earth's shadow is a target the Moon only hits when full moon happens near a
    node of its orbit, so most lunations return ``None``. The ``|sin F|`` test is a coarse first
    cut that deliberately lets near-misses through; they are rejected afterwards on their computed
    penumbral magnitude, which is the real criterion. Filtering on ``sin F`` alone ships phantom
    eclipses.

    Times come out in Terrestrial Time and are converted to UT here, so nothing downstream has to
    remember which scale it is holding.
    """
    k = k + 0.5                       # +0.5 selects full moon; new moon is the integer
    t = k / 1236.85

    jde = (
        2451550.09766 + _SYNODIC_MONTH * k
        + 0.00015437 * t ** 2 - 0.000000150 * t ** 3 + 0.00000000073 * t ** 4
    )
    e = 1.0 - 0.002516 * t - 0.0000074 * t ** 2
    sun_anomaly = math.radians(2.5534 + 29.10535670 * k
                               - 0.0000014 * t ** 2 - 0.00000011 * t ** 3)
    moon_anomaly = math.radians(201.5643 + 385.81693528 * k + 0.0107582 * t ** 2
                                + 0.00001238 * t ** 3 - 0.000000058 * t ** 4)
    latitude_argument = math.radians(160.7108 + 390.67050284 * k - 0.0016118 * t ** 2
                                     - 0.00000227 * t ** 3 + 0.000000011 * t ** 4)
    node = math.radians(124.7746 - 1.56375588 * k
                        + 0.0020672 * t ** 2 + 0.00000215 * t ** 3)

    if abs(math.sin(latitude_argument)) > _LUNAR_NODE_LIMIT:
        return None

    f1 = latitude_argument - math.radians(0.02665) * math.sin(node)
    a1 = math.radians(299.77 + 0.107408 * k - 0.009173 * t ** 2)
    sin, cos = math.sin, math.cos

    jde += (
        -0.4065 * sin(moon_anomaly)
        + 0.1727 * e * sin(sun_anomaly)
        + 0.0161 * sin(2 * moon_anomaly)
        - 0.0097 * sin(2 * f1)
        + 0.0073 * e * sin(moon_anomaly - sun_anomaly)
        - 0.0050 * e * sin(moon_anomaly + sun_anomaly)
        - 0.0023 * sin(moon_anomaly - 2 * f1)
        + 0.0021 * e * sin(2 * sun_anomaly)
        + 0.0012 * sin(moon_anomaly + 2 * f1)
        + 0.0006 * e * sin(2 * moon_anomaly + sun_anomaly)
        - 0.0004 * sin(3 * moon_anomaly)
        - 0.0003 * e * sin(sun_anomaly + 2 * f1)
        + 0.0003 * sin(a1)
        - 0.0002 * e * sin(sun_anomaly - 2 * f1)
        - 0.0002 * e * sin(2 * moon_anomaly - sun_anomaly)
        - 0.0002 * sin(node)
    )

    p = (
        0.2070 * e * sin(sun_anomaly) + 0.0024 * e * sin(2 * sun_anomaly)
        - 0.0392 * sin(moon_anomaly) + 0.0116 * sin(2 * moon_anomaly)
        - 0.0073 * e * sin(moon_anomaly + sun_anomaly)
        + 0.0067 * e * sin(moon_anomaly - sun_anomaly) + 0.0118 * sin(2 * f1)
    )
    q = (
        5.2207 - 0.0048 * e * cos(sun_anomaly) + 0.0020 * e * cos(2 * sun_anomaly)
        - 0.3299 * cos(moon_anomaly) - 0.0060 * e * cos(moon_anomaly + sun_anomaly)
        + 0.0041 * e * cos(moon_anomaly - sun_anomaly)
    )
    w = abs(cos(f1))
    gamma = (p * cos(f1) + q * sin(f1)) * (1.0 - 0.0048 * w)
    u = (
        0.0059 + 0.0046 * e * cos(sun_anomaly) - 0.0182 * cos(moon_anomaly)
        + 0.0004 * cos(2 * moon_anomaly) - 0.0005 * e * cos(sun_anomaly + moon_anomaly)
    )

    penumbral_magnitude = (1.5573 + u - abs(gamma)) / 0.5450
    if penumbral_magnitude <= 0.0:
        return None                    # a genuine near-miss the sin F cut let through
    umbral_magnitude = (1.0128 - u - abs(gamma)) / 0.5450

    # Semi-durations, Meeus's rates. n is the Moon's hourly motion relative to the shadow.
    n = 0.5458 + 0.0400 * cos(moon_anomaly)

    def semi_duration(radius: float) -> float:
        """Return half the length of a phase of the given radius, in minutes."""
        return (60.0 / n) * math.sqrt(max(0.0, radius ** 2 - gamma ** 2))

    if umbral_magnitude >= 1.0:
        eclipse_type = TYPE_TOTAL
    elif umbral_magnitude > 0.0:
        eclipse_type = TYPE_PARTIAL
    else:
        eclipse_type = TYPE_PENUMBRAL

    greatest = astro.datetime_from_jd(jde)
    greatest -= timedelta(seconds=astro.delta_t_seconds(astro.year_fraction(greatest)))

    return {
        "kind": KIND_LUNAR,
        "type": eclipse_type,
        "greatest_utc": greatest,
        "gamma": gamma,
        "umbral_magnitude": umbral_magnitude,
        "penumbral_magnitude": penumbral_magnitude,
        "umbral_radius": 0.7403 - u,
        "penumbral_radius": 1.2848 + u,
        "penumbral_semi_duration_min": semi_duration(1.5573 + u),
        "partial_semi_duration_min": semi_duration(1.0128 - u) if umbral_magnitude > 0.0 else 0.0,
        "total_semi_duration_min": semi_duration(0.4678 - u) if umbral_magnitude >= 1.0 else 0.0,
    }


def lunar_eclipses_between(start: datetime, end: datetime) -> List[Dict[str, Any]]:
    """Return every lunar eclipse whose greatest phase falls between *start* and *end*.

    Needs no catalog and has no horizon: unlike the solar side this stays correct for as far
    ahead as anyone cares to ask.
    """
    if end < start:
        return []
    first = int(math.floor(_lunation_for(start))) - 2
    last = int(math.ceil(_lunation_for(end))) + 2
    found = []
    for k in range(first, last + 1):
        eclipse_ = lunar_eclipse_at_lunation(k)
        if eclipse_ is not None and start <= eclipse_["greatest_utc"] <= end:
            found.append(eclipse_)
    found.sort(key=lambda item: item["greatest_utc"])
    return found


def lunar_shadow_separation(eclipse_: Dict[str, Any], minutes_from_greatest: float) -> float:
    """Return the Moon's distance from the shadow axis, in Meeus's shadow-radius units.

    The Moon crosses the shadow in what is very nearly a straight line at a very nearly constant
    rate, so its distance from the axis is the hypotenuse of the least distance ``gamma`` and how
    far it has travelled along its track. That is the same geometry the semi-duration formulae
    encode, used forwards instead of backwards.
    """
    rate = eclipse_["penumbral_semi_duration_min"]
    span = eclipse_["penumbral_radius"] + _LUNAR_RADIUS
    if rate <= 0.0:
        return abs(eclipse_["gamma"])
    along = math.sqrt(max(0.0, span ** 2 - eclipse_["gamma"] ** 2)) * (minutes_from_greatest / rate)
    return math.hypot(eclipse_["gamma"], along)


def lunar_magnitudes_at(eclipse_: Dict[str, Any],
                        minutes_from_greatest: float = 0.0) -> Tuple[float, float]:
    """Return the ``(umbral, penumbral)`` magnitudes at an offset from greatest eclipse.

    Both are diameter fractions of the Moon, on the same footing as the values Meeus gives for
    greatest eclipse -- at an offset of zero these reproduce them exactly. They exist so that what
    an observer sees can be classified from the part of the eclipse that happens above their
    horizon, rather than from the eclipse as a whole: a Moon that rises after the last umbral
    contact witnesses a penumbral smudge, whatever the almanac calls the event.
    """
    separation = lunar_shadow_separation(eclipse_, minutes_from_greatest)
    return (
        (eclipse_["umbral_radius"] + _LUNAR_RADIUS - separation) / (2.0 * _LUNAR_RADIUS),
        (eclipse_["penumbral_radius"] + _LUNAR_RADIUS - separation) / (2.0 * _LUNAR_RADIUS),
    )


def lunar_type_for(umbral_magnitude: float, penumbral_magnitude: float) -> str:
    """Return the eclipse type implied by a pair of magnitudes."""
    if umbral_magnitude >= 1.0:
        return TYPE_TOTAL
    if umbral_magnitude > 0.0:
        return TYPE_PARTIAL
    if penumbral_magnitude > 0.0:
        return TYPE_PENUMBRAL
    return TYPE_NONE


def lunar_coverage(eclipse_: Dict[str, Any], minutes_from_greatest: float = 0.0) -> float:
    """Return the fraction of the Moon's **area** inside the umbra, ``0.0``-``1.0``."""
    return disc_overlap_fraction(
        lunar_shadow_separation(eclipse_, minutes_from_greatest),
        _LUNAR_RADIUS,
        eclipse_["umbral_radius"],
    )


def _sun_altitude_at(when: datetime, latitude: float, longitude: float) -> float:
    """Return the Sun's altitude at *when*, for the sky-brightness term of a lunar eclipse."""
    return astro.sun_altitude(astro.julian_day(when), latitude, longitude)


def lunar_local_circumstances(
    eclipse_: Dict[str, Any],
    latitude: float,
    longitude: float,
) -> Dict[str, Any]:
    """Return what one observer gets of a lunar eclipse.

    A lunar eclipse is the same event everywhere -- the Moon really is in shadow, and every
    observer who can see the Moon at all sees the identical thing at the identical instant. So
    the only local question is whether the Moon is up, which is why this needs none of the
    machinery the solar side does.
    """
    greatest = eclipse_["greatest_utc"]
    half_window = eclipse_["penumbral_semi_duration_min"]

    step = 2.0
    offsets = [-half_window + index * step
               for index in range(int(2.0 * half_window / step) + 1)]
    if not offsets or offsets[-1] < half_window:
        offsets.append(half_window)

    above: List[Tuple[float, datetime, float, float, float]] = []
    total = 0
    for offset in offsets:
        when = greatest + timedelta(minutes=offset)
        jd = astro.julian_day(when)
        right_ascension, declination = astro.moon_equatorial(jd)
        altitude, azimuth = astro.equatorial_to_horizontal(
            right_ascension, declination, latitude, astro.local_sidereal_time(jd, longitude),
        )
        total += 1
        if altitude > _MOON_HORIZON_DEG:
            _, penumbral = lunar_magnitudes_at(eclipse_, offset)
            above.append((offset, when, altitude, azimuth,
                          lunar_coverage(eclipse_, offset), penumbral))

    jd_greatest = astro.julian_day(greatest)
    right_ascension, declination = astro.moon_equatorial(jd_greatest)
    altitude_at_max, azimuth_at_max = astro.equatorial_to_horizontal(
        right_ascension, declination, latitude,
        astro.local_sidereal_time(jd_greatest, longitude),
    )
    # A lunar eclipse in a bright sky is a washed-out one, and the Moon is by definition opposite
    # the Sun, so this is only ever an issue near rise and set -- and in the polar summer, where
    # the Moon can be up in a sky that never gets dark at all.
    sun_altitude = astro.sun_altitude(jd_greatest, latitude, longitude)

    def phase_bounds(semi_duration: float) -> Tuple[Optional[datetime], Optional[datetime]]:
        """Return the start and end of a phase given its semi-duration in minutes."""
        if semi_duration <= 0.0:
            return None, None
        return (greatest - timedelta(minutes=semi_duration),
                greatest + timedelta(minutes=semi_duration))

    start_utc, end_utc = phase_bounds(half_window)
    partial_start, partial_end = phase_bounds(eclipse_["partial_semi_duration_min"])
    total_start, total_end = phase_bounds(eclipse_["total_semi_duration_min"])

    def _merit(sample):
        """Rank one watchable moment: umbral coverage, then penumbral depth, then altitude.

        The penumbral rung applies *only* where no umbral phase is visible at all. It is there
        for the site that catches nothing but the penumbral tail, which has zero coverage
        throughout and would otherwise rank straight to altitude and pick the last sample of the
        night, by which point the penumbra has all but gone. Letting it rank alongside coverage
        instead breaks the case it was meant to leave alone: through totality every sample is
        100% covered but the penumbral magnitude still peaks at greatest eclipse, so a setting
        Moon would be pinned to its lowest total moment rather than its highest.
        """
        _, _, altitude, _, coverage, penumbral = sample
        return (
            round(coverage, 4),
            round(penumbral, 4) if coverage <= 0.0 else 0.0,
            altitude,
        )

    best = max(above, key=_merit) if above else None
    # What is seen, classified from the moment it is seen. Without this a site whose Moon rises
    # after the last umbral contact is told it watched a total lunar eclipse while being shown
    # nought per cent covered -- the same eclipse-versus-your-eclipse split the solar side makes.
    if best is None:
        visible_umbral, visible_penumbral = 0.0, 0.0
    else:
        visible_umbral, visible_penumbral = lunar_magnitudes_at(eclipse_, best[0])

    return {
        "visible": best is not None,
        "reason": None if best is not None else "below the horizon",
        "local_type": eclipse_["type"],
        "global_type": eclipse_["type"],
        "obscuration": lunar_coverage(eclipse_),
        "magnitude": eclipse_["umbral_magnitude"],
        "umbral_magnitude": eclipse_["umbral_magnitude"],
        "penumbral_magnitude": eclipse_["penumbral_magnitude"],
        "start_utc": start_utc,
        "max_utc": greatest,
        "end_utc": end_utc,
        "partial_start_utc": partial_start,
        "partial_end_utc": partial_end,
        "central_start_utc": total_start,
        "central_end_utc": total_end,
        "central_duration_s": int(round(eclipse_["total_semi_duration_min"] * 120.0)),
        "duration_s": int(round(half_window * 120.0)),
        "altitude_at_max": altitude_at_max,
        "azimuth_at_max": azimuth_at_max,
        "above_horizon_at_max": altitude_at_max > _MOON_HORIZON_DEG,
        "sun_altitude_at_max": sun_altitude,
        "visible_sun_altitude": _sun_altitude_at(
            best[1] if best else greatest, latitude, longitude,
        ),
        "visible_fraction": (len(above) / total) if total else 0.0,
        "gamma": eclipse_["gamma"],
        "visible_obscuration": best[4] if best else 0.0,
        "visible_type": (
            lunar_type_for(visible_umbral, visible_penumbral) if best else TYPE_NONE
        ),
        "visible_umbral_magnitude": visible_umbral,
        "visible_penumbral_magnitude": visible_penumbral,
        # The geometry at the moment worth watching, which is not the geometry at greatest
        # eclipse whenever the Moon sets partway through. Scoring and "where do I look" both
        # need this one; reporting the other sends people to a horizon the Moon set behind.
        "visible_altitude": best[2] if best else altitude_at_max,
        "visible_azimuth": best[3] if best else azimuth_at_max,
        # Same rule as the solar side: a Moon that is up when the eclipse begins gives a
        # watchable window that starts with the eclipse itself, not with the first sample.
        "visible_start_utc": (
            None if not above
            else (start_utc if above[0][0] == offsets[0] else above[0][1])
        ),
        "visible_end_utc": (
            None if not above
            else (end_utc if above[-1][0] == offsets[-1] else above[-1][1])
        ),
        "in_progress_at_rise": bool(above) and offsets[0] < above[0][0],
        "in_progress_at_set": bool(above) and offsets[-1] > above[-1][0],
        "path_width_km": 0.0,
    }


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def altitude_factor(altitude: float) -> float:
    """Return how much of an eclipse's potential survives being this low in the sky.

    Zero at the horizon, rising to one by :data:`_GOOD_ALTITUDE_DEG`. Geometry does not care how
    high the Sun is, but observers do: an eclipse four degrees up is behind the treeline, in the
    haze, and over somebody's roof. The 2026 total solar eclipse is the standing example -- it is
    genuinely total in Valencia, with the Sun four degrees off the horizon.
    """
    if altitude <= _HORIZON_DEG:
        return 0.0
    ratio = (math.sin(math.radians(max(0.0, altitude)))
             / math.sin(math.radians(_GOOD_ALTITUDE_DEG)))
    # Square-rooted, so altitude matters without dominating. Straight sine is far too steep down
    # here: it makes the difference between a Sun seven degrees up and one ten degrees up worth
    # more than the difference between a 91% eclipse and a 99.8% one, which is nonsense. The same
    # taper is used on the moonlight term in ``meteor.moon_penalty``, for the same reason.
    return _clamp(math.sqrt(_clamp(ratio)))


def darkness_factor(sun_altitude: float) -> float:
    """Return how much of a lunar eclipse survives the sky not being properly dark.

    A totally eclipsed Moon is a dim red ember, perhaps a thousand times fainter than a full one,
    so it needs a dark sky in a way that a solar eclipse -- which supplies its own -- does not.
    Full value once the Sun is below astronomical twilight, tapering to a third in daylight.
    """
    if sun_altitude <= astro.ASTRONOMICAL_TWILIGHT_DEG:
        return 1.0
    if sun_altitude >= 0.0:
        return 0.3
    return 0.3 + 0.7 * (sun_altitude / astro.ASTRONOMICAL_TWILIGHT_DEG)


def solar_viewing_score(covered: float, local_type: str, altitude: float) -> int:
    """Return a 0-100 score for how worthwhile a solar eclipse is from here.

    Unlike ``meteor.viewing_score`` this deliberately does **not** factor out the strength of the
    event. It cannot: whether the Moon covers 12% of the Sun or all of it is the single most
    important thing about a solar eclipse, and a score that ignored it would rate a barely
    perceptible nibble under a perfect sky as highly as totality.

    The partial term is cubic, and that is the honest shape. Daylight falls off far more slowly
    than covered area -- at 50% obscuration the light has dimmed by a percent or so, and almost
    nobody notices without a filter -- while the last few percent are where everything happens.
    A linear score would badly oversell the ordinary partial eclipse most people will get, and
    equally undersell the near-miss.

    Altitude is treated very differently either side of that divide. A partial eclipse low in the
    sky is simply a poor one. A *total* eclipse low in the sky is still a total eclipse, so its
    altitude term is floored rather than scaled -- without that, the 2026 totality over northern
    Spain, which is the best thing to happen to European observers in decades, would be scored
    merely "Good" for the crime of happening at eight degrees.
    """
    if local_type in (TYPE_TOTAL, TYPE_ANNULAR):
        base = 1.0 if local_type == TYPE_TOTAL else 0.9
        # Floored rather than scaled: see _CENTRAL_ALTITUDE_FLOOR.
        sky = _CENTRAL_ALTITUDE_FLOOR + (1.0 - _CENTRAL_ALTITUDE_FLOOR) * altitude_factor(altitude)
        if altitude <= _HORIZON_DEG:
            sky = 0.0
    elif local_type == TYPE_PARTIAL:
        base = _PARTIAL_CEILING * _clamp(covered) ** 3
        sky = altitude_factor(altitude)
    else:
        return 0
    return int(round(_clamp(base * sky) * 100))


def lunar_viewing_score(umbral_magnitude: float, penumbral_magnitude: float,
                        altitude: float, sun_altitude: float) -> int:
    """Return a 0-100 score for how worthwhile a lunar eclipse is from here.

    Scaled on umbral magnitude rather than covered area because that is what tracks the visual
    impression: the Moon is obviously bitten well before half its area is in shadow. A penumbral
    eclipse is scored at a tenth, which is generous -- most observers cannot see one at all.
    """
    if umbral_magnitude >= 1.0:
        base = 1.0
    elif umbral_magnitude > 0.0:
        base = _clamp(umbral_magnitude)
    else:
        base = 0.1 * _clamp(penumbral_magnitude)
    return int(round(
        _clamp(base * altitude_factor(altitude) * darkness_factor(sun_altitude)) * 100
    ))


def score_rating(score: int) -> str:
    """Return a human-readable rating band for a viewing *score*."""
    for threshold, label in _SCORE_RATINGS:
        if score >= threshold:
            return label
    return _SCORE_RATINGS[-1][1]


def limiting_factor(circumstances: Dict[str, Any]) -> str:
    """Return whichever condition is costing this observer the most.

    Ranked by how much of the ideal each removes, so the answers compare directly -- the same
    approach ``meteor.limiting_factor`` takes.
    """
    if not circumstances.get("visible"):
        return FACTOR_BELOW_HORIZON
    altitude = circumstances.get("visible_altitude", circumstances.get("altitude_at_max", 0.0))
    losses = [
        (1.0 - _clamp(circumstances.get("visible_obscuration", 0.0)), FACTOR_COVERAGE),
        (1.0 - altitude_factor(altitude), FACTOR_ALTITUDE),
    ]
    sun_altitude = circumstances.get(
        "visible_sun_altitude", circumstances.get("sun_altitude_at_max"),
    )
    if sun_altitude is not None:
        losses.append((1.0 - darkness_factor(sun_altitude), FACTOR_TWILIGHT))
    loss, factor = max(losses, key=lambda item: item[0])
    return factor if loss > 0.01 else FACTOR_NONE


# ---------------------------------------------------------------------------
# Forecast assembly
# ---------------------------------------------------------------------------

_DISPLAY_NAMES = {
    (KIND_SOLAR, TYPE_TOTAL): "Total Solar Eclipse",
    (KIND_SOLAR, TYPE_ANNULAR): "Annular Solar Eclipse",
    (KIND_SOLAR, TYPE_HYBRID): "Hybrid Solar Eclipse",
    (KIND_SOLAR, TYPE_PARTIAL): "Partial Solar Eclipse",
    (KIND_SOLAR, TYPE_NONE): "Solar Eclipse (not visible here)",
    (KIND_LUNAR, TYPE_TOTAL): "Total Lunar Eclipse",
    (KIND_LUNAR, TYPE_PARTIAL): "Partial Lunar Eclipse",
    (KIND_LUNAR, TYPE_PENUMBRAL): "Penumbral Lunar Eclipse",
    (KIND_LUNAR, TYPE_NONE): "Lunar Eclipse (not visible here)",
}


def display_name(kind: str, local_type: str) -> str:
    """Return the human-readable name of an eclipse **as this observer sees it**."""
    return _DISPLAY_NAMES.get((kind, local_type), "Eclipse")


def _eye_safety(kind: str, local_type: str) -> Dict[str, Any]:
    """Return the eye-safety fields for an eclipse.

    The gate is totality and nothing else. An **annular** eclipse never becomes safe to look at
    -- at maximum there is still a complete ring of photosphere, which is roughly as damaging as
    the uneclipsed Sun -- and neither does a 99% partial. Treating "central phase" as the
    permission to remove a filter would tell people to stare at an annular eclipse, so this keys
    strictly on the local type being total.
    """
    if kind == KIND_LUNAR:
        return {
            "eye_protection_required": False,
            "safe_unfiltered": True,
            "eye_safety": "A lunar eclipse is completely safe to watch with the naked eye.",
        }
    return {
        "eye_protection_required": True,
        "safe_unfiltered": local_type == TYPE_TOTAL,
        "eye_safety": (
            ISO_12312_2_NOTICE + " " + TOTALITY_NOTICE
            if local_type == TYPE_TOTAL else ISO_12312_2_NOTICE
        ),
    }


def _build_entry(kind: str, circumstances: Dict[str, Any], now: datetime, tz: tzinfo,
                 date_label: str) -> Dict[str, Any]:
    """Return the rendered payload for one eclipse, ready for an entity to read straight out."""
    covered = circumstances.get("visible_obscuration", 0.0)
    local_type = circumstances.get("visible_type") or circumstances.get("local_type", TYPE_NONE)
    # Everything scored here describes the eclipse the observer can actually watch, so the
    # altitude has to come from that same moment. Taking it from greatest eclipse instead scores
    # a totally eclipsed Moon that is up for three hours as zero, because by the instant of
    # maximum it has set.
    altitude = circumstances.get("visible_altitude", circumstances.get("altitude_at_max", 0.0))

    if not circumstances.get("visible"):
        score = 0
    elif kind == KIND_SOLAR:
        score = solar_viewing_score(covered, local_type, altitude)
    else:
        score = lunar_viewing_score(
            circumstances.get("visible_umbral_magnitude",
                              circumstances.get("umbral_magnitude", 0.0)),
            circumstances.get("visible_penumbral_magnitude",
                              circumstances.get("penumbral_magnitude", 0.0)),
            altitude,
            circumstances.get("visible_sun_altitude",
                              circumstances.get("sun_altitude_at_max", -90.0)),
        )

    visible_azimuth = circumstances.get(
        "visible_azimuth", circumstances.get("azimuth_at_max", 0.0),
    )
    maximum = circumstances["max_utc"]
    start = circumstances.get("start_utc") or maximum
    end = circumstances.get("end_utc") or maximum
    # "In progress" has to mean *watchable* now, not merely between first and last contact. The
    # geometric window runs on regardless of whether the body has set: for New York's 2026-03-03
    # lunar eclipse it continues for nearly three hours after moonset, and an alert keyed to it
    # spends all of that telling somebody to go outside and look at a Moon that is not there --
    # while the coordinator holds its one-minute polling to do it.
    watch_from = circumstances.get("visible_start_utc") or start
    watch_until = circumstances.get("visible_end_utc") or end
    safety = _eye_safety(kind, local_type)

    entry = {
        "kind": kind,
        "type": local_type,
        "global_type": circumstances.get("global_type"),
        "name": display_name(kind, local_type),
        "date": date_label,
        "visible": bool(circumstances.get("visible")),
        "not_visible_reason": circumstances.get("reason"),
        "in_progress": watch_from <= now <= watch_until,

        "disc_covered": round(_clamp(covered) * 100.0, 1),
        "peak_disc_covered": round(_clamp(circumstances.get("obscuration", 0.0)) * 100.0, 1),
        "magnitude": round(circumstances.get("magnitude", 0.0), 4),
        "umbral_magnitude": (
            round(circumstances["umbral_magnitude"], 4)
            if "umbral_magnitude" in circumstances else None
        ),
        "penumbral_magnitude": (
            round(circumstances["penumbral_magnitude"], 4)
            if "penumbral_magnitude" in circumstances else None
        ),
        "gamma": round(circumstances.get("gamma", 0.0), 4),

        "viewing_score": score,
        "rating": score_rating(score),
        "limiting_factor": limiting_factor(circumstances),

        "start_utc": _utc_iso(start),
        "start_local": _local_iso(start, tz),
        "max_utc": _utc_iso(maximum),
        "max_local": _local_iso(maximum, tz),
        "end_utc": _utc_iso(end),
        "end_local": _local_iso(end, tz),
        "central_start_local": _local_iso(circumstances.get("central_start_utc"), tz),
        "central_end_local": _local_iso(circumstances.get("central_end_utc"), tz),
        "partial_start_local": _local_iso(circumstances.get("partial_start_utc"), tz),
        "partial_end_local": _local_iso(circumstances.get("partial_end_utc"), tz),
        # The watchable window in both forms, matching how start/max/end each carry a UTC twin.
        # The UTC one is what the timestamp sensor publishes: a local string trimmed to minutes
        # reads well on a card but is a weaker thing to hand a machine.
        "visible_start_utc": _utc_iso(circumstances.get("visible_start_utc")),
        "visible_end_utc": _utc_iso(circumstances.get("visible_end_utc")),
        "visible_start_local": _local_iso(circumstances.get("visible_start_utc"), tz),
        "visible_end_local": _local_iso(circumstances.get("visible_end_utc"), tz),
        "central_duration_s": circumstances.get("central_duration_s", 0),
        "duration_s": circumstances.get("duration_s", 0),
        "days_until": round((maximum - now).total_seconds() / 86400.0, 3),
        "hours_until": round((maximum - now).total_seconds() / 3600.0, 2),
        # Both, because they answer different questions and the difference is hours. The lead
        # time on the "go outside" alert is about first contact -- a lunar eclipse runs nearly
        # three hours from there to maximum, so measuring the lead against maximum means the
        # window has already opened and closed before the alert would have fired.
        "hours_until_start": round((start - now).total_seconds() / 3600.0, 2),

        "altitude_at_max": round(circumstances.get("altitude_at_max", 0.0), 1),
        "azimuth_at_max": round(circumstances.get("azimuth_at_max", 0.0), 1),
        "direction_at_max": compass_direction(circumstances.get("azimuth_at_max", 0.0)),
        "altitude_when_visible": round(altitude, 1),
        "azimuth_when_visible": round(visible_azimuth, 1),
        "direction_when_visible": compass_direction(visible_azimuth),
        "above_horizon_at_max": bool(circumstances.get("above_horizon_at_max")),
        "visible_fraction": round(_clamp(circumstances.get("visible_fraction", 0.0)) * 100.0, 1),
        "in_progress_at_rise": bool(circumstances.get("in_progress_at_rise")),
        "in_progress_at_set": bool(circumstances.get("in_progress_at_set")),

        "path_width_km": circumstances.get("path_width_km", 0.0),
    }
    entry.update(safety)
    return entry


def _trim(entry: Dict[str, Any]) -> Dict[str, Any]:
    """Return the small form of an entry, for the look-ahead list.

    Kept deliberately short: the full entry is nearly forty keys, and Home Assistant's recorder
    stores every attribute of every state change. ``meteor.py`` trims its shower list for the
    same reason.
    """
    return {
        "kind": entry["kind"],
        "name": entry["name"],
        "date": entry["date"],
        "max_local": entry["max_local"],
        "days_until": round(entry["days_until"], 1),
        "disc_covered": entry["disc_covered"],
        "viewing_score": entry["viewing_score"],
        "visible": entry["visible"],
    }


def _solar_candidates(catalog: Sequence[Dict[str, Any]], now: datetime,
                      max_scan: int) -> List[Dict[str, Any]]:
    """Return the next *max_scan* catalogued solar eclipses that have not already finished."""
    cutoff = (now - timedelta(days=1)).date()
    upcoming = [entry for entry in catalog if _entry_date(entry) >= cutoff]
    return upcoming[:max_scan]


def _entry_date(entry: Dict[str, Any]):
    """Return a catalog entry's date as a ``datetime.date``."""
    year, month, day = entry["date"]
    return datetime(year, month, day, tzinfo=timezone.utc).date()


def build_eclipse_forecast(
    now: datetime,
    latitude: float,
    longitude: float,
    tz: tzinfo,
    catalog: Sequence[Dict[str, Any]],
    upcoming_count: int = 5,
    elevation_m: float = 0.0,
    include_penumbral: bool = False,
    max_catalog_scan: int = 24,
    lunar_scan_years: float = 4.0,
) -> Dict[str, Any]:
    """Return the complete eclipse forecast for one observer.

    The single entry point the coordinator calls, mirroring ``meteor.build_meteor_forecast``.
    Everything an entity renders -- including local time strings -- is computed here, so the
    entity classes stay simple property readers.

    Deliberately *not* modelled on the meteor forecast's "night of" framing. An eclipse is an
    absolute instant, not something that belongs to an observing night, and borrowing that
    machinery would import a set of local-noon and hemisphere edge cases for no benefit.
    """
    solar_entries: List[Dict[str, Any]] = []
    next_solar_global: Optional[Dict[str, Any]] = None

    for entry in _solar_candidates(catalog, now, max_catalog_scan):
        circumstances = solar_local_circumstances(entry, latitude, longitude, elevation_m)
        year, month, day = entry["date"]
        date_label = f"{year:04d}-{month:02d}-{day:02d}"
        if circumstances.get("max_utc") is None:
            # The shadow never came near; there is no local instant to report. Still worth
            # naming, so that "next solar eclipse anywhere" can mention it.
            if next_solar_global is None:
                next_solar_global = {
                    "date": date_label,
                    "name": display_name(KIND_SOLAR, entry["type"]),
                    "days_until": round(
                        (datetime(year, month, day, tzinfo=timezone.utc) - now).total_seconds()
                        / 86400.0, 1,
                    ),
                }
            continue
        built = _build_entry(KIND_SOLAR, circumstances, now, tz, date_label)
        if next_solar_global is None:
            next_solar_global = {
                "date": built["date"],
                "name": display_name(KIND_SOLAR, entry["type"]),
                "days_until": round(built["days_until"], 1),
            }
        solar_entries.append(built)

    lunar_entries = []
    for found in lunar_eclipses_between(
        now - timedelta(days=1), now + timedelta(days=365.25 * lunar_scan_years),
    ):
        if not include_penumbral and found["type"] == TYPE_PENUMBRAL:
            continue
        circumstances = lunar_local_circumstances(found, latitude, longitude)
        lunar_entries.append(_build_entry(
            KIND_LUNAR, circumstances, now, tz,
            found["greatest_utc"].strftime("%Y-%m-%d"),
        ))

    everything = sorted(solar_entries + lunar_entries, key=lambda item: item["days_until"])
    visible = [item for item in everything if item["visible"]]

    current = next((item for item in visible if item["in_progress"]), None)
    future = [item for item in visible if item["days_until"] >= 0.0]

    # Compared against the last catalogued eclipse's *date*, not its year: the final entry is in
    # July 2075, so a year comparison leaves the last five months of 2075 returning nothing at all
    # with the flag still False and nothing in the log to explain it.
    catalog_exhausted = (
        not solar_entries and bool(catalog) and _entry_date(catalog[-1]) < now.date()
    )

    return {
        "generated_utc": _utc_iso(now),
        "latitude": latitude,
        "longitude": longitude,
        "catalog_first_year": catalog[0]["date"][0] if catalog else None,
        "catalog_last_year": catalog[-1]["date"][0] if catalog else None,
        "catalog_exhausted": catalog_exhausted,
        "current": current,
        "next": future[0] if future else None,
        "next_solar": next((i for i in future if i["kind"] == KIND_SOLAR), None),
        "next_lunar": next((i for i in future if i["kind"] == KIND_LUNAR), None),
        "next_solar_global": next_solar_global,
        "upcoming": [_trim(item) for item in everything if item["days_until"] >= 0.0][
            :upcoming_count
        ],
    }
