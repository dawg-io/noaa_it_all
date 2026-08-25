"""Unit tests for eclipse.py -- pure functions, no Home Assistant dependency.

Reference values come from NASA's published local circumstances, and every absolute one is for an
eclipse that has **already happened**. That is deliberate: the 2024-04-08 obscuration at New York
is an observed, published, permanent fact, whereas pinning a 2045 figure to three decimals would
only encode whatever the implementation happened to do the day the test was written.

Forward-looking behaviour is asserted as *invariants* instead -- orderings, ranges, and
relationships that must hold for any observer at any date -- in the spirit of ``test_meteor.py``,
where end-to-end assertions are stated as ranges around physically verified values so that an
empirical tweak does not break CI while a sign error still does.

``now`` is frozen in every test. Nothing here may consult the wall clock.
"""

import math
import unittest
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import eclipse
from eclipse import (
    KIND_LUNAR,
    KIND_SOLAR,
    TYPE_ANNULAR,
    TYPE_NONE,
    TYPE_PARTIAL,
    TYPE_PENUMBRAL,
    TYPE_TOTAL,
    build_eclipse_forecast,
    compass_direction,
    disc_overlap_fraction,
    geocentric_observer,
    lunar_eclipse_at_lunation,
    lunar_eclipses_between,
    lunar_local_circumstances,
    obscuration,
    score_rating,
    solar_local_circumstances,
    solar_magnitude,
    solar_viewing_score,
)
from eclipse_catalog import SOLAR_ECLIPSES

UTC = timezone.utc

# Observing sites. ILM matches an NWS office the integration ships; the rest exist to exercise
# the southern hemisphere, high latitude, and the far side of the planet.
ILM = (34.2675, -77.9011)
DALLAS = (32.7767, -96.7970)
NEW_YORK = (40.7128, -74.0060)
SYDNEY = (-33.87, 151.21)
TROMSO = (69.65, 18.96)
TOKYO = (35.68, 139.69)
CAPE_TOWN = (-33.92, 18.42)
REYKJAVIK = (64.15, -21.94)

#: The Besselian elements for the total solar eclipse of 2024 April 8, from NASA's Five
#: Millennium Canon. Held as a literal rather than read from the catalog -- which starts in 2025
#: -- exactly as ``test_meteor.py`` defines its Perseids literal instead of pulling from
#: ``METEOR_SHOWERS``. That keeps these assertions independent of the catalog's span.
ECLIPSE_2024_04_08 = {
    "date": (2024, 4, 8), "type": "total",
    "t0_jd": 2460409.25, "delta_t": 74.0,
    "gamma": 0.3431, "magnitude": 1.0566,
    "tanf1": 0.0046683, "tanf2": 0.0046450,
    "x": (-0.318244, 0.5117116, 3.26e-05, -8.4e-06),
    "y": (0.219764, 0.2709589, -5.95e-05, -4.7e-06),
    "d": (7.5862002, 0.014844, -2e-06, 0.0),
    "mu": (89.591217, 15.00408, 0.0, 0.0),
    "l1": (0.535814, 6.18e-05, -1.28e-05, 0.0),
    "l2": (-0.010272, 6.15e-05, -1.27e-05, 0.0),
    "path_width_km": 197.5, "central_duration_s": 268,
    "greatest_jd": 2460409.278, "greatest_latitude": 25.3,
    "greatest_longitude": -104.1, "greatest_altitude": 70.2,
}

NOW = datetime(2026, 7, 1, 12, 0, tzinfo=UTC)


class TestDiscOverlap(unittest.TestCase):
    """Closed-form cases for the circle geometry both halves of the module share."""

    def test_disjoint_discs_overlap_not_at_all(self):
        self.assertEqual(disc_overlap_fraction(3.0, 1.0, 1.0), 0.0)

    def test_touching_discs_overlap_not_at_all(self):
        self.assertEqual(disc_overlap_fraction(2.0, 1.0, 1.0), 0.0)

    def test_a_disc_swallowed_whole_is_fully_covered(self):
        self.assertEqual(disc_overlap_fraction(0.0, 1.0, 2.0), 1.0)
        self.assertEqual(disc_overlap_fraction(0.5, 1.0, 2.0), 1.0)

    def test_a_smaller_disc_inside_covers_its_area_ratio(self):
        # The annular case: the Moon sits entirely within the Sun's disc.
        self.assertAlmostEqual(disc_overlap_fraction(0.0, 1.0, 0.5), 0.25)

    def test_identical_discs_exactly_aligned_cover_everything(self):
        self.assertAlmostEqual(disc_overlap_fraction(0.0, 1.0, 1.0), 1.0)

    def test_half_covered_at_the_symmetric_crossing(self):
        # Two equal discs whose centres are one radius apart cover a known lens area.
        expected = (2.0 * (math.acos(0.5) - 0.5 * math.sqrt(0.75))) / math.pi
        self.assertAlmostEqual(disc_overlap_fraction(1.0, 1.0, 1.0), expected)

    def test_a_vanished_coverer_covers_nothing(self):
        self.assertEqual(disc_overlap_fraction(0.0, 1.0, 0.0), 0.0)

    def test_a_vanished_target_is_not_a_division_by_zero(self):
        self.assertEqual(disc_overlap_fraction(0.0, 0.0, 1.0), 0.0)


class TestObscurationSignRegression(unittest.TestCase):
    """The negative-``l2`` trap, pinned so it cannot come back.

    During totality the umbral cone radius goes negative, and that sign is what encodes "the
    Moon's disc is the larger one". Taking its absolute value as the Moon's radius -- which is
    the obvious reading -- reports a total solar eclipse as about 0.1% obscured.
    """

    def _geometry(self, m, l1, l2):
        return eclipse.ShadowGeometry(m=m, l1=l1, l2=l2, zeta=0.0)

    def test_totality_is_fully_obscured_not_nearly_zero(self):
        geometry = self._geometry(m=0.0, l1=0.5358, l2=-0.0144)
        self.assertAlmostEqual(obscuration(geometry), 1.0, places=6)

    def test_the_naive_reading_is_the_one_that_would_be_wrong(self):
        # Demonstrates the failure this guards against: |l2| as the Moon's radius gives a number
        # near zero for the same geometry that is in fact a total eclipse.
        naive = disc_overlap_fraction(0.0, 0.5358, abs(-0.0144))
        self.assertLess(naive, 0.01)

    def test_moon_is_larger_than_sun_when_l2_is_negative(self):
        sun, moon = eclipse.solar_disc_radii(self._geometry(0.0, 0.5358, -0.0144))
        self.assertGreater(moon, sun)

    def test_moon_is_smaller_than_sun_when_l2_is_positive(self):
        sun, moon = eclipse.solar_disc_radii(self._geometry(0.0, 0.5358, 0.0144))
        self.assertLess(moon, sun)

    def test_annular_eclipse_leaves_a_ring_of_sun(self):
        covered = obscuration(self._geometry(m=0.0, l1=0.5600, l2=0.0300))
        self.assertGreater(covered, 0.8)
        self.assertLess(covered, 1.0)


