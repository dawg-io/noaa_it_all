"""Unit tests for meteor.py — pure functions, no Home Assistant dependency.

Covers the activity profile, the sky-brightness model, the scoring relation, and end-to-end
forecasts for observers where the interesting edge cases live: a northern mid-latitude site, the
southern hemisphere, and a high-latitude site in midsummer where astronomical night never arrives.

End-to-end assertions are deliberately stated as *ranges* around physically verified values, so
that a tweak to the empirical moonlight model does not break CI while a sign error still would.
"""

import unittest
from datetime import datetime, timedelta, timezone

from astro import DARKNESS_ASTRONOMICAL, DARKNESS_NAUTICAL, DARKNESS_NONE
from meteor import (
    FACTOR_DARKNESS,
    FACTOR_MOON,
    FACTOR_RADIANT,
    IDEAL_LIMITING_MAGNITUDE,
    activity_slope,
    build_meteor_forecast,
    is_active,
    limiting_factor,
    limiting_magnitude,
    moon_penalty,
    nearest_peak,
    observed_rate,
    score_rating,
    twilight_penalty,
    viewing_score,
    zhr_at,
)
from meteor_catalog import METEOR_SHOWERS

UTC = timezone.utc

# Observing sites used throughout. Wilmington NC matches an NWS office the integration ships.
ILM = (34.2675, -77.9011)
SYDNEY = (-33.87, 151.21)
TROMSO = (69.65, 18.96)

PERSEIDS = {
    "code": "PER", "name": "Perseids",
    "sol_lon_max": 140.0, "sol_lon_start": 114.46, "sol_lon_end": 150.87,
    "ra": 48.0, "dec": 58.0,
    "zhr": 100, "r": 2.2, "v_geo": 59,
    "constellation": "Perseus", "parent": "109P/Swift-Tuttle",
    "variable": False, "b": None,
}


def _by_code(code):
    return next(shower for shower in METEOR_SHOWERS if shower["code"] == code)


class TestActivityProfile(unittest.TestCase):
    """ZHR as a function of solar longitude."""

    def test_peak_returns_maximum_zhr(self):
        self.assertAlmostEqual(zhr_at(PERSEIDS, 140.0), 100.0, places=6)

    def test_zhr_falls_away_from_peak(self):
        self.assertLess(zhr_at(PERSEIDS, 135.0), zhr_at(PERSEIDS, 139.0))
        self.assertLess(zhr_at(PERSEIDS, 145.0), zhr_at(PERSEIDS, 141.0))

    def test_zhr_is_a_tenth_at_the_nearer_window_edge(self):
        """The derived slope is defined so activity drops by a decade at the window edge."""
        slope = activity_slope(PERSEIDS)
        half_width = 1.0 / slope
        self.assertAlmostEqual(zhr_at(PERSEIDS, 140.0 + half_width), 10.0, places=4)

    def test_published_slope_wins_when_supplied(self):
        shower = dict(PERSEIDS, b=0.35)
        self.assertAlmostEqual(activity_slope(shower), 0.35)

    def test_zero_slope_is_honoured_not_treated_as_missing(self):
        """A published b of 0 is a real value; a falsy check would silently discard it."""
        self.assertAlmostEqual(activity_slope(dict(PERSEIDS, b=0.0)), 0.0)

    def test_catalog_majors_use_published_slopes(self):
        """The derived fallback is far too shallow for sharp showers, so majors must be sourced.

        Deriving the Quadrantid slope from its activity window gives about 0.145 against a
        published 2.2 — a fourteen-hour peak smeared across a fortnight, which made the
        "worth going outside" alert fire on 94 nights of the year instead of around 50.
        """
        for code in ("QUA", "PER", "GEM", "LEO", "URS", "ORI", "ETA", "LYR"):
            shower = _by_code(code)
            self.assertIsNotNone(shower["b"], f"{code} must carry a published activity slope")

    def test_derived_slope_is_floored(self):
        """An unsourced shower must never get a profile broader than the floor allows."""
        wide = dict(PERSEIDS, b=None, zhr=3,
                    sol_lon_max=100.0, sol_lon_start=40.0, sol_lon_end=160.0)
        self.assertGreaterEqual(activity_slope(wide), 0.15)

    def test_slope_is_steeper_for_narrow_showers(self):
        """The Draconids last hours; the Taurids last weeks."""
        self.assertGreater(activity_slope(_by_code("DRA")), activity_slope(_by_code("STA")))

    def test_profile_wraps_across_zero(self):
        """A shower peaking at 1 deg must treat 359 deg as 2 deg away, not 358."""
        shower = dict(PERSEIDS, sol_lon_max=1.0, sol_lon_start=350.0, sol_lon_end=12.0)
        self.assertAlmostEqual(zhr_at(shower, 359.0), zhr_at(shower, 3.0), places=9)

    def test_is_active_inside_and_outside_window(self):
        self.assertTrue(is_active(PERSEIDS, 140.0))
        self.assertTrue(is_active(PERSEIDS, 114.5))
        self.assertFalse(is_active(PERSEIDS, 200.0))

    def test_is_active_handles_wrapping_window(self):
        """The Quadrantid window straddles the 360/0 boundary."""
        quadrantids = _by_code("QUA")
        self.assertTrue(is_active(quadrantids, 283.15))
        self.assertFalse(is_active(quadrantids, 140.0))

    def test_gamma_normids_window_wraps_year_end(self):
        gnormids = _by_code("GNO")
        self.assertGreater(gnormids["sol_lon_start"], gnormids["sol_lon_end"])
        self.assertTrue(is_active(gnormids, 354.0))
        self.assertTrue(is_active(gnormids, 2.0))
        self.assertFalse(is_active(gnormids, 180.0))


