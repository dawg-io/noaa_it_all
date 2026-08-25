"""Unit tests for eclipse_catalog.py -- structure, and a self-check against NASA's own answers.

Two kinds of test live here, and the second is the one that matters.

The first is structural, and mirrors ``test_meteor_catalog.py``: required fields, sane ranges,
ordering. It catches a mangled regeneration.

The second runs this integration's own solver at the point on Earth where NASA says each eclipse
is greatest, and checks it reproduces NASA's published time, magnitude and Sun altitude there.
Those figures are carried in the catalog itself, so this is 114 independent regression cases
containing **no hand-typed expected values** -- which means it cannot rot, cannot disagree with a
future regeneration, and catches a sign error, a missing flattening term or a dropped delta-T all
at once. It is the reason those ``greatest_*`` fields exist.
"""

import unittest
from datetime import timezone

from astro import datetime_from_jd, delta_t_seconds
from eclipse import solar_local_circumstances
from eclipse_catalog import (
    ACKNOWLEDGEMENT,
    CATALOG_END_YEAR,
    CATALOG_START_YEAR,
    ECLIPSE_TYPES,
    REQUIRED_FIELDS,
    SOLAR_ECLIPSES,
    eclipses_in_year,
    find_eclipse,
)

UTC = timezone.utc

#: Eclipses whose shadow axis misses Earth's centre by more than this are "non-central": the axis
#: passes off the limb entirely, so NASA's greatest-eclipse point sits on the horizon at grazing
#: incidence. The geometry there is genuinely degenerate -- the Sun is at 0.0 degrees altitude by
#: definition -- and magnitude becomes hypersensitive to the 0.1-degree rounding of the published
#: coordinates. They are held to a looser bound rather than excluded, because away from the limb
#: they produce perfectly ordinary partial eclipses that the same code has to get right.
GRAZING_GAMMA = 0.99

#: NASA publishes the greatest-eclipse point to a tenth of a degree, which is about eleven
#: kilometres. Where the path of totality is not much wider than that, the stored coordinates may
#: simply not be on it -- the 2067 hybrid eclipse is central over a strip four kilometres across.
#: Duration is therefore only checked where the path is comfortably wider than the rounding.
NARROW_PATH_KM = 25.0