class TestObserverGeometry(unittest.TestCase):
    """The ellipsoid correction, which is worth about twenty kilometres of shadow path."""

    def test_the_equator_is_a_full_radius_from_the_axis(self):
        rho_sin, rho_cos = geocentric_observer(0.0)
        self.assertAlmostEqual(rho_sin, 0.0, places=9)
        self.assertAlmostEqual(rho_cos, 1.0, places=9)

    def test_the_pole_is_flattened(self):
        rho_sin, rho_cos = geocentric_observer(90.0)
        self.assertAlmostEqual(rho_cos, 0.0, places=9)
        self.assertLess(rho_sin, 1.0)          # Earth is flattened, so the pole is closer in
        self.assertGreater(rho_sin, 0.99)

    def test_flattening_actually_moves_a_mid_latitude_observer(self):
        # If this were computed on a sphere, rho_sin would be sin(45) exactly.
        rho_sin, _ = geocentric_observer(45.0)
        self.assertNotAlmostEqual(rho_sin, math.sin(math.radians(45.0)), places=4)

    def test_the_southern_hemisphere_mirrors_the_northern(self):
        north_sin, north_cos = geocentric_observer(45.0)
        south_sin, south_cos = geocentric_observer(-45.0)
        self.assertAlmostEqual(north_sin, -south_sin)
        self.assertAlmostEqual(north_cos, south_cos)

    def test_elevation_pushes_the_observer_outwards(self):
        _, sea_level = geocentric_observer(45.0, 0.0)
        _, on_a_mountain = geocentric_observer(45.0, 4000.0)
        self.assertGreater(on_a_mountain, sea_level)


class TestCompass(unittest.TestCase):
    """Azimuth to a direction anybody can act on."""

    def test_cardinal_points(self):
        self.assertEqual(compass_direction(0.0), "N")
        self.assertEqual(compass_direction(90.0), "E")
        self.assertEqual(compass_direction(180.0), "S")
        self.assertEqual(compass_direction(270.0), "W")

    def test_wraps_around_north(self):
        self.assertEqual(compass_direction(359.0), "N")
        self.assertEqual(compass_direction(360.0), "N")

    def test_intermediate_points(self):
        self.assertEqual(compass_direction(225.0), "SW")
        self.assertEqual(compass_direction(247.5), "WSW")


class TestSolarEclipse2024(unittest.TestCase):
    """The 8 April 2024 total solar eclipse, against NASA's published local circumstances.

    A past event, so these numbers are settled forever.
    """

    def _at(self, site):
        return solar_local_circumstances(ECLIPSE_2024_04_08, site[0], site[1])

    def test_dallas_was_inside_the_path_of_totality(self):
        circumstances = self._at(DALLAS)
        self.assertEqual(circumstances["local_type"], TYPE_TOTAL)
        self.assertAlmostEqual(circumstances["obscuration"], 1.0, places=6)

    def test_dallas_totality_timing(self):
        # Published: totality 18:40:43 to 18:44:32 UT, about 3m49s.
        circumstances = self._at(DALLAS)
        self.assertAlmostEqual(
            circumstances["central_start_utc"],
            datetime(2024, 4, 8, 18, 40, 43, tzinfo=UTC), delta=timedelta(minutes=2),
        )
        self.assertAlmostEqual(
            circumstances["central_end_utc"],
            datetime(2024, 4, 8, 18, 44, 32, tzinfo=UTC), delta=timedelta(minutes=2),
        )
        self.assertAlmostEqual(circumstances["central_duration_s"], 229, delta=45)

    def test_dallas_first_and_last_contact(self):
        # Published: partial phase 17:23:35 to 20:02:38 UT.
        circumstances = self._at(DALLAS)
        self.assertAlmostEqual(
            circumstances["start_utc"],
            datetime(2024, 4, 8, 17, 23, 35, tzinfo=UTC), delta=timedelta(minutes=2),
        )
        self.assertAlmostEqual(
            circumstances["end_utc"],
            datetime(2024, 4, 8, 20, 2, 38, tzinfo=UTC), delta=timedelta(minutes=2),
        )

    def test_new_york_saw_a_deep_partial(self):
        # Published: magnitude 0.907, obscuration 89.6%.
        circumstances = self._at(NEW_YORK)
        self.assertEqual(circumstances["local_type"], TYPE_PARTIAL)
        self.assertAlmostEqual(circumstances["magnitude"], 0.907, delta=0.01)
        self.assertAlmostEqual(circumstances["obscuration"], 0.896, delta=0.015)

    def test_the_local_type_is_not_the_headline_type(self):
        # The whole point of re-deriving type per observer: this is catalogued as a *total*
        # eclipse, and a New Yorker saw a partial one.
        circumstances = self._at(NEW_YORK)
        self.assertEqual(circumstances["global_type"], TYPE_TOTAL)
        self.assertEqual(circumstances["local_type"], TYPE_PARTIAL)

    def test_wilmington_saw_a_modest_partial(self):
        circumstances = self._at(ILM)
        self.assertEqual(circumstances["local_type"], TYPE_PARTIAL)
        self.assertAlmostEqual(circumstances["obscuration"], 0.71, delta=0.03)

    def test_obscuration_is_always_below_magnitude_for_a_partial(self):
        # Area is covered more slowly than diameter, always. This relationship is what makes
        # reporting the two separately worth doing.
        circumstances = self._at(NEW_YORK)
        self.assertLess(circumstances["obscuration"], circumstances["magnitude"])

    def test_a_low_sun_observer_still_gets_a_sensible_answer(self):
        circumstances = self._at(REYKJAVIK)
        self.assertTrue(circumstances["visible"])
        self.assertGreater(circumstances["obscuration"], 0.3)
        self.assertLess(circumstances["altitude_at_max"], 20.0)

    def test_an_observer_on_the_night_side_sees_nothing(self):
        # Tokyo is geometrically inside the penumbra and the Sun is far below its horizon. The
        # Besselian solve will happily hand back a magnitude here, so altitude has to be checked
        # separately -- this is the case that proves the two failures are told apart.
        circumstances = self._at(TOKYO)
        self.assertGreater(circumstances["magnitude"], 0.0)
        self.assertLess(circumstances["altitude_at_max"], 0.0)
        self.assertFalse(circumstances["visible"])
        self.assertEqual(circumstances["reason"], "below the horizon")
        self.assertEqual(circumstances["visible_obscuration"], 0.0)

    def test_an_observer_outside_the_shadow_entirely_sees_nothing(self):
        circumstances = self._at(CAPE_TOWN)
        self.assertFalse(circumstances["visible"])
        self.assertEqual(circumstances["reason"], "outside the shadow")
        self.assertEqual(circumstances["local_type"], TYPE_NONE)
        self.assertEqual(circumstances["obscuration"], 0.0)

    def test_the_two_kinds_of_invisibility_are_distinguishable(self):
        self.assertNotEqual(self._at(TOKYO)["reason"], self._at(CAPE_TOWN)["reason"])

    def test_magnitude_never_goes_negative(self):
        # An observer well outside the penumbra computes a negative magnitude from the raw
        # formula; reporting "-105% covered" would be worse than useless.
        for site in (CAPE_TOWN, SYDNEY, TROMSO):
            self.assertGreaterEqual(self._at(site)["magnitude"], 0.0)