class TestSkyBrightness(unittest.TestCase):
    """The moonlight model. Explicitly empirical, but it must hit its anchor points."""

    def test_moon_below_horizon_costs_nothing(self):
        self.assertEqual(moon_penalty(1.0, -0.1), 0.0)
        self.assertEqual(moon_penalty(1.0, -45.0), 0.0)

    def test_new_moon_costs_nothing(self):
        self.assertAlmostEqual(moon_penalty(0.0, 60.0), 0.0, places=6)

    def test_full_moon_overhead_costs_two_and_a_half_magnitudes(self):
        self.assertAlmostEqual(moon_penalty(1.0, 90.0), 2.5, places=6)

    def test_penalty_increases_with_illumination(self):
        values = [moon_penalty(fraction / 10.0, 45.0) for fraction in range(11)]
        self.assertEqual(values, sorted(values))

    def test_penalty_increases_with_altitude(self):
        values = [moon_penalty(1.0, altitude) for altitude in range(1, 90, 10)]
        self.assertEqual(values, sorted(values))

    def test_limiting_magnitude_ideal_under_dark_sky(self):
        self.assertAlmostEqual(
            limiting_magnitude(0.0, -30.0, DARKNESS_ASTRONOMICAL), IDEAL_LIMITING_MAGNITUDE,
        )

    def test_full_moon_overhead_gives_magnitude_four(self):
        self.assertAlmostEqual(limiting_magnitude(1.0, 90.0, DARKNESS_ASTRONOMICAL), 4.0, places=6)

    def test_twilight_costs_a_magnitude(self):
        self.assertEqual(twilight_penalty(DARKNESS_ASTRONOMICAL), 0.0)
        self.assertGreater(twilight_penalty(DARKNESS_NAUTICAL), 0.0)
        dark = limiting_magnitude(0.0, -30.0, DARKNESS_ASTRONOMICAL)
        twilit = limiting_magnitude(0.0, -30.0, DARKNESS_NAUTICAL)
        self.assertAlmostEqual(dark - twilit, 1.0, places=6)

    def test_limiting_magnitude_never_runs_away(self):
        self.assertGreaterEqual(limiting_magnitude(1.0, 90.0, DARKNESS_NAUTICAL), 1.0)