class TestCatalogStructure(unittest.TestCase):
    """Every entry has to carry every field, in range."""

    def test_catalog_is_not_empty(self):
        self.assertGreater(len(SOLAR_ECLIPSES), 50)

    def test_every_entry_has_every_required_field(self):
        for entry in SOLAR_ECLIPSES:
            for field in REQUIRED_FIELDS:
                self.assertIn(field, entry, f"{entry.get('date')} is missing {field}")

    def test_no_entry_carries_unexpected_fields(self):
        for entry in SOLAR_ECLIPSES:
            self.assertEqual(set(entry) - set(REQUIRED_FIELDS), set(), str(entry.get("date")))

    def test_types_are_from_the_known_set(self):
        for entry in SOLAR_ECLIPSES:
            self.assertIn(entry["type"], ECLIPSE_TYPES)

    def test_dates_are_unique_and_ascending(self):
        dates = [entry["date"] for entry in SOLAR_ECLIPSES]
        self.assertEqual(dates, sorted(dates))
        self.assertEqual(len(dates), len(set(dates)))

    def test_dates_lie_inside_the_declared_span(self):
        for entry in SOLAR_ECLIPSES:
            self.assertGreaterEqual(entry["date"][0], CATALOG_START_YEAR)
            self.assertLessEqual(entry["date"][0], CATALOG_END_YEAR)

    def test_span_constants_match_the_data(self):
        # Two static constants compared against each other, so this never goes stale. A check of
        # the form "the catalog reaches at least N years past today" would pass now and start
        # failing on old checkouts later, which is a test that measures the calendar.
        self.assertEqual(SOLAR_ECLIPSES[0]["date"][0], CATALOG_START_YEAR)
        self.assertEqual(SOLAR_ECLIPSES[-1]["date"][0], CATALOG_END_YEAR)

    def test_polynomials_have_a_uniform_arity(self):
        for entry in SOLAR_ECLIPSES:
            for field in ("x", "y", "d", "mu", "l1", "l2"):
                self.assertEqual(len(entry[field]), 4, f"{entry['date']} {field}")

    def test_physical_quantities_are_in_range(self):
        for entry in SOLAR_ECLIPSES:
            where = entry["date"]
            self.assertLess(abs(entry["gamma"]), 1.6, where)
            self.assertGreater(entry["magnitude"], 0.0, where)
            self.assertLess(entry["magnitude"], 1.09, where)
            # The cone half-angles vary only with Earth's distance from the Sun over the year,
            # so they stay inside a narrow band -- wide enough to admit January and July,
            # tight enough that a column read out of the wrong field would not fit.
            for field in ("tanf1", "tanf2"):
                self.assertGreater(entry[field], 0.00455, f"{where} {field}")
                self.assertLess(entry[field], 0.00480, f"{where} {field}")
            self.assertLess(entry["tanf2"], entry["tanf1"], where)
            self.assertGreaterEqual(entry["path_width_km"], 0.0, where)
            self.assertGreaterEqual(entry["central_duration_s"], 0, where)

    def test_reference_instant_is_near_greatest_eclipse(self):
        # The guard on the day-boundary bug: t0 is an integer hour that can belong to the
        # neighbouring calendar day, and getting that wrong puts an eclipse a full day out
        # while leaving every other field looking perfectly reasonable.
        for entry in SOLAR_ECLIPSES:
            self.assertLess(abs(entry["t0_jd"] - entry["greatest_jd"]), 0.25, str(entry["date"]))

    def test_only_central_eclipses_carry_a_path(self):
        for entry in SOLAR_ECLIPSES:
            if entry["type"] == "partial":
                self.assertEqual(entry["path_width_km"], 0.0, str(entry["date"]))
                self.assertEqual(entry["central_duration_s"], 0, str(entry["date"]))

    def test_acknowledgement_is_present(self):
        # NASA's terms of use require it to travel with the data.
        self.assertIn("Espenak", ACKNOWLEDGEMENT)


class TestHelpers(unittest.TestCase):
    """The two lookup helpers the catalog exposes."""

    def test_eclipses_in_year_finds_them(self):
        found = eclipses_in_year(2026)
        self.assertTrue(found)
        self.assertTrue(all(entry["date"][0] == 2026 for entry in found))

    def test_eclipses_in_a_year_with_none_is_empty(self):
        self.assertEqual(eclipses_in_year(CATALOG_END_YEAR + 50), [])

    def test_find_eclipse_by_date(self):
        entry = find_eclipse(2026, 8, 12)
        self.assertIsNotNone(entry)
        self.assertEqual(entry["type"], "total")

    def test_find_eclipse_returns_none_for_an_ordinary_day(self):
        self.assertIsNone(find_eclipse(2026, 8, 13))


class TestDeltaTAgreesWithTheCatalog(unittest.TestCase):
    """``astro.delta_t_seconds`` must match the values NASA generated the elements with."""

    def test_polynomial_reproduces_every_catalogued_value(self):
        for entry in SOLAR_ECLIPSES:
            year, month, _ = entry["date"]
            computed = delta_t_seconds(year + (month - 0.5) / 12.0)
            self.assertAlmostEqual(
                computed, entry["delta_t"], delta=1.0,
                msg=f"delta-T disagrees for {entry['date']}",
            )