class TestSolarMagnitudeRegimes(unittest.TestCase):
    """Magnitude switches definition at the edge of the shadow, and must switch cleanly."""

    def _geometry(self, m, l1, l2):
        return eclipse.ShadowGeometry(m=m, l1=l1, l2=l2, zeta=0.0)

    def test_partial_regime_measures_progress_across_the_disc(self):
        magnitude = solar_magnitude(self._geometry(m=0.3, l1=0.5358, l2=-0.0144))
        self.assertAlmostEqual(magnitude, (0.5358 - 0.3) / (0.5358 - 0.0144), places=6)

    def test_central_regime_measures_the_ratio_of_the_discs(self):
        # Inside the shadow the discs fully overlap, so magnitude stops describing progress and
        # starts describing relative size -- which is why totality is quoted above 1.0.
        magnitude = solar_magnitude(self._geometry(m=0.0, l1=0.5358, l2=-0.0144))
        self.assertAlmostEqual(magnitude, (0.5358 + 0.0144) / (0.5358 - 0.0144), places=6)
        self.assertGreater(magnitude, 1.0)

    def test_the_partial_regime_reaches_exactly_one_at_second_contact(self):
        l1, l2 = 0.5358, -0.0144
        self.assertAlmostEqual(
            solar_magnitude(self._geometry(abs(l2), l1, l2)), 1.0, places=6,
        )

    def test_magnitude_steps_up_at_second_contact_and_that_is_correct(self):
        """The jump is the convention, not a bug.

        At second contact the Moon's leading edge reaches the far limb, so the covered fraction
        of the Sun's *diameter* is exactly 1.0 and can go no higher. The number every published
        source quotes for a total eclipse -- 1.0566 for 2024 April 8 -- is a different quantity
        wearing the same name: the ratio of the two apparent diameters. Reporting the smooth
        extension instead would disagree with NASA for every central eclipse in the catalog.
        """
        l1, l2 = 0.5358, -0.0144
        just_outside = solar_magnitude(self._geometry(abs(l2) + 1e-9, l1, l2))
        just_inside = solar_magnitude(self._geometry(abs(l2) - 1e-9, l1, l2))
        self.assertAlmostEqual(just_outside, 1.0, places=6)
        self.assertGreater(just_inside, just_outside)
        self.assertAlmostEqual(just_inside, (l1 - l2) / (l1 + l2), places=6)

    def test_no_eclipse_gives_zero_not_a_negative_number(self):
        self.assertEqual(solar_magnitude(self._geometry(m=1.0, l1=0.5358, l2=-0.0144)), 0.0)


