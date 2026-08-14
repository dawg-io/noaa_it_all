"""Unit tests for astro.py — pure functions, no Home Assistant dependency.

Reference values come from Jean Meeus, *Astronomical Algorithms* (2nd ed.) worked examples, and
from published equinox/solstice times. Because astro.py imports nothing but the standard library
it loads directly via pytest.ini's ``pythonpath``, exactly like ``test_parsers.py``.
"""

import math
import unittest
from datetime import date, datetime, timedelta, timezone

from astro import (
    DARKNESS_ASTRONOMICAL,
    DARKNESS_NONE,
    J2000_JD,
    angular_separation_degrees,
    datetime_from_jd,
    equatorial_to_horizontal,
    find_dark_window,
    gmst_degrees,
    julian_day,
    local_sidereal_time,
    max_altitude,
    moon_equatorial,
    moon_illuminated_fraction,
    next_solar_longitude_after,
    normalize_degrees,
    obliquity_of_ecliptic,
    previous_solar_longitude_before,
    sun_altitude,
    solar_noon_utc,
    sun_apparent_longitude,
    sun_equatorial,
    wrap180,
)

UTC = timezone.utc
J2000 = datetime(2000, 1, 1, 12, 0, 0, tzinfo=UTC)


class TestAngleHelpers(unittest.TestCase):
    """Angle normalisation, especially the wraparound that shower timing depends on."""

    def test_normalize_degrees(self):
        self.assertEqual(normalize_degrees(0.0), 0.0)
        self.assertEqual(normalize_degrees(360.0), 0.0)
        self.assertEqual(normalize_degrees(370.0), 10.0)
        self.assertAlmostEqual(normalize_degrees(-10.0), 350.0)

    def test_wrap180_range(self):
        """wrap180 must land in (-180, 180], with -180 canonicalised to +180."""
        self.assertEqual(wrap180(0.0), 0.0)
        self.assertEqual(wrap180(190.0), -170.0)
        self.assertEqual(wrap180(350.0), -10.0)
        self.assertEqual(wrap180(-180.0), 180.0)
        self.assertEqual(wrap180(180.0), 180.0)

    def test_wrap180_shortest_distance_across_zero(self):
        """359 deg and 1 deg are 2 deg apart, not 358 — the case Quadrantid timing hinges on."""
        self.assertAlmostEqual(abs(wrap180(359.0 - 1.0)), 2.0)
        self.assertAlmostEqual(abs(wrap180(1.0 - 359.0)), 2.0)

    def test_angular_separation(self):
        self.assertAlmostEqual(angular_separation_degrees(0, 0, 0, 0), 0.0, places=6)
        self.assertAlmostEqual(angular_separation_degrees(0, 0, 90, 0), 90.0, places=6)
        self.assertAlmostEqual(angular_separation_degrees(0, -90, 0, 90), 180.0, places=4)


class TestJulianDay(unittest.TestCase):
    """Julian Day conversion against Meeus worked examples."""

    def test_j2000_epoch(self):
        """The defining epoch: 2000-01-01 12:00 UTC is exactly JD 2451545.0."""
        self.assertEqual(julian_day(J2000), 2451545.0)

    def test_meeus_example_7a(self):
        """Meeus example 7.a — the Sputnik 1 launch."""
        sputnik = datetime(1957, 10, 4, 19, 26, 24, tzinfo=UTC)
        self.assertAlmostEqual(julian_day(sputnik), 2436116.31, places=5)

    def test_naive_datetime_rejected(self):
        """A naive datetime would silently shift every peak by the observer's offset."""
        with self.assertRaises(ValueError):
            julian_day(datetime(2026, 8, 12, 12, 0, 0))

    def test_non_utc_timezone_converted(self):
        aware = datetime(2000, 1, 1, 7, 0, 0, tzinfo=timezone(timedelta(hours=-5)))
        self.assertEqual(julian_day(aware), 2451545.0)

    def test_round_trip(self):
        """julian_day and datetime_from_jd must invert each other to well under a second."""
        for days in range(-20000, 20001, 617):
            moment = J2000 + timedelta(days=days, hours=7, minutes=13, seconds=41)
            error = abs((datetime_from_jd(julian_day(moment)) - moment).total_seconds())
            self.assertLess(error, 0.001)


