"""Validation tests for meteor_catalog.py.

These assert **structure and ranges**, never specific published values, so that correcting a
shower's parameters against a newer IMO working list never breaks CI. The one exception is the
solar-longitude round-trip: that verifies the catalog is internally consistent with the astronomy,
which is a genuine invariant rather than a data choice.
"""

import unittest
from datetime import datetime, timezone

from astro import next_solar_longitude_after, normalize_degrees, wrap180
from meteor_catalog import METEOR_SHOWERS, REQUIRED_FIELDS

UTC = timezone.utc


class TestCatalogStructure(unittest.TestCase):
    """Every entry must be complete and well-formed."""

    def test_catalog_is_populated(self):
        self.assertGreaterEqual(len(METEOR_SHOWERS), 25)

    def test_all_required_fields_present(self):
        for shower in METEOR_SHOWERS:
            for field in REQUIRED_FIELDS:
                self.assertIn(field, shower, f"{shower.get('code')} is missing '{field}'")

    def test_codes_are_unique(self):
        codes = [shower["code"] for shower in METEOR_SHOWERS]
        self.assertEqual(len(codes), len(set(codes)), "duplicate shower codes")

    def test_codes_are_three_uppercase_letters(self):
        for shower in METEOR_SHOWERS:
            code = shower["code"]
            self.assertEqual(len(code), 3, f"{code} is not a 3-letter IAU code")
            self.assertTrue(code.isupper(), f"{code} should be uppercase")
            self.assertTrue(code.isalpha(), f"{code} should be alphabetic")

    def test_names_are_non_empty(self):
        for shower in METEOR_SHOWERS:
            self.assertTrue(shower["name"].strip(), f"{shower['code']} has an empty name")


class TestCatalogRanges(unittest.TestCase):
    """Every numeric parameter must be physically plausible."""

    def test_solar_longitudes_in_range(self):
        for shower in METEOR_SHOWERS:
            for field in ("sol_lon_max", "sol_lon_start", "sol_lon_end"):
                value = shower[field]
                self.assertGreaterEqual(value, 0.0, f"{shower['code']}.{field}")
                self.assertLess(value, 360.0, f"{shower['code']}.{field}")

    def test_radiant_coordinates_in_range(self):
        for shower in METEOR_SHOWERS:
            self.assertGreaterEqual(shower["ra"], 0.0, f"{shower['code']}.ra")
            self.assertLess(shower["ra"], 360.0, f"{shower['code']}.ra")
            self.assertGreaterEqual(shower["dec"], -90.0, f"{shower['code']}.dec")
            self.assertLessEqual(shower["dec"], 90.0, f"{shower['code']}.dec")

    def test_zhr_positive(self):
        for shower in METEOR_SHOWERS:
            self.assertGreater(shower["zhr"], 0, f"{shower['code']}.zhr")
            self.assertLessEqual(shower["zhr"], 500, f"{shower['code']}.zhr implausibly high")

    def test_population_index_above_one(self):
        """A population index at or below 1 would invert the sky-brightness correction."""
        for shower in METEOR_SHOWERS:
            self.assertGreater(shower["r"], 1.0, f"{shower['code']}.r")
            self.assertLess(shower["r"], 5.0, f"{shower['code']}.r implausibly high")

    def test_geocentric_velocity_plausible(self):
        """Meteoroid entry speeds are bounded by orbital mechanics: roughly 11-72 km/s."""
        for shower in METEOR_SHOWERS:
            self.assertGreaterEqual(shower["v_geo"], 10, f"{shower['code']}.v_geo")
            self.assertLessEqual(shower["v_geo"], 75, f"{shower['code']}.v_geo")

    def test_variable_flag_is_boolean(self):
        for shower in METEOR_SHOWERS:
            self.assertIsInstance(shower["variable"], bool, f"{shower['code']}.variable")

    def test_activity_slope_is_none_or_positive(self):
        for shower in METEOR_SHOWERS:
            slope = shower["b"]
            if slope is not None:
                self.assertGreater(slope, 0.0, f"{shower['code']}.b")


class TestActivityWindows(unittest.TestCase):
    """Activity windows must actually contain their maximum, wraparound included."""

    def test_maximum_inside_window(self):
        for shower in METEOR_SHOWERS:
            width = normalize_degrees(shower["sol_lon_end"] - shower["sol_lon_start"])
            offset = normalize_degrees(shower["sol_lon_max"] - shower["sol_lon_start"])
            self.assertLessEqual(
                offset, width,
                f"{shower['code']}: maximum {shower['sol_lon_max']} is outside "
                f"[{shower['sol_lon_start']}, {shower['sol_lon_end']}]",
            )

    def test_windows_have_sensible_width(self):
        for shower in METEOR_SHOWERS:
            width = normalize_degrees(shower["sol_lon_end"] - shower["sol_lon_start"])
            self.assertGreater(width, 0.5, f"{shower['code']} window is impossibly narrow")
            self.assertLess(width, 120.0, f"{shower['code']} window is implausibly wide")

    def test_maximum_not_exactly_on_an_edge(self):
        """A maximum sitting on a window edge would make the derived activity slope degenerate."""
        for shower in METEOR_SHOWERS:
            to_start = abs(wrap180(shower["sol_lon_max"] - shower["sol_lon_start"]))
            to_end = abs(wrap180(shower["sol_lon_end"] - shower["sol_lon_max"]))
            self.assertGreater(min(to_start, to_end), 0.1, f"{shower['code']}")


class TestCatalogAstronomyConsistency(unittest.TestCase):
    """The catalog must agree with the astronomy that consumes it.

    Solar longitudes are stored rather than dates precisely so peaks recompute correctly every
    year. These tests confirm the stored values land where the published calendars say they do.
    """

    KNOWN_PEAKS = {
        "QUA": (1, (3, 4)),
        "LYR": (4, (22, 23)),
        "ETA": (5, (5, 6)),
        "PER": (8, (12, 13)),
        "ORI": (10, (21, 22)),
        "LEO": (11, (17, 18)),
        "GEM": (12, (13, 14)),
        "URS": (12, (21, 22, 23)),
    }

    def test_major_showers_peak_on_published_dates(self):
        by_code = {shower["code"]: shower for shower in METEOR_SHOWERS}
        for code, (month, days) in self.KNOWN_PEAKS.items():
            shower = by_code[code]
            peak = next_solar_longitude_after(
                shower["sol_lon_max"], datetime(2026, 1, 1, tzinfo=UTC),
            )
            self.assertEqual(peak.month, month, f"{code} peaked in month {peak.month}: {peak}")
            self.assertIn(peak.day, days, f"{code} peaked on day {peak.day}: {peak}")

    def test_peaks_are_stable_across_years(self):
        """The same solar longitude must land on nearly the same calendar date every year."""
        for shower in METEOR_SHOWERS:
            peaks = [
                next_solar_longitude_after(
                    shower["sol_lon_max"], datetime(year, 1, 1, tzinfo=UTC),
                )
                for year in (2026, 2027, 2028)
            ]
            days_of_year = [int(peak.strftime("%j")) for peak in peaks]
            self.assertLessEqual(
                max(days_of_year) - min(days_of_year), 2,
                f"{shower['code']} drifts more than 2 days between years: {peaks}",
            )


if __name__ == "__main__":
    unittest.main()