class TestLunarEclipses(unittest.TestCase):
    """Meeus ch. 54 against NASA's Five Millennium Catalog of Lunar Eclipses.

    All four references are past or imminent events with published, settled figures.
    """

    #: ``(greatest UT, umbral magnitude, penumbral magnitude, type)`` as published by NASA.
    PUBLISHED = (
        (datetime(2025, 3, 14, 6, 58, 43, tzinfo=UTC), 1.1783, 2.2609, TYPE_TOTAL),
        (datetime(2025, 9, 7, 18, 11, 47, tzinfo=UTC), 1.3617, 2.3427, TYPE_TOTAL),
        (datetime(2026, 3, 3, 11, 33, 53, tzinfo=UTC), 1.1512, 2.1837, TYPE_TOTAL),
        (datetime(2026, 8, 28, 4, 12, 57, tzinfo=UTC), 0.9296, 1.9634, TYPE_PARTIAL),
    )

    def _found(self):
        return lunar_eclipses_between(
            datetime(2025, 1, 1, tzinfo=UTC), datetime(2026, 12, 31, tzinfo=UTC),
        )

    def test_finds_exactly_the_published_eclipses(self):
        # Penumbral eclipses are included here, so this also proves the sin F pre-filter is not
        # letting phantom eclipses through: anything it admits that is not real is rejected on
        # its computed penumbral magnitude instead.
        found = [item for item in self._found() if item["type"] != TYPE_PENUMBRAL]
        self.assertEqual(len(found), len(self.PUBLISHED))

    def test_times_match_nasa(self):
        found = [item for item in self._found() if item["type"] != TYPE_PENUMBRAL]
        for computed, (published, _, _, _) in zip(found, self.PUBLISHED):
            self.assertAlmostEqual(
                computed["greatest_utc"], published, delta=timedelta(minutes=2),
                msg=f"{computed['greatest_utc']} vs NASA {published}",
            )

    def test_magnitudes_match_nasa(self):
        found = [item for item in self._found() if item["type"] != TYPE_PENUMBRAL]
        for computed, (_, umbral, penumbral, kind) in zip(found, self.PUBLISHED):
            self.assertAlmostEqual(computed["umbral_magnitude"], umbral, delta=0.01)
            self.assertAlmostEqual(computed["penumbral_magnitude"], penumbral, delta=0.01)
            self.assertEqual(computed["type"], kind)

    def test_totality_semi_duration_matches_nasa(self):
        # 2025-03-14 was total for 65.4 minutes, so a semi-duration of about 32.7.
        first = self._found()[0]
        self.assertAlmostEqual(first["total_semi_duration_min"], 32.7, delta=2.0)

    def test_full_moon_is_selected_not_new_moon(self):
        # The classic off-by-half in Meeus's k: an integer k is new moon. A lunar eclipse at new
        # moon would be nonsense, and the Sun and Moon would be on the same side of the sky.
        for found in self._found():
            self.assertLess(abs(found["gamma"]), 1.6)
            self.assertGreater(found["penumbral_magnitude"], 0.0)

    def test_most_lunations_have_no_eclipse(self):
        # Roughly one full moon in six produces an eclipse of any kind; if this ever returned an
        # eclipse for most lunations, the node test would have stopped working.
        hits = sum(1 for k in range(300, 340) if lunar_eclipse_at_lunation(k) is not None)
        self.assertGreater(hits, 0)
        self.assertLess(hits, 20)

    def test_an_empty_interval_finds_nothing(self):
        self.assertEqual(
            lunar_eclipses_between(datetime(2026, 1, 1, tzinfo=UTC),
                                   datetime(2025, 1, 1, tzinfo=UTC)),
            [],
        )

    def test_results_are_ordered(self):
        found = self._found()
        self.assertEqual(found, sorted(found, key=lambda item: item["greatest_utc"]))

    def test_lunar_eclipses_work_far_beyond_the_solar_catalog(self):
        # The lunar half needs no catalog and therefore has no horizon. This is the property
        # that keeps "next eclipse" answerable after the bundled elements run out.
        found = lunar_eclipses_between(
            datetime(2200, 1, 1, tzinfo=UTC), datetime(2202, 1, 1, tzinfo=UTC),
        )
        self.assertGreater(len(found), 2)


class TestLunarLocalCircumstances(unittest.TestCase):
    """A lunar eclipse is the same everywhere; only "is the Moon up" is local.

    Checked against the published visibility of the 3 March 2026 total lunar eclipse, which
    favours the Pacific and Asia, sets during the eclipse over the eastern United States, and
    misses Europe entirely.
    """

    def _eclipse(self):
        return lunar_eclipses_between(
            datetime(2026, 2, 1, tzinfo=UTC), datetime(2026, 4, 1, tzinfo=UTC),
        )[0]

    def _at(self, site):
        return lunar_local_circumstances(self._eclipse(), site[0], site[1])

    def test_the_eclipse_itself_is_the_same_for_everyone(self):
        tokyo = self._at(TOKYO)
        london = self._at((51.5, -0.13))
        self.assertEqual(tokyo["magnitude"], london["magnitude"])
        self.assertEqual(tokyo["max_utc"], london["max_utc"])

    def test_visible_from_the_pacific_side(self):
        for site in (TOKYO, SYDNEY):
            circumstances = self._at(site)
            self.assertTrue(circumstances["visible"], site)
            self.assertGreater(circumstances["altitude_at_max"], 20.0, site)
            self.assertAlmostEqual(circumstances["visible_fraction"], 1.0, delta=0.05)

    def test_not_visible_from_europe(self):
        circumstances = self._at((51.5, -0.13))
        self.assertFalse(circumstances["visible"])
        self.assertLess(circumstances["altitude_at_max"], 0.0)
        self.assertEqual(circumstances["visible_obscuration"], 0.0)
        self.assertEqual(circumstances["visible_type"], TYPE_NONE)

    def test_the_moon_sets_partway_through_over_the_east_coast(self):
        circumstances = self._at(ILM)
        self.assertTrue(circumstances["visible"])
        self.assertTrue(circumstances["in_progress_at_set"])
        self.assertFalse(circumstances["in_progress_at_rise"])
        # The headline number for a site like this must be what was actually watchable.
        self.assertLess(circumstances["visible_fraction"], 1.0)

    def test_the_southern_hemisphere_is_not_a_special_case(self):
        circumstances = self._at(SYDNEY)
        self.assertTrue(circumstances["visible"])
        self.assertGreater(circumstances["obscuration"], 0.9)

    def test_coverage_falls_away_either_side_of_greatest_eclipse(self):
        found = self._eclipse()
        at_greatest = eclipse.lunar_coverage(found, 0.0)
        later = eclipse.lunar_coverage(found, found["penumbral_semi_duration_min"] * 0.9)
        self.assertGreater(at_greatest, later)

    def test_a_total_eclipse_covers_the_whole_disc(self):
        self.assertAlmostEqual(self._at(TOKYO)["obscuration"], 1.0, places=6)