class TestSun(unittest.TestCase):
    """Solar position against Meeus worked examples."""

    def test_meeus_example_25a(self):
        """Meeus example 25.a — apparent solar longitude at JDE 2448908.5."""
        self.assertAlmostEqual(sun_apparent_longitude(2448908.5), 199.90895, places=3)

    def test_longitude_always_normalized(self):
        for offset in range(0, 4000, 137):
            longitude = sun_apparent_longitude(J2000_JD + offset)
            self.assertGreaterEqual(longitude, 0.0)
            self.assertLess(longitude, 360.0)

    def test_obliquity_near_23_44_degrees(self):
        """obliquity_of_ecliptic returns the *true* obliquity, i.e. mean plus nutation.

        The mean value at J2000.0 is 23.4392911 deg; the nutation term contributes about
        -0.0015 deg there, so the true value is slightly smaller.
        """
        true_obliquity = obliquity_of_ecliptic(J2000_JD)
        self.assertAlmostEqual(true_obliquity, 23.4378, places=3)
        self.assertLess(abs(true_obliquity - 23.4392911), 0.0026)

    def test_sun_declination_extremes(self):
        """Declination should reach roughly +/-23.44 deg at the solstices."""
        june = julian_day(next_solar_longitude_after(90.0, datetime(2026, 1, 1, tzinfo=UTC)))
        december = julian_day(next_solar_longitude_after(270.0, datetime(2026, 1, 1, tzinfo=UTC)))
        self.assertAlmostEqual(sun_equatorial(june)[1], 23.44, delta=0.05)
        self.assertAlmostEqual(sun_equatorial(december)[1], -23.44, delta=0.05)


class TestSolarLongitudeInversion(unittest.TestCase):
    """Inverting solar longitude to a datetime is what makes the shower catalog date-free."""

    # Published equinox and solstice times. The low-precision series is accurate to about
    # +/-11 minutes, which is far finer than the hours-wide spread of real shower maxima.
    REFERENCES = [
        (0.0, datetime(2025, 3, 20, 9, 1, 36, tzinfo=UTC)),
        (0.0, datetime(2026, 3, 20, 14, 45, 36, tzinfo=UTC)),
        (90.0, datetime(2026, 6, 21, 8, 24, 55, tzinfo=UTC)),
        (180.0, datetime(2026, 9, 23, 0, 5, 30, tzinfo=UTC)),
        (270.0, datetime(2026, 12, 21, 20, 50, 13, tzinfo=UTC)),
    ]

    def test_equinoxes_and_solstices_within_fifteen_minutes(self):
        for longitude, expected in self.REFERENCES:
            start = datetime(expected.year, 1, 1, tzinfo=UTC)
            computed = next_solar_longitude_after(longitude, start)
            error_minutes = abs((computed - expected).total_seconds()) / 60.0
            self.assertLess(
                error_minutes, 15.0,
                f"lambda={longitude} in {expected.year}: off by {error_minutes:.1f} min",
            )

    def test_round_trip(self):
        """Solving for a longitude then re-evaluating must return that longitude."""
        reference = datetime(2026, 1, 1, tzinfo=UTC)
        for target in range(0, 360, 7):
            solved = next_solar_longitude_after(float(target), reference)
            self.assertAlmostEqual(
                wrap180(sun_apparent_longitude(julian_day(solved)) - target), 0.0, places=5,
            )

    def test_quadrantid_wraparound(self):
        """Solar longitude 283.15 asked for from 1 January lands in early January of that year.

        This is the classic off-by-one-year trap: a naive 'days since the March equinox'
        formulation puts the Quadrantids twelve months late.
        """
        peak = next_solar_longitude_after(283.15, datetime(2026, 1, 1, tzinfo=UTC))
        self.assertEqual(peak.year, 2026)
        self.assertEqual(peak.month, 1)
        self.assertIn(peak.day, (3, 4))

    def test_ursid_near_year_end(self):
        peak = next_solar_longitude_after(270.7, datetime(2026, 12, 1, tzinfo=UTC))
        self.assertEqual((peak.year, peak.month), (2026, 12))
        self.assertIn(peak.day, (21, 22, 23))

    def test_known_shower_peaks(self):
        """Published maxima must reproduce from solar longitude alone, to within a day."""
        cases = [
            (283.15, 1, (3, 4)),      # Quadrantids
            (32.32, 4, (22, 23)),     # Lyrids
            (140.0, 8, (12, 13)),     # Perseids
            (208.0, 10, (21, 22)),    # Orionids
            (235.27, 11, (17, 18)),   # Leonids
            (262.2, 12, (13, 14)),    # Geminids
        ]
        for longitude, month, days in cases:
            peak = next_solar_longitude_after(longitude, datetime(2026, 1, 1, tzinfo=UTC))
            self.assertEqual(peak.month, month, f"lambda={longitude} -> {peak}")
            self.assertIn(peak.day, days, f"lambda={longitude} -> {peak}")

    def test_next_is_always_after(self):
        reference = datetime(2026, 6, 15, 3, 27, tzinfo=UTC)
        for target in range(0, 360, 11):
            self.assertGreater(next_solar_longitude_after(float(target), reference), reference)

    def test_previous_is_always_before(self):
        reference = datetime(2026, 6, 15, 3, 27, tzinfo=UTC)
        for target in range(0, 360, 11):
            self.assertLess(previous_solar_longitude_before(float(target), reference), reference)

    def test_next_and_previous_bracket_one_year(self):
        reference = datetime(2026, 6, 15, tzinfo=UTC)
        for target in (0.0, 90.0, 140.0, 283.15):
            span = (next_solar_longitude_after(target, reference)
                    - previous_solar_longitude_before(target, reference))
            self.assertAlmostEqual(span.total_seconds() / 86400.0, 365.24, delta=0.5)

    def test_exact_crossing_advances_a_full_year(self):
        """Asking for the next crossing while sitting exactly on one must not return now."""
        crossing = next_solar_longitude_after(140.0, datetime(2026, 1, 1, tzinfo=UTC))
        following = next_solar_longitude_after(140.0, crossing)
        self.assertGreater((following - crossing).days, 360)