class TestRatesAndScoring(unittest.TestCase):
    """The observing relation and the conditions score derived from it."""

    def test_rate_zero_below_horizon(self):
        self.assertEqual(observed_rate(100.0, 0.0, 2.2, 6.5), 0.0)
        self.assertEqual(observed_rate(100.0, -20.0, 2.2, 6.5), 0.0)

    def test_rate_equals_zhr_at_zenith_under_ideal_sky(self):
        self.assertAlmostEqual(observed_rate(100.0, 90.0, 2.2, 6.5), 100.0, places=6)

    def test_rate_halves_at_thirty_degrees(self):
        """sin(30 deg) is 0.5, so a radiant a third of the way up halves the rate."""
        self.assertAlmostEqual(observed_rate(100.0, 30.0, 2.2, 6.5), 50.0, places=6)

    def test_moonlight_reduces_rate(self):
        bright = observed_rate(100.0, 60.0, 2.2, 4.0)
        dark = observed_rate(100.0, 60.0, 2.2, 6.5)
        self.assertLess(bright, dark)

    def test_score_is_one_hundred_under_perfect_geometry(self):
        self.assertEqual(viewing_score(90.0, 2.2, 6.5), 100)

    def test_score_is_zero_below_horizon(self):
        self.assertEqual(viewing_score(0.0, 2.2, 6.5), 0)
        self.assertEqual(viewing_score(-30.0, 2.2, 6.5), 0)

    def test_score_is_independent_of_shower_strength(self):
        """The whole point of the score: ZHR cancels, so it measures conditions only."""
        weak = dict(PERSEIDS, zhr=2)
        strong = dict(PERSEIDS, zhr=150)
        self.assertEqual(
            viewing_score(45.0, weak["r"], 6.0), viewing_score(45.0, strong["r"], 6.0),
        )

    def test_score_bounded_across_a_sweep(self):
        for altitude in range(-90, 91, 7):
            for population in (1.5, 2.2, 3.2, 4.5):
                for magnitude in (1.0, 3.0, 4.5, 6.5):
                    score = viewing_score(float(altitude), population, magnitude)
                    self.assertGreaterEqual(score, 0)
                    self.assertLessEqual(score, 100)

    def test_rating_bands(self):
        self.assertEqual(score_rating(100), "Excellent")
        self.assertEqual(score_rating(85), "Excellent")
        self.assertEqual(score_rating(78), "Very Good")
        self.assertEqual(score_rating(45), "Good")
        self.assertEqual(score_rating(25), "Fair")
        self.assertEqual(score_rating(0), "Poor")


class TestLimitingFactor(unittest.TestCase):
    """Which condition is costing the most meteors."""

    def test_low_radiant_under_dark_sky(self):
        self.assertEqual(
            limiting_factor(10.0, 2.2, 0.0, -30.0, DARKNESS_ASTRONOMICAL), FACTOR_RADIANT,
        )

    def test_full_moon_with_high_radiant(self):
        self.assertEqual(
            limiting_factor(80.0, 2.2, 1.0, 70.0, DARKNESS_ASTRONOMICAL), FACTOR_MOON,
        )

    def test_no_darkness_dominates_everything(self):
        self.assertEqual(
            limiting_factor(85.0, 2.2, 0.0, -40.0, DARKNESS_NONE), FACTOR_DARKNESS,
        )


class TestNearestPeak(unittest.TestCase):
    """A shower that peaked last night is still tonight's story."""

    def test_returns_recent_past_peak(self):
        just_after = datetime(2026, 8, 12, 20, 0, tzinfo=UTC)
        peak = nearest_peak(PERSEIDS, just_after)
        self.assertLess(abs((peak - just_after).total_seconds()), 86400)

    def test_returns_imminent_future_peak(self):
        just_before = datetime(2026, 8, 12, 6, 0, tzinfo=UTC)
        peak = nearest_peak(PERSEIDS, just_before)
        self.assertGreater(peak, just_before)
        self.assertLess((peak - just_before).total_seconds(), 86400)