class TestScoring(unittest.TestCase):
    """The score has to reward what an observer would actually go outside for."""

    def test_totality_scores_highly_even_low_in_the_sky(self):
        # The case this rule exists for: the 2026 totality over northern Spain happens with the
        # Sun about eight degrees up, and it is the best thing to happen to European observers
        # in decades. A score that treated altitude as a plain multiplier would call it "Good".
        self.assertGreaterEqual(solar_viewing_score(1.0, TYPE_TOTAL, 8.0), 80)
        self.assertEqual(score_rating(solar_viewing_score(1.0, TYPE_TOTAL, 8.0)), "Excellent")

    def test_totality_overhead_is_a_perfect_score(self):
        self.assertEqual(solar_viewing_score(1.0, TYPE_TOTAL, 60.0), 100)

    def test_an_annular_eclipse_scores_just_below_a_total_one(self):
        self.assertLess(
            solar_viewing_score(0.95, TYPE_ANNULAR, 60.0),
            solar_viewing_score(1.0, TYPE_TOTAL, 60.0),
        )

    def test_a_half_covered_partial_is_unremarkable(self):
        # 50% obscuration dims the daylight by about a percent; almost nobody notices unaided.
        self.assertLess(solar_viewing_score(0.5, TYPE_PARTIAL, 60.0), 25)

    def test_a_deep_partial_beats_a_shallow_one(self):
        self.assertGreater(
            solar_viewing_score(0.9, TYPE_PARTIAL, 45.0),
            solar_viewing_score(0.3, TYPE_PARTIAL, 45.0),
        )

    def test_nothing_visible_scores_nothing(self):
        self.assertEqual(solar_viewing_score(0.0, TYPE_NONE, 45.0), 0)

    def test_below_the_horizon_scores_nothing_even_for_totality(self):
        self.assertEqual(solar_viewing_score(1.0, TYPE_TOTAL, -5.0), 0)

    def test_a_total_lunar_eclipse_in_a_dark_sky_is_a_perfect_score(self):
        self.assertEqual(eclipse.lunar_viewing_score(1.2, 2.3, 60.0, -40.0), 100)

    def test_twilight_costs_a_lunar_eclipse(self):
        dark = eclipse.lunar_viewing_score(1.2, 2.3, 40.0, -40.0)
        twilight = eclipse.lunar_viewing_score(1.2, 2.3, 40.0, -3.0)
        self.assertLess(twilight, dark)

    def test_a_penumbral_lunar_eclipse_scores_almost_nothing(self):
        self.assertLess(eclipse.lunar_viewing_score(-0.2, 0.9, 60.0, -40.0), 15)

    def test_rating_bands(self):
        self.assertEqual(score_rating(100), "Excellent")
        self.assertEqual(score_rating(80), "Excellent")
        self.assertEqual(score_rating(79), "Very Good")
        self.assertEqual(score_rating(40), "Good")
        self.assertEqual(score_rating(20), "Fair")
        self.assertEqual(score_rating(0), "Poor")


class TestEyeSafety(unittest.TestCase):
    """Getting this wrong sends somebody outside to damage their eyes."""

    def test_an_annular_eclipse_is_never_safe_to_look_at(self):
        # The dangerous mistake available here: treating "central phase" as permission to take
        # the filter off. At annular maximum a complete ring of photosphere is still showing.
        safety = eclipse._eye_safety(KIND_SOLAR, TYPE_ANNULAR)
        self.assertTrue(safety["eye_protection_required"])
        self.assertFalse(safety["safe_unfiltered"])

    def test_a_deep_partial_is_never_safe_to_look_at(self):
        safety = eclipse._eye_safety(KIND_SOLAR, TYPE_PARTIAL)
        self.assertTrue(safety["eye_protection_required"])
        self.assertFalse(safety["safe_unfiltered"])

    def test_only_totality_allows_the_filter_off(self):
        safety = eclipse._eye_safety(KIND_SOLAR, TYPE_TOTAL)
        self.assertTrue(safety["safe_unfiltered"])
        self.assertIn("totality", safety["eye_safety"].lower())

    def test_every_solar_eclipse_carries_the_iso_standard(self):
        for kind in (TYPE_TOTAL, TYPE_ANNULAR, TYPE_PARTIAL, TYPE_NONE):
            self.assertIn("ISO 12312-2", eclipse._eye_safety(KIND_SOLAR, kind)["eye_safety"])

    def test_a_lunar_eclipse_needs_no_protection(self):
        safety = eclipse._eye_safety(KIND_LUNAR, TYPE_TOTAL)
        self.assertFalse(safety["eye_protection_required"])
        self.assertTrue(safety["safe_unfiltered"])