class TestSiderealTime(unittest.TestCase):
    """Sidereal time against Meeus example 12.a."""

    def test_gmst_at_j2000(self):
        self.assertAlmostEqual(gmst_degrees(J2000_JD), 280.46061837, places=6)

    def test_meeus_example_12a(self):
        self.assertAlmostEqual(gmst_degrees(2446896.30625), 128.7378734, places=4)

    def test_local_sidereal_time_is_east_positive(self):
        """Home Assistant stores east-positive longitude; Meeus uses west-positive."""
        greenwich = gmst_degrees(J2000_JD)
        self.assertAlmostEqual(local_sidereal_time(J2000_JD, 0.0), greenwich, places=9)
        self.assertAlmostEqual(
            local_sidereal_time(J2000_JD, 15.0), normalize_degrees(greenwich + 15.0), places=9,
        )


class TestCoordinateTransform(unittest.TestCase):
    """Equatorial to horizontal conversion, including Meeus example 13.b."""

    def test_zenith_invariant(self):
        """A source whose declination equals the latitude, on the meridian, sits at the zenith."""
        for latitude in (-70.0, -33.9, 0.0, 34.0, 64.1):
            altitude, _ = equatorial_to_horizontal(123.0, latitude, latitude, 123.0)
            self.assertAlmostEqual(altitude, 90.0, places=5)

    def test_meeus_example_13b(self):
        """Meeus example 13.b, Venus from Washington DC.

        Meeus quotes azimuth 68.0337 measured from *south*; this module measures from north, so
        the expected value is 180 degrees away.
        """
        sidereal = local_sidereal_time(2446896.30625, -77.065555)
        altitude, azimuth = equatorial_to_horizontal(
            347.3193375, -6.719892, 38.921389, sidereal,
        )
        self.assertAlmostEqual(altitude, 15.1249, delta=0.02)
        self.assertAlmostEqual(azimuth, 248.0337, delta=0.02)

    def test_altitude_bounded(self):
        for declination in range(-90, 91, 15):
            for latitude in (-60.0, 0.0, 45.0):
                for sidereal in range(0, 360, 45):
                    altitude, azimuth = equatorial_to_horizontal(
                        0.0, float(declination), latitude, float(sidereal),
                    )
                    self.assertGreaterEqual(altitude, -90.0001)
                    self.assertLessEqual(altitude, 90.0001)
                    self.assertGreaterEqual(azimuth, 0.0)
                    self.assertLess(azimuth, 360.0)

    def test_max_altitude(self):
        """Highest an object can climb, used to spot radiants that never rise."""
        self.assertAlmostEqual(max_altitude(45.0, 45.0), 90.0)
        self.assertAlmostEqual(max_altitude(0.0, 45.0), 45.0)
        # The Quadrantid radiant is permanently below the horizon deep in the south.
        self.assertLess(max_altitude(49.0, -60.0), 0.0)


class TestMoon(unittest.TestCase):
    """Lunar position and phase against Meeus examples 47.a and 48.a."""

    MEEUS_JD = 2448724.5

    def test_meeus_example_47a_position(self):
        right_ascension, declination = moon_equatorial(self.MEEUS_JD)
        self.assertAlmostEqual(right_ascension, 134.6885, delta=0.3)
        self.assertAlmostEqual(declination, 13.7684, delta=0.3)

    def test_meeus_example_48a_illumination(self):
        self.assertAlmostEqual(moon_illuminated_fraction(self.MEEUS_JD), 0.6786, delta=0.005)

    def test_illumination_bounded(self):
        for day in range(0, 400):
            fraction = moon_illuminated_fraction(J2000_JD + day * 0.7)
            self.assertGreaterEqual(fraction, 0.0)
            self.assertLessEqual(fraction, 1.0)

    def test_illumination_reaches_both_extremes(self):
        values = [moon_illuminated_fraction(J2000_JD + day) for day in range(60)]
        self.assertLess(min(values), 0.02)
        self.assertGreater(max(values), 0.98)

    def test_synodic_period(self):
        """Successive new moons should average the 29.53-day synodic month."""
        samples = [
            (hour / 24.0, moon_illuminated_fraction(J2000_JD + hour / 24.0))
            for hour in range(24 * 400)
        ]
        minima = [
            samples[i][0]
            for i in range(1, len(samples) - 1)
            if samples[i][1] < samples[i - 1][1] and samples[i][1] < samples[i + 1][1]
        ]
        self.assertGreater(len(minima), 10)
        gaps = [minima[i + 1] - minima[i] for i in range(len(minima) - 1)]
        self.assertAlmostEqual(sum(gaps) / len(gaps), 29.5306, delta=0.05)