class TestForecastAssembly(unittest.TestCase):
    """End-to-end forecasts. Ranges, not exact values, around physically verified results."""

    def _forecast(self, when, observer, **kwargs):
        return build_meteor_forecast(when, observer[0], observer[1], UTC, METEOR_SHOWERS, **kwargs)

    def test_payload_has_expected_keys(self):
        forecast = self._forecast(datetime(2026, 8, 12, 20, 0, tzinfo=UTC), ILM)
        for key in (
            "generated_utc", "solar_longitude", "night_of", "darkness", "dark_window_start",
            "dark_window_end", "dark_hours", "moon_illumination", "moon_altitude",
            "active", "best", "upcoming",
        ):
            self.assertIn(key, forecast)

    def test_perseids_score_well_in_a_dark_moon_year(self):
        """August 2026 has a new moon at the Perseid peak, so only radiant altitude limits it."""
        forecast = self._forecast(datetime(2026, 8, 12, 20, 0, tzinfo=UTC), ILM)
        best = forecast["best"]
        self.assertEqual(best["code"], "PER")
        self.assertGreaterEqual(best["viewing_score"], 75)
        self.assertGreater(best["expected_per_hour"], 50)
        self.assertLess(best["moon_illumination"], 10)
        self.assertEqual(best["limiting_factor"], FACTOR_RADIANT)
        self.assertTrue(best["is_peak_night"])

    def test_geminids_reach_near_perfect_geometry(self):
        """The Geminid radiant passes almost exactly overhead from mid-northern latitudes."""
        forecast = self._forecast(datetime(2026, 12, 14, 2, 0, tzinfo=UTC), ILM)
        best = forecast["best"]
        self.assertEqual(best["code"], "GEM")
        self.assertGreater(best["radiant_altitude"], 75)
        self.assertGreaterEqual(best["viewing_score"], 90)

    def test_quadrantids_ruined_by_a_full_moon(self):
        """January 2026 puts a full moon right on the Quadrantid peak."""
        forecast = self._forecast(datetime(2026, 1, 3, 6, 0, tzinfo=UTC), ILM)
        best = forecast["best"]
        self.assertEqual(best["code"], "QUA")
        self.assertGreater(best["moon_illumination"], 90)
        self.assertEqual(best["limiting_factor"], FACTOR_MOON)
        self.assertLess(best["viewing_score"], 50)

    def test_best_window_lies_inside_the_dark_window(self):
        forecast = self._forecast(datetime(2026, 8, 12, 20, 0, tzinfo=UTC), ILM)
        best = forecast["best"]
        self.assertIsNotNone(best["best_window_start"])
        self.assertGreaterEqual(best["best_window_start"], forecast["dark_window_start"])
        self.assertLessEqual(best["best_window_end"], forecast["dark_window_end"])

    def test_active_list_sorted_by_expected_rate(self):
        forecast = self._forecast(datetime(2026, 8, 12, 20, 0, tzinfo=UTC), ILM)
        rates = [shower["expected_per_hour"] for shower in forecast["active"]]
        self.assertEqual(rates, sorted(rates, reverse=True))

    def test_upcoming_is_ordered_and_in_the_future(self):
        now = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
        forecast = self._forecast(now, ILM, upcoming_count=5)
        upcoming = forecast["upcoming"]
        self.assertEqual(len(upcoming), 5)
        self.assertEqual(
            [item["days_until"] for item in upcoming],
            sorted(item["days_until"] for item in upcoming),
        )
        for item in upcoming:
            self.assertGreater(item["days_until"], 0)

    def test_southern_hemisphere_observer(self):
        """Eta Aquariids are a pre-dawn shower and are best seen from the south."""
        forecast = self._forecast(datetime(2026, 5, 6, 16, 0, tzinfo=UTC), SYDNEY)
        codes = [shower["code"] for shower in forecast["active"]]
        self.assertIn("ETA", codes)
        eta = next(s for s in forecast["active"] if s["code"] == "ETA")
        self.assertGreater(eta["radiant_altitude"], 0)

    def test_best_is_never_a_shower_below_the_horizon(self):
        """The headline sensor must not name a shower whose radiant never clears the horizon.

        Seen from Sydney in early January the Quadrantid radiant sits about 74 degrees *below*
        the horizon all night, yet it was being reported as the shower worth watching on roughly
        a quarter of the year's nights.
        """
        for observer in (ILM, SYDNEY, TROMSO):
            for day in range(0, 365, 5):
                when = datetime(2026, 1, 1, 12, 0, tzinfo=UTC) + timedelta(days=day)
                best = self._forecast(when, observer)["best"]
                if best is not None:
                    self.assertGreater(
                        best["radiant_altitude"], 0.0,
                        f"{observer} on day {day}: best is {best['name']} at "
                        f"{best['radiant_altitude']} deg",
                    )

    def test_forecast_rolls_forward_once_the_night_is_over(self):
        """After dawn the forecast must move to the next night, not keep a closed window.

        Otherwise the alert spends every morning advertising a best-viewing window that ended
        hours earlier, in daylight.
        """
        tz = timezone(timedelta(hours=-4))
        for hour in (7, 9, 11):
            now = datetime(2026, 8, 14, hour, 0, tzinfo=tz)
            forecast = build_meteor_forecast(now, ILM[0], ILM[1], tz, METEOR_SHOWERS)
            end = forecast["dark_window_end"]
            self.assertIsNotNone(end)
            self.assertGreater(
                datetime.fromisoformat(end), now,
                f"at {hour}:00 the reported dark window had already closed",
            )

    def test_radiant_that_never_rises(self):
        """The Quadrantid radiant at declination +49 stays below the horizon from Sydney."""
        forecast = self._forecast(datetime(2026, 1, 3, 6, 0, tzinfo=UTC), SYDNEY)
        quadrantids = next(s for s in forecast["active"] if s["code"] == "QUA")
        self.assertEqual(quadrantids["viewing_score"], 0)
        self.assertEqual(quadrantids["expected_per_hour"], 0)
        self.assertLess(quadrantids["max_radiant_altitude"], 10)

    def test_high_latitude_summer_has_no_darkness(self):
        """Tromso in late June never gets dark; the forecast must say so rather than crash."""
        forecast = self._forecast(datetime(2026, 6, 27, 22, 0, tzinfo=UTC), TROMSO)
        self.assertEqual(forecast["darkness"], DARKNESS_NONE)
        self.assertIsNone(forecast["dark_window_start"])
        self.assertEqual(forecast["dark_hours"], 0.0)
        if forecast["best"]:
            self.assertEqual(forecast["best"]["viewing_score"], 0)
            self.assertEqual(forecast["best"]["limiting_factor"], FACTOR_DARKNESS)

    def test_no_active_shower_still_reports_upcoming(self):
        """Quiet stretches must still answer 'what's coming up' — that is half the feature."""
        forecast = build_meteor_forecast(
            datetime(2026, 3, 5, 6, 0, tzinfo=UTC), ILM[0], ILM[1], UTC,
            [PERSEIDS],  # a catalog with nothing active in March
        )
        self.assertEqual(forecast["active"], [])
        self.assertIsNone(forecast["best"])
        self.assertEqual(len(forecast["upcoming"]), 1)
        self.assertGreater(forecast["upcoming"][0]["days_until"], 0)

    def test_runs_without_error_across_a_whole_year(self):
        """Sweep every week of the year at three latitudes; nothing may raise."""
        for observer in (ILM, SYDNEY, TROMSO):
            for day in range(0, 365, 7):
                when = datetime(2026, 1, 1, 21, 0, tzinfo=UTC) + timedelta(days=day)
                forecast = self._forecast(when, observer)
                self.assertIn(forecast["darkness"], (
                    DARKNESS_ASTRONOMICAL, DARKNESS_NAUTICAL, DARKNESS_NONE,
                ))
                if forecast["best"]:
                    self.assertGreaterEqual(forecast["best"]["viewing_score"], 0)
                    self.assertLessEqual(forecast["best"]["viewing_score"], 100)


class TestNoHomeAssistantDependency(unittest.TestCase):
    """meteor.py must stay loadable with Home Assistant entirely absent."""

    def test_no_home_assistant_imports(self):
        import meteor
        source = open(meteor.__file__).read()
        for forbidden in ("homeassistant", "aiohttp", "voluptuous"):
            self.assertNotIn(forbidden, source)

    def test_catalog_is_injected_not_imported(self):
        """The catalog arrives as a parameter, mirroring how parsers.py receives its tables."""
        import meteor
        source = open(meteor.__file__).read()
        self.assertNotIn("from meteor_catalog import", source)
        self.assertNotIn("from .meteor_catalog import", source)


if __name__ == "__main__":
    unittest.main()