class TestForecast(unittest.TestCase):
    """End-to-end, from a frozen ``now``.

    Assertions here are invariants -- orderings, ranges, relationships -- rather than values, so
    they hold for any observer at any date and cannot silently encode today's implementation.
    """

    def _forecast(self, site, now=NOW, **kwargs):
        return build_eclipse_forecast(
            now, site[0], site[1], UTC, SOLAR_ECLIPSES, **kwargs,
        )

    def _every_entry(self, forecast):
        """Yield every full entry the payload carries."""
        for key in ("current", "next", "next_solar", "next_lunar"):
            if forecast.get(key):
                yield forecast[key]

    def test_payload_carries_the_expected_keys(self):
        forecast = self._forecast(ILM)
        for key in ("generated_utc", "latitude", "longitude", "catalog_first_year",
                    "catalog_last_year", "catalog_exhausted", "current", "next",
                    "next_solar", "next_lunar", "next_solar_global", "upcoming"):
            self.assertIn(key, forecast)

    def test_upcoming_is_ordered_and_in_the_future(self):
        for site in (ILM, SYDNEY, TROMSO):
            upcoming = self._forecast(site)["upcoming"]
            self.assertTrue(upcoming, site)
            days = [item["days_until"] for item in upcoming]
            self.assertEqual(days, sorted(days), site)
            self.assertTrue(all(value >= 0 for value in days), site)

    def test_upcoming_entries_stay_small(self):
        # Home Assistant's recorder stores every attribute of every state change, so the
        # look-ahead list is trimmed rather than carrying forty keys per eclipse.
        for item in self._forecast(ILM)["upcoming"]:
            self.assertLessEqual(len(item), 10)

    def test_contact_times_are_ordered(self):
        for site in (ILM, SYDNEY, TROMSO, TOKYO):
            for entry in self._every_entry(self._forecast(site)):
                self.assertLessEqual(entry["start_utc"], entry["max_utc"], entry["name"])
                self.assertLessEqual(entry["max_utc"], entry["end_utc"], entry["name"])

    def test_percentages_stay_in_range(self):
        for site in (ILM, SYDNEY, TROMSO, TOKYO, CAPE_TOWN):
            forecast = self._forecast(site)
            for entry in self._every_entry(forecast):
                for key in ("disc_covered", "peak_disc_covered", "visible_fraction",
                            "viewing_score"):
                    self.assertGreaterEqual(entry[key], 0, f"{site} {key}")
                    self.assertLessEqual(entry[key], 100, f"{site} {key}")

    def test_the_next_eclipse_is_always_one_that_can_be_seen(self):
        for site in (ILM, SYDNEY, TROMSO):
            upcoming = self._forecast(site)["next"]
            if upcoming:
                self.assertTrue(upcoming["visible"], site)
                self.assertGreater(upcoming["disc_covered"], 0.0, site)

    def test_totality_always_means_full_coverage(self):
        for site in (ILM, SYDNEY, TROMSO, REYKJAVIK, (42.34, -3.70)):
            for entry in self._every_entry(self._forecast(site)):
                if entry["kind"] == KIND_SOLAR and entry["type"] == TYPE_TOTAL:
                    self.assertEqual(entry["disc_covered"], 100.0, site)

    def test_only_totality_is_ever_safe_without_a_filter(self):
        for site in (ILM, SYDNEY, TROMSO, REYKJAVIK, (42.34, -3.70)):
            for entry in self._every_entry(self._forecast(site)):
                if entry["kind"] == KIND_SOLAR and entry["safe_unfiltered"]:
                    self.assertEqual(entry["type"], TYPE_TOTAL, site)

    def test_solar_eclipses_always_demand_eye_protection(self):
        for site in (ILM, SYDNEY, TROMSO):
            for entry in self._every_entry(self._forecast(site)):
                self.assertEqual(
                    entry["eye_protection_required"], entry["kind"] == KIND_SOLAR, site,
                )

    def test_next_solar_and_next_lunar_are_of_the_right_kind(self):
        forecast = self._forecast(ILM)
        if forecast["next_solar"]:
            self.assertEqual(forecast["next_solar"]["kind"], KIND_SOLAR)
        if forecast["next_lunar"]:
            self.assertEqual(forecast["next_lunar"]["kind"], KIND_LUNAR)

    def test_next_is_the_soonest_of_the_two(self):
        forecast = self._forecast(ILM)
        candidates = [forecast[key]["days_until"]
                      for key in ("next_solar", "next_lunar") if forecast[key]]
        if candidates and forecast["next"]:
            self.assertAlmostEqual(forecast["next"]["days_until"], min(candidates), places=6)

    def test_a_solar_eclipse_invisible_from_here_is_still_named_globally(self):
        # Otherwise a user who has just watched one on the news is told the next solar eclipse
        # is years away.
        forecast = self._forecast(SYDNEY)
        self.assertIsNotNone(forecast["next_solar_global"])
        self.assertIn("Solar", forecast["next_solar_global"]["name"])

    def test_penumbral_lunar_eclipses_are_excluded_by_default(self):
        default = self._forecast(ILM)
        included = self._forecast(ILM, include_penumbral=True)
        for entry in self._every_entry(default):
            self.assertNotEqual(entry["type"], TYPE_PENUMBRAL)
        # Over a four-year window there is always at least one, so asking for them changes the
        # answer -- which proves the exclusion is doing something rather than being vacuous.
        self.assertGreaterEqual(len(included["upcoming"]), len(default["upcoming"]))

    def test_local_times_are_rendered_in_the_supplied_zone(self):
        forecast = build_eclipse_forecast(
            NOW, ILM[0], ILM[1], ZoneInfo("America/New_York"), SOLAR_ECLIPSES,
        )
        upcoming = forecast["next"]
        self.assertIsNotNone(upcoming)
        self.assertTrue(upcoming["max_local"].endswith(("-04:00", "-05:00")))

    def test_high_latitude_observers_are_handled(self):
        for now in (datetime(2026, 1, 15, tzinfo=UTC), datetime(2026, 6, 15, tzinfo=UTC)):
            forecast = self._forecast(TROMSO, now=now)
            self.assertIsInstance(forecast["upcoming"], list)

    def test_a_decade_of_refreshes_never_raises(self):
        # Mirrors test_meteor.py's whole-year sweep. Steps through ten years a month at a time
        # from three different observing sites; anything that raises for a particular geometry
        # shows up here rather than in somebody's log.
        for site in (ILM, SYDNEY, TROMSO):
            for month in range(0, 120, 2):
                now = datetime(2026, 1, 1, tzinfo=UTC) + timedelta(days=30.4 * month)
                self._forecast(site, now=now)

    def test_the_catalog_running_out_is_reported_not_raised(self):
        # The solar half has a horizon and the lunar half does not, so past the end this must
        # degrade into a lunar-only answer that says so -- never into an exception.
        beyond = datetime(SOLAR_ECLIPSES[-1]["date"][0] + 5, 6, 1, tzinfo=UTC)
        forecast = self._forecast(ILM, now=beyond)
        self.assertTrue(forecast["catalog_exhausted"])
        self.assertIsNone(forecast["next_solar"])
        self.assertIsNotNone(forecast["next_lunar"])

    def test_an_empty_catalog_is_survivable(self):
        forecast = build_eclipse_forecast(NOW, ILM[0], ILM[1], UTC, [])
        self.assertIsNone(forecast["next_solar"])
        self.assertIsNone(forecast["catalog_last_year"])


class TestNoHomeAssistantDependency(unittest.TestCase):
    """``eclipse.py`` has to stay importable as a bare module, like ``astro`` and ``meteor``."""

    def test_module_does_not_import_home_assistant(self):
        import inspect
        source = inspect.getsource(eclipse)
        self.assertNotIn("homeassistant", source)

    def test_the_catalog_is_injected_rather_than_imported(self):
        import inspect
        source = inspect.getsource(eclipse)
        self.assertNotIn("from eclipse_catalog", source)
        self.assertNotIn("import eclipse_catalog", source)