class TestDarkWindow(unittest.TestCase):
    """Twilight search, including the high-latitude cases the closed-form solution cannot do."""

    LA = (34.05, -118.24)
    REYKJAVIK = (64.13, -21.90)
    SYDNEY = (-33.87, 151.21)

    def test_mid_latitude_summer_night(self):
        start, end, label = find_dark_window(date(2026, 8, 12), *self.LA)
        self.assertEqual(label, DARKNESS_ASTRONOMICAL)
        hours = (end - start).total_seconds() / 3600.0
        self.assertGreater(hours, 5.0)
        self.assertLess(hours, 10.0)

    def test_sun_is_actually_below_threshold_inside_window(self):
        start, end, _ = find_dark_window(date(2026, 8, 12), *self.LA)
        midpoint = start + (end - start) / 2
        self.assertLess(sun_altitude(julian_day(midpoint), *self.LA), -18.0)

    def test_high_latitude_summer_has_no_darkness(self):
        """Above roughly 49 degrees there is no astronomical night in midsummer.

        The closed-form sunset equation has no solution here; sampling degrades gracefully.
        """
        start, end, label = find_dark_window(date(2026, 6, 21), *self.REYKJAVIK)
        self.assertEqual(label, DARKNESS_NONE)
        self.assertIsNone(start)
        self.assertIsNone(end)

    def test_high_latitude_winter_has_long_night(self):
        start, end, label = find_dark_window(date(2026, 12, 21), *self.REYKJAVIK)
        self.assertEqual(label, DARKNESS_ASTRONOMICAL)
        self.assertGreater((end - start).total_seconds() / 3600.0, 10.0)

    def test_southern_hemisphere(self):
        start, end, label = find_dark_window(date(2026, 8, 12), *self.SYDNEY)
        self.assertEqual(label, DARKNESS_ASTRONOMICAL)
        self.assertGreater((end - start).total_seconds() / 3600.0, 5.0)

    def test_window_is_independent_of_the_configured_timezone(self):
        """The window is anchored on the observer's longitude, not on a civil timezone.

        A Home Assistant left on UTC while pointed at California used to have the night clipped
        at the search boundary, reporting 9.7 dark hours instead of 11.1.
        """
        start, end, label = find_dark_window(date(2026, 12, 21), *self.LA)
        hours = (end - start).total_seconds() / 3600.0
        self.assertEqual(label, DARKNESS_ASTRONOMICAL)
        self.assertGreater(hours, 10.5)
        # and the sun really is below the threshold right up to the reported end
        self.assertLess(sun_altitude(julian_day(end - timedelta(minutes=5)), *self.LA), -18.0)

    def test_solar_noon_tracks_longitude(self):
        """Solar noon runs earlier in UTC the further east the observer is."""
        greenwich = solar_noon_utc(date(2026, 6, 21), 0.0)
        self.assertEqual(greenwich.hour, 12)
        east = solar_noon_utc(date(2026, 6, 21), 15.0)
        self.assertEqual((greenwich - east).total_seconds() / 3600.0, 1.0)
        west = solar_noon_utc(date(2026, 6, 21), -15.0)
        self.assertEqual((west - greenwich).total_seconds() / 3600.0, 1.0)

    def test_window_is_ordered(self):
        for observer in (self.LA, self.REYKJAVIK, self.SYDNEY):
            for day in (date(2026, 3, 21), date(2026, 9, 23), date(2026, 12, 21)):
                start, end, _ = find_dark_window(day, *observer)
                if start is not None:
                    self.assertLess(start, end)


class TestNoHomeAssistantDependency(unittest.TestCase):
    """astro.py must stay importable with Home Assistant entirely absent."""

    def test_only_standard_library_imports(self):
        import astro
        source = open(astro.__file__).read()
        for forbidden in ("homeassistant", "aiohttp", "voluptuous"):
            self.assertNotIn(forbidden, source)

    def test_math_module_available(self):
        self.assertTrue(callable(math.sin))


if __name__ == "__main__":
    unittest.main()