class TestSolverReproducesNasa(unittest.TestCase):
    """Run the solver at NASA's greatest-eclipse point and check it agrees with NASA.

    Every assertion here compares computed output against a figure NASA published and this
    catalog carries. There is nothing hand-typed to go stale, and regenerating the catalog from a
    newer revision of the Canon updates the inputs and the expected values together.
    """

    def _circumstances(self, entry):
        """Return the local circumstances at NASA's own greatest-eclipse coordinates."""
        return solar_local_circumstances(
            entry, entry["greatest_latitude"], entry["greatest_longitude"],
        )

    def _split(self):
        """Return the catalog partitioned into ordinary and grazing eclipses."""
        ordinary, grazing = [], []
        for entry in SOLAR_ECLIPSES:
            (grazing if abs(entry["gamma"]) > GRAZING_GAMMA else ordinary).append(entry)
        return ordinary, grazing

    def test_the_split_is_not_degenerate(self):
        ordinary, grazing = self._split()
        self.assertGreater(len(ordinary), 40)
        self.assertGreater(len(grazing), 5)

    def test_every_eclipse_is_visible_from_its_own_greatest_point(self):
        # The strongest single statement available: at the point NASA calls greatest eclipse,
        # every one of these must produce an eclipse. A coarse pre-filter that rejected a real
        # hit, or a longitude sign error, would show up here first and unmistakably.
        for entry in SOLAR_ECLIPSES:
            circumstances = self._circumstances(entry)
            self.assertIsNotNone(circumstances.get("max_utc"), str(entry["date"]))
            self.assertGreater(circumstances["magnitude"], 0.0, str(entry["date"]))

    def test_time_of_maximum_matches_nasa(self):
        for entry in SOLAR_ECLIPSES:
            computed = self._circumstances(entry)["max_utc"]
            published = datetime_from_jd(entry["greatest_jd"]).replace(tzinfo=UTC)
            self.assertLess(
                abs((computed - published).total_seconds()), 60.0,
                f"{entry['date']}: {computed} vs NASA {published}",
            )

    def test_magnitude_matches_nasa(self):
        ordinary, grazing = self._split()
        for entry in ordinary:
            self.assertAlmostEqual(
                self._circumstances(entry)["magnitude"], entry["magnitude"],
                delta=0.01, msg=str(entry["date"]),
            )
        for entry in grazing:
            self.assertAlmostEqual(
                self._circumstances(entry)["magnitude"], entry["magnitude"],
                delta=0.05, msg=str(entry["date"]),
            )

    def test_sun_altitude_matches_nasa(self):
        for entry in SOLAR_ECLIPSES:
            self.assertAlmostEqual(
                self._circumstances(entry)["altitude_at_max"], entry["greatest_altitude"],
                delta=1.0, msg=str(entry["date"]),
            )

    def test_local_type_matches_the_global_type_at_the_greatest_point(self):
        # At greatest eclipse the observer is on the axis, so what they see is by definition the
        # headline classification -- except for a hybrid, which is total along part of its path
        # and annular along the rest, and that is exactly what makes it hybrid.
        for entry in SOLAR_ECLIPSES:
            if entry["type"] == "hybrid" or abs(entry["gamma"]) > GRAZING_GAMMA:
                continue
            self.assertEqual(
                self._circumstances(entry)["local_type"], entry["type"], str(entry["date"]),
            )

    def test_central_duration_matches_nasa(self):
        # Published to the nearest second on the centre line, but the catalog's coordinates are
        # rounded to a tenth of a degree -- about eleven kilometres, which on a path a couple of
        # hundred kilometres wide is a real fraction of the way to the edge, where duration falls
        # away fastest. So this checks the right ballpark, not the published second -- and skips
        # the handful of paths narrower than the rounding itself.
        for entry in SOLAR_ECLIPSES:
            if entry["central_duration_s"] <= 0 or abs(entry["gamma"]) > GRAZING_GAMMA:
                continue
            if entry["path_width_km"] < NARROW_PATH_KM:
                continue
            computed = self._circumstances(entry)["central_duration_s"]
            self.assertAlmostEqual(
                computed, entry["central_duration_s"],
                delta=max(30.0, 0.15 * entry["central_duration_s"]),
                msg=f"{entry['date']}: {computed}s vs NASA {entry['central_duration_s']}s",
            )