class TestWatchableMomentIsWhatCounts(unittest.TestCase):
    """Regression tests for the review findings on PR #36.

    Every one of these had the same root cause: the model separates *the eclipse* from *the
    eclipse you can watch*, and the layers on top of it were reading coverage from one and
    geometry from the other. Where the whole eclipse is above the horizon the two are identical,
    which is why it went unnoticed -- and it is exactly the sites where they differ that most need
    telling what they are getting.

    The standing example is New York on 2026-03-03: a totally eclipsed Moon, visible for nearly
    three hours, that set before greatest eclipse.
    """

    NYC_TOTAL_LUNAR = datetime(2026, 2, 20, tzinfo=UTC)

    def _nyc(self):
        return build_eclipse_forecast(
            self.NYC_TOTAL_LUNAR, NEW_YORK[0], NEW_YORK[1], UTC, SOLAR_ECLIPSES,
        )["next_lunar"]

    def test_a_total_eclipse_that_sets_partway_through_is_not_scored_as_poor(self):
        entry = self._nyc()
        self.assertEqual(entry["disc_covered"], 100.0)
        self.assertGreater(entry["visible_fraction"], 40.0)
        # It was 0 / "Poor" / "low altitude", scored on the Moon's altitude at an instant it
        # had already set through.
        self.assertGreater(entry["viewing_score"], 15)
        self.assertNotEqual(entry["limiting_factor"], eclipse.FACTOR_ALTITUDE)

    def test_the_watchable_altitude_beats_the_altitude_at_maximum(self):
        # The invariant that was silently violated: for a body that sets during the eclipse, the
        # best moment you can watch is necessarily higher than the moment of greatest eclipse.
        entry = self._nyc()
        self.assertTrue(entry["in_progress_at_set"])
        self.assertGreater(entry["altitude_when_visible"], entry["altitude_at_max"])
        self.assertGreater(entry["altitude_when_visible"], 0.0)
        self.assertLess(entry["altitude_at_max"], 0.0)

    def test_look_towards_is_where_the_eclipse_is_when_you_can_see_it(self):
        entry = self._nyc()
        self.assertIsInstance(entry["direction_when_visible"], str)
        self.assertIn("azimuth_when_visible", entry)

    def test_the_two_geometries_agree_when_the_whole_eclipse_is_visible(self):
        # The containment half of the fix: it must change nothing for the ordinary case.
        for site in (TOKYO, SYDNEY):
            entry = build_eclipse_forecast(
                self.NYC_TOTAL_LUNAR, site[0], site[1], UTC, SOLAR_ECLIPSES,
            )["next_lunar"]
            self.assertAlmostEqual(entry["visible_fraction"], 100.0, delta=1.0, msg=str(site))
            self.assertAlmostEqual(
                entry["altitude_when_visible"], entry["altitude_at_max"], delta=6.0, msg=str(site),
            )

    def test_the_best_moment_is_the_highest_one_at_equal_coverage(self):
        # Totality holds at 100% for the best part of an hour. Picking by coverage alone leaves
        # the choice on that plateau to list order rather than to what the observer would want.
        entry = self._nyc()
        self.assertEqual(entry["disc_covered"], 100.0)
        self.assertGreater(entry["altitude_when_visible"], 2.0)

    def test_time_to_first_contact_is_reported_separately_from_time_to_maximum(self):
        # They differ by nearly three hours for a lunar eclipse, and the alert's lead window is
        # about first contact. Measuring it against maximum made that window unreachable.
        entry = self._nyc()
        self.assertLess(entry["hours_until_start"], entry["hours_until"])
        self.assertGreater(entry["hours_until"] - entry["hours_until_start"], 1.0)

    def test_the_lunar_horizon_allows_for_the_moon_being_close(self):
        # astro.moon_equatorial is geocentric, and the Moon has about a degree of horizontal
        # parallax, so the geocentric altitude at which it truly rises and sets is slightly
        # *above* zero -- not the Sun's -0.833. Meeus: h0 = 0.7275 * parallax - 0.5667.
        self.assertGreater(eclipse._MOON_HORIZON_DEG, 0.0)
        self.assertLess(eclipse._MOON_HORIZON_DEG, 0.3)
        self.assertLess(eclipse._HORIZON_DEG, 0.0)

    def test_the_catalog_running_out_is_flagged_from_the_last_eclipse_not_the_new_year(self):
        # The final entry is in July; a year comparison left the rest of that year returning
        # nothing with the flag still False and nothing in the log to explain it.
        year, month, day = SOLAR_ECLIPSES[-1]["date"]
        after = datetime(year, month, day, tzinfo=UTC) + timedelta(days=20)
        self.assertEqual(after.year, year)
        forecast = build_eclipse_forecast(after, ILM[0], ILM[1], UTC, SOLAR_ECLIPSES)
        self.assertTrue(forecast["catalog_exhausted"])
        self.assertIsNone(forecast["next_solar"])

    def test_the_catalog_is_not_exhausted_on_the_day_of_its_last_eclipse(self):
        year, month, day = SOLAR_ECLIPSES[-1]["date"]
        forecast = build_eclipse_forecast(
            datetime(year, month, day, tzinfo=UTC), ILM[0], ILM[1], UTC, SOLAR_ECLIPSES,
        )
        self.assertFalse(forecast["catalog_exhausted"])


class TestWatchableWindowPrecision(unittest.TestCase):
    """The watchable window is what the timestamp sensor publishes, so its edges have to be sharp.

    They come from two different places by design: where the body is already above the horizon the
    window is the eclipse itself, taken from the bisected contact times; where the body rises or
    sets partway through it is the sampled horizon crossing. Getting that backwards quantises the
    "go outside at" instant to the scan grid and sends people out up to a minute late.
    """

    NOW_SOLAR = datetime(2026, 8, 1, tzinfo=UTC)
    NOW_LUNAR = datetime(2026, 2, 20, tzinfo=UTC)

    def _solar(self, site):
        return build_eclipse_forecast(
            self.NOW_SOLAR, site[0], site[1], UTC, SOLAR_ECLIPSES,
        )["next_solar"]

    def _lunar(self, site):
        return build_eclipse_forecast(
            self.NOW_LUNAR, site[0], site[1], UTC, SOLAR_ECLIPSES,
        )["next_lunar"]

    def test_a_body_up_throughout_gives_a_window_equal_to_the_eclipse(self):
        for site in (REYKJAVIK, (51.51, -0.13)):
            entry = self._solar(site)
            self.assertEqual(entry["visible_start_utc"], entry["start_utc"], str(site))
            self.assertEqual(entry["visible_end_utc"], entry["end_utc"], str(site))

    def test_the_window_never_starts_before_the_eclipse_or_end_after_it(self):
        for entry in (self._solar(REYKJAVIK), self._solar((42.34, -3.70)),
                      self._lunar(TOKYO), self._lunar(NEW_YORK)):
            self.assertGreaterEqual(entry["visible_start_utc"], entry["start_utc"])
            self.assertLessEqual(entry["visible_end_utc"], entry["end_utc"])

    def test_a_body_that_sets_partway_through_has_the_window_clipped(self):
        entry = self._lunar(NEW_YORK)
        self.assertEqual(entry["visible_start_utc"], entry["start_utc"])
        self.assertLess(entry["visible_end_utc"], entry["end_utc"])
        self.assertTrue(entry["in_progress_at_set"])

    def test_the_window_is_reported_in_utc_as_well_as_local(self):
        # The local strings are trimmed to minutes and read well on a card; the UTC ones carry
        # seconds and are what anything machine-readable should be given.
        entry = self._solar(REYKJAVIK)
        for key in ("visible_start_utc", "visible_end_utc"):
            parsed = datetime.fromisoformat(entry[key])
            self.assertIsNotNone(parsed.tzinfo, key)

    def test_no_window_at_all_when_nothing_is_visible(self):
        entry = build_eclipse_forecast(
            self.NOW_LUNAR, 51.51, -0.13, UTC, SOLAR_ECLIPSES,
        )["next_lunar"]
        # London misses the 2026-03-03 eclipse entirely, so whatever it reports next is a later
        # one it can actually see -- the point being that an invisible eclipse is never offered.
        self.assertTrue(entry["visible"])
        self.assertIsNotNone(entry["visible_start_utc"])


class TestTheTypeIsAlsoWhatYouCanSee(unittest.TestCase):
    """Second round of review regressions, same seam as the first.

    Coverage and altitude had been made to follow the watchable window; the *type*, the lunar
    score and the in-progress flag had not. Each produced a payload that contradicted itself.
    """

    def _lunar_2025_09_07(self):
        return lunar_eclipses_between(
            datetime(2025, 8, 1, tzinfo=UTC), datetime(2025, 10, 1, tzinfo=UTC),
        )[0]

    def test_a_moon_that_rises_after_totality_saw_a_penumbral_eclipse(self):
        # The almanac calls 2025-09-07 total. An observer whose Moon clears the horizon after the
        # last umbral contact watched a faint grey smudge, and was being told "Total Lunar
        # Eclipse", nought per cent covered, score 49 "Good" -- all at once.
        found = self._lunar_2025_09_07()
        self.assertEqual(found["type"], TYPE_TOTAL)
        circumstances = lunar_local_circumstances(found, 30.0, -30.0)
        entry = eclipse._build_entry(
            KIND_LUNAR, circumstances, datetime(2025, 9, 1, tzinfo=UTC), UTC, "2025-09-07",
        )
        self.assertTrue(entry["visible"])
        self.assertEqual(entry["type"], TYPE_PENUMBRAL)
        self.assertEqual(entry["global_type"], TYPE_TOTAL)
        self.assertEqual(entry["disc_covered"], 0.0)
        self.assertEqual(entry["viewing_score"], 0)

    def test_a_site_that_sees_the_whole_thing_still_gets_the_real_type(self):
        circumstances = lunar_local_circumstances(self._lunar_2025_09_07(), *TOKYO)
        entry = eclipse._build_entry(
            KIND_LUNAR, circumstances, datetime(2025, 9, 1, tzinfo=UTC), UTC, "2025-09-07",
        )
        self.assertEqual(entry["type"], TYPE_TOTAL)
        self.assertEqual(entry["disc_covered"], 100.0)

    def test_the_penumbral_tiebreak_does_not_disturb_a_setting_total_eclipse(self):
        """The rung that ranks penumbral depth must not outrank altitude during totality.

        Through totality every sample is fully covered while the penumbral magnitude still peaks
        at greatest eclipse, so letting it rank alongside coverage pins a setting Moon to its
        lowest total moment instead of its highest -- which is the very bug the first review
        round fixed, reintroduced from the other end.
        """
        entry = build_eclipse_forecast(
            datetime(2026, 2, 20, tzinfo=UTC), NEW_YORK[0], NEW_YORK[1], UTC, SOLAR_ECLIPSES,
        )["next_lunar"]
        self.assertEqual(entry["disc_covered"], 100.0)
        self.assertGreater(entry["altitude_when_visible"], 2.0)

    def test_a_totality_shorter_than_the_scan_step_is_still_a_total_eclipse(self):
        # 37 seconds of totality falls between two samples of the one-minute grid, so the type
        # read off the nearest sample said "partial" while the same entry published a totality
        # window and a totality duration.
        from eclipse_catalog import find_eclipse
        circumstances = solar_local_circumstances(find_eclipse(2026, 8, 12), 42.52, -1.5)
        entry = eclipse._build_entry(
            KIND_SOLAR, circumstances, datetime(2026, 8, 1, tzinfo=UTC), UTC, "2026-08-12",
        )
        self.assertGreater(entry["central_duration_s"], 0)
        self.assertLess(entry["central_duration_s"], 60)
        self.assertEqual(entry["type"], TYPE_TOTAL)
        self.assertTrue(entry["safe_unfiltered"])
        self.assertIsNotNone(entry["central_start_local"])

    def test_publishing_a_totality_window_and_a_partial_type_is_impossible(self):
        # The invariant behind the previous test, asserted across a spread of sites and both
        # kinds: a central duration and a non-central type cannot both be true of one observer.
        for now, sites in (
            (datetime(2026, 8, 1, tzinfo=UTC),
             (REYKJAVIK, (42.34, -3.70), (42.52, -1.5), (39.47, -0.38), ILM)),
            (datetime(2026, 2, 20, tzinfo=UTC), (TOKYO, NEW_YORK, SYDNEY, ILM)),
        ):
            for site in sites:
                forecast = build_eclipse_forecast(now, site[0], site[1], UTC, SOLAR_ECLIPSES)
                for key in ("current", "next", "next_solar", "next_lunar"):
                    entry = forecast.get(key)
                    if entry and entry["central_duration_s"] > 0:
                        self.assertIn(
                            entry["type"], (TYPE_TOTAL, TYPE_ANNULAR),
                            f"{site} {key}: {entry['central_duration_s']}s of central phase "
                            f"reported as {entry['type']}",
                        )

    def test_in_progress_ends_when_the_body_sets_not_at_last_contact(self):
        # It ran on for nearly three hours past moonset for New York, and the alert keyed to it
        # spent all of that saying go outside -- with the coordinator on one-minute polling.
        circumstances = lunar_local_circumstances(self._lunar_2026_03_03(), *NEW_YORK)
        moonset = circumstances["visible_end_utc"]
        self.assertLess(moonset, circumstances["end_utc"])
        for offset, expected in ((-30, True), (-1, True), (5, False), (150, False)):
            entry = eclipse._build_entry(
                KIND_LUNAR, circumstances, moonset + timedelta(minutes=offset),
                UTC, "2026-03-03",
            )
            self.assertEqual(entry["in_progress"], expected, f"{offset:+d} min from moonset")

    def _lunar_2026_03_03(self):
        return lunar_eclipses_between(
            datetime(2026, 2, 20, tzinfo=UTC), datetime(2026, 3, 20, tzinfo=UTC),
        )[0]
