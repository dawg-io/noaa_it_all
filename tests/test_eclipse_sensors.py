"""Tests for the eclipse sensor, binary sensor and image entities.

Follows the repository's established pattern for entity tests: Home Assistant is replaced with
MagicMocks at import time, coordinators are stubbed with a fixture payload, and the entity classes
are imported inside the test methods once the patch is active.

Every entity is exercised in the three states the repository treats as mandatory -- a populated
payload, a quiet one, and ``None`` before the coordinator's first refresh -- because an eclipse
sensor spends almost all of its life in the second of those.
"""

import json
import os
import sys
import unittest
from datetime import datetime
from unittest.mock import MagicMock, patch

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CC = os.path.join(_REPO, "custom_components")
_FIXTURES = os.path.join(_REPO, "tests", "fixtures")

if _CC not in sys.path:
    sys.path.insert(0, _CC)

# ---------------------------------------------------------------------------
# Mock Home Assistant modules
# ---------------------------------------------------------------------------
_ha_entity = MagicMock()
_ha_coordinator = MagicMock()

_ha_coordinator.CoordinatorEntity = type("CoordinatorEntity", (), {
    "__init__": lambda self, coordinator: setattr(self, "coordinator", coordinator),
})
_ha_coordinator.DataUpdateCoordinator = type("DataUpdateCoordinator", (), {})
_ha_entity.DeviceInfo = dict

_ha_binary_sensor = MagicMock()
_ha_binary_sensor.BinarySensorEntity = type("BinarySensorEntity", (), {})

_MOCK_MODULES = {
    "homeassistant": MagicMock(),
    "homeassistant.helpers": MagicMock(),
    "homeassistant.helpers.entity": _ha_entity,
    "homeassistant.helpers.update_coordinator": _ha_coordinator,
    "homeassistant.helpers.entity_platform": MagicMock(),
    "homeassistant.helpers.aiohttp_client": MagicMock(),
    "homeassistant.components": MagicMock(),
    "homeassistant.components.binary_sensor": _ha_binary_sensor,
    "homeassistant.const": MagicMock(),
    "homeassistant.config_entries": MagicMock(),
    "homeassistant.core": MagicMock(),
    "homeassistant.util": MagicMock(),
    "homeassistant.util.dt": MagicMock(),
    "aiohttp": MagicMock(),
}

_patcher = None


def setUpModule():
    global _patcher
    _patcher = patch.dict(sys.modules, _MOCK_MODULES)
    _patcher.start()


def tearDownModule():
    if _patcher is not None:
        _patcher.stop()


OFFICE = "ILM"


def _load_fixture(name):
    with open(os.path.join(_FIXTURES, name)) as f:
        return json.load(f)


def _make_coordinator(data=None):
    coord = MagicMock()
    coord.data = data
    return coord


def _forecast():
    """A rich payload: two days before the 2026 totality, seen from northern Spain."""
    return _load_fixture("eclipse_forecast.json")


def _quiet_forecast():
    """Nothing visible from here for years, which is the ordinary state of affairs."""
    data = _forecast()
    data["current"] = None
    data["next"] = None
    data["next_solar"] = None
    data["next_lunar"] = None
    data["upcoming"] = []
    return data


def _in_progress_forecast():
    """Totality happening right now."""
    data = _forecast()
    eclipse = dict(data["next"])
    eclipse["in_progress"] = True
    eclipse["hours_until"] = 0.0
    eclipse["days_until"] = 0.0
    data["current"] = eclipse
    return data


def _imminent_forecast(minutes):
    """The next eclipse's *first contact* is *minutes* away and it is not yet under way."""
    data = _forecast()
    eclipse = dict(data["next"])
    eclipse["in_progress"] = False
    eclipse["hours_until_start"] = minutes / 60.0
    eclipse["hours_until"] = minutes / 60.0 + 1.5      # maximum is later still
    eclipse["days_until"] = minutes / 1440.0
    data["next"] = eclipse
    data["current"] = None
    return data


def _shallow_forecast(covered):
    """The next eclipse is visible but barely covers anything."""
    data = _forecast()
    eclipse = dict(data["next"])
    eclipse["disc_covered"] = covered
    eclipse["hours_until_start"] = 0.5
    eclipse["hours_until"] = 0.5
    eclipse["days_until"] = 0.5 / 24.0
    data["next"] = eclipse
    data["current"] = None
    return data


# ---------------------------------------------------------------------------
# Next Eclipse
# ---------------------------------------------------------------------------

class TestFixtureMatchesTheModel(unittest.TestCase):
    """The fixture has to keep the shape the model actually produces.

    Entity tests read a checked-in payload, which is what keeps them fast and independent of the
    astronomy -- but it also means the payload can quietly drift out of step with the model until
    the sensors are reading keys that no longer exist. This compares the shape, not the values, so
    it catches a renamed or dropped key without breaking every time the scoring is tuned.
    """

    def _live(self):
        import eclipse
        from eclipse_catalog import SOLAR_ECLIPSES
        from datetime import datetime, timezone
        return eclipse.build_eclipse_forecast(
            datetime(2026, 8, 10, 9, 0, tzinfo=timezone.utc),
            42.34, -3.70, timezone.utc, SOLAR_ECLIPSES,
        )

    def test_top_level_keys_match(self):
        self.assertEqual(set(_forecast()), set(self._live()))

    def test_entry_keys_match(self):
        self.assertEqual(set(_forecast()["next"]), set(self._live()["next"]))

    def test_trimmed_entry_keys_match(self):
        self.assertEqual(
            set(_forecast()["upcoming"][0]), set(self._live()["upcoming"][0]),
        )


class TestNextEclipseSensor(unittest.TestCase):
    """What is coming, named the way this observer will experience it."""

    def _sensor(self, data):
        from noaa_it_all.sensors.eclipses import NextEclipseSensor
        return NextEclipseSensor(_make_coordinator(data), OFFICE)

    def test_state_is_the_eclipse_name(self):
        self.assertEqual(self._sensor(_forecast()).state, "Total Solar Eclipse")

    def test_state_when_nothing_is_coming(self):
        self.assertEqual(self._sensor(_quiet_forecast()).state, "None")

    def test_state_before_first_refresh(self):
        self.assertEqual(self._sensor(None).state, "None")

    def test_an_eclipse_in_progress_outranks_the_next_one(self):
        self.assertTrue(self._sensor(_in_progress_forecast()).extra_state_attributes[
            "in_progress"
        ])

    def test_naming(self):
        sensor = self._sensor(_forecast())
        self.assertEqual(sensor.name, "Next Eclipse")
        self.assertEqual(sensor.unique_id, f"noaa_{OFFICE}_next_eclipse")

    def test_icon_distinguishes_solar_from_lunar(self):
        solar = self._sensor(_forecast()).icon
        data = _forecast()
        data["next"] = dict(data["next"], kind="lunar")
        self.assertNotEqual(solar, self._sensor(data).icon)

    def test_attributes_carry_the_local_and_global_type(self):
        attrs = self._sensor(_forecast()).extra_state_attributes
        self.assertEqual(attrs["eclipse_type"], "total")
        self.assertEqual(attrs["global_type"], "total")

    def test_attributes_carry_the_look_ahead_list(self):
        attrs = self._sensor(_forecast()).extra_state_attributes
        self.assertTrue(attrs["upcoming"])

    def test_attributes_name_the_next_solar_eclipse_anywhere(self):
        attrs = self._sensor(_forecast()).extra_state_attributes
        self.assertIn("Solar", attrs["next_solar_anywhere"])

    def test_attributes_before_first_refresh(self):
        attrs = self._sensor(None).extra_state_attributes
        self.assertEqual(attrs["office_code"], OFFICE)
        self.assertEqual(attrs["upcoming"], [])

    def test_device_grouping(self):
        from noaa_it_all.const import DOMAIN
        self.assertEqual(self._sensor(_forecast()).device_info, {
            "identifiers": {(DOMAIN, f"noaa_{OFFICE}_space")},
            "name": f"NOAA {OFFICE} Space",
            "manufacturer": "NOAA",
        })


# ---------------------------------------------------------------------------
# Eclipse Coverage
# ---------------------------------------------------------------------------

class TestEclipseCoverageSensor(unittest.TestCase):
    """The "will I see 29% or all of it" number."""

    def _sensor(self, data):
        from noaa_it_all.sensors.eclipses import EclipseCoverageSensor
        return EclipseCoverageSensor(_make_coordinator(data), OFFICE)

    def test_state_is_the_percentage_covered(self):
        self.assertEqual(self._sensor(_forecast()).state, 100.0)

    def test_state_when_nothing_is_coming(self):
        self.assertEqual(self._sensor(_quiet_forecast()).state, 0)

    def test_state_before_first_refresh(self):
        self.assertEqual(self._sensor(None).state, 0)

    def test_a_partial_eclipse_reports_its_own_percentage(self):
        self.assertEqual(self._sensor(_shallow_forecast(29.0)).state, 29.0)

    def test_unit_is_a_percentage(self):
        self.assertEqual(self._sensor(_forecast()).unit_of_measurement, "%")

    def test_naming(self):
        sensor = self._sensor(_forecast())
        self.assertEqual(sensor.name, "Eclipse Coverage")
        self.assertEqual(sensor.unique_id, f"noaa_{OFFICE}_eclipse_coverage")

    def test_magnitude_is_reported_separately_from_coverage(self):
        # They are different quantities -- diameter against area -- and conflating them is the
        # obvious mistake for anybody comparing against a published table.
        attrs = self._sensor(_forecast()).extra_state_attributes
        self.assertIn("magnitude", attrs)
        self.assertNotEqual(attrs["magnitude"], self._sensor(_forecast()).state)

    def test_attributes_expose_the_geometric_peak_as_well(self):
        attrs = self._sensor(_forecast()).extra_state_attributes
        self.assertIn("peak_disc_covered", attrs)
        self.assertIn("visible_fraction", attrs)

    def test_attributes_when_nothing_is_coming(self):
        attrs = self._sensor(_quiet_forecast()).extra_state_attributes
        self.assertIsNone(attrs["eclipse"])
        self.assertFalse(attrs["visible"])

    def test_attributes_before_first_refresh(self):
        self.assertEqual(self._sensor(None).extra_state_attributes["office_code"], OFFICE)


# ---------------------------------------------------------------------------
# Eclipse Viewing Score
# ---------------------------------------------------------------------------

class TestEclipseViewingScoreSensor(unittest.TestCase):
    """How worthwhile it is, 0-100."""

    def _sensor(self, data):
        from noaa_it_all.sensors.eclipses import EclipseViewingScoreSensor
        return EclipseViewingScoreSensor(_make_coordinator(data), OFFICE)

    def test_state_is_the_score(self):
        self.assertEqual(self._sensor(_forecast()).state, 91)

    def test_state_when_nothing_is_coming(self):
        self.assertEqual(self._sensor(_quiet_forecast()).state, 0)

    def test_state_before_first_refresh(self):
        self.assertEqual(self._sensor(None).state, 0)

    def test_naming(self):
        sensor = self._sensor(_forecast())
        self.assertEqual(sensor.name, "Eclipse Viewing Score")
        self.assertEqual(sensor.unique_id, f"noaa_{OFFICE}_eclipse_viewing_score")

    def test_attributes_carry_the_rating_and_the_reason(self):
        attrs = self._sensor(_forecast()).extra_state_attributes
        self.assertEqual(attrs["rating"], "Excellent")
        self.assertIn("limiting_factor", attrs)

    def test_attributes_carry_the_eye_safety_notice(self):
        attrs = self._sensor(_forecast()).extra_state_attributes
        self.assertTrue(attrs["eye_protection_required"])
        self.assertIn("ISO 12312-2", attrs["eye_safety"])

    def test_attributes_carry_the_totality_window(self):
        attrs = self._sensor(_forecast()).extra_state_attributes
        self.assertIsNotNone(attrs["totality_starts_local"])
        self.assertGreater(attrs["totality_seconds"], 0)

    def test_attributes_when_nothing_is_coming(self):
        attrs = self._sensor(_quiet_forecast()).extra_state_attributes
        self.assertEqual(attrs["rating"], "Poor")
        self.assertIsNone(attrs["eclipse"])

    def test_attributes_before_first_refresh(self):
        self.assertEqual(self._sensor(None).extra_state_attributes["office_code"], OFFICE)


# ---------------------------------------------------------------------------
# Binary sensors
# ---------------------------------------------------------------------------

class TestEclipseVisibleNowBinarySensor(unittest.TestCase):
    """The go-outside-now flag."""

    def _sensor(self, data):
        from noaa_it_all.binary_sensor import EclipseVisibleNowBinarySensor
        return EclipseVisibleNowBinarySensor(_make_coordinator(data), OFFICE)

    def test_on_while_an_eclipse_is_under_way(self):
        self.assertTrue(self._sensor(_in_progress_forecast()).is_on)

    def test_on_inside_the_lead_window(self):
        from noaa_it_all.const import ECLIPSE_VISIBLE_LEAD_MINUTES
        self.assertTrue(self._sensor(_imminent_forecast(
            ECLIPSE_VISIBLE_LEAD_MINUTES - 5)).is_on)

    def test_off_outside_the_lead_window(self):
        from noaa_it_all.const import ECLIPSE_VISIBLE_LEAD_MINUTES
        self.assertFalse(self._sensor(_imminent_forecast(
            ECLIPSE_VISIBLE_LEAD_MINUTES + 30)).is_on)

    def test_the_lead_window_is_measured_from_first_contact(self):
        """Regression: measured from maximum, the lead window was unreachable.

        A lunar eclipse runs nearly three hours from first contact to greatest eclipse. Comparing
        the hour of lead time against the time to *maximum* meant that by the moment the branch
        could have matched, the eclipse had already started and was being reported as ``current``
        instead -- so the documented hour of warning was in practice none at all.
        """
        from noaa_it_all.const import ECLIPSE_VISIBLE_LEAD_MINUTES
        data = _imminent_forecast(ECLIPSE_VISIBLE_LEAD_MINUTES - 10)
        # Maximum is comfortably outside the window; first contact is inside it.
        self.assertGreater(data["next"]["hours_until"] * 60.0, ECLIPSE_VISIBLE_LEAD_MINUTES)
        self.assertLess(data["next"]["hours_until_start"] * 60.0, ECLIPSE_VISIBLE_LEAD_MINUTES)
        self.assertTrue(self._sensor(data).is_on)

    def test_minutes_until_counts_down_to_first_contact(self):
        from noaa_it_all.const import ECLIPSE_VISIBLE_LEAD_MINUTES
        attrs = self._sensor(_imminent_forecast(
            ECLIPSE_VISIBLE_LEAD_MINUTES - 10)).extra_state_attributes
        self.assertAlmostEqual(attrs["minutes_until"], ECLIPSE_VISIBLE_LEAD_MINUTES - 10, delta=1)

    def test_off_when_the_eclipse_barely_covers_anything(self):
        # A three percent nibble is invisible without a filter, and announcing it would only
        # teach people to ignore this sensor.
        from noaa_it_all.const import ECLIPSE_VISIBLE_MIN_COVERAGE
        self.assertFalse(self._sensor(
            _shallow_forecast(ECLIPSE_VISIBLE_MIN_COVERAGE - 1)).is_on)

    def test_on_once_the_threshold_is_met(self):
        from noaa_it_all.const import ECLIPSE_VISIBLE_MIN_COVERAGE
        self.assertTrue(self._sensor(
            _shallow_forecast(ECLIPSE_VISIBLE_MIN_COVERAGE + 1)).is_on)

    def test_on_even_when_the_body_sets_before_greatest_eclipse(self):
        """Regression: gating on the instant of maximum silenced the alert for a whole eclipse.

        When the Moon sets partway through a total lunar eclipse you can still watch most of it
        -- the 2026-03-03 eclipse from New York is nearly three hours of it -- but the body is
        below the horizon at greatest eclipse. Requiring it to be up *then* turned this sensor
        off for the entire event, which is the one case it exists for.
        """
        data = _in_progress_forecast()
        data["current"] = dict(data["current"], above_horizon_at_max=False)
        self.assertTrue(self._sensor(data).is_on)

    def test_off_when_the_eclipse_reaches_nothing_visible_here(self):
        data = _in_progress_forecast()
        data["current"] = dict(data["current"], visible=False)
        self.assertFalse(self._sensor(data).is_on)

    def test_off_when_the_eclipse_is_not_visible_from_here(self):
        data = _in_progress_forecast()
        data["current"] = dict(data["current"], visible=False)
        self.assertFalse(self._sensor(data).is_on)

    def test_off_when_nothing_is_coming(self):
        self.assertFalse(self._sensor(_quiet_forecast()).is_on)

    def test_off_before_first_refresh(self):
        self.assertFalse(self._sensor(None).is_on)

    def test_naming(self):
        sensor = self._sensor(_forecast())
        self.assertEqual(sensor.name, "Eclipse Visible Now")
        # Binary sensors set _attr_unique_id; the platform base class that turns it into a
        # ``unique_id`` property is mocked out here, as it is in test_binary_sensor.py.
        self.assertEqual(sensor._attr_unique_id, f"noaa_{OFFICE}_eclipse_visible_now")

    def test_icon_reflects_state(self):
        self.assertNotEqual(
            self._sensor(_in_progress_forecast()).icon,
            self._sensor(_quiet_forecast()).icon,
        )

    def test_attributes_point_at_where_the_eclipse_will_be_when_watchable(self):
        attrs = self._sensor(_in_progress_forecast()).extra_state_attributes
        self.assertIn("look_towards", attrs)
        self.assertIn("altitude_when_visible", attrs)

    def test_attributes_carry_the_eye_safety_warning(self):
        # The automation that fires from this entity is exactly the one that sends somebody
        # outside to look at the Sun, so the warning has to be reachable from here.
        attrs = self._sensor(_in_progress_forecast()).extra_state_attributes
        self.assertTrue(attrs["eye_protection_required"])
        self.assertIn("ISO 12312-2", attrs["eye_safety"])

    def test_attributes_carry_the_thresholds_back(self):
        from noaa_it_all.const import (
            ECLIPSE_VISIBLE_LEAD_MINUTES, ECLIPSE_VISIBLE_MIN_COVERAGE,
        )
        attrs = self._sensor(_quiet_forecast()).extra_state_attributes
        self.assertEqual(attrs["minimum_disc_covered"], ECLIPSE_VISIBLE_MIN_COVERAGE)
        self.assertEqual(attrs["lead_minutes"], ECLIPSE_VISIBLE_LEAD_MINUTES)

    def test_attributes_before_first_refresh(self):
        self.assertEqual(self._sensor(None).extra_state_attributes["office_code"], OFFICE)

    def test_device_grouping(self):
        from noaa_it_all.const import DOMAIN
        self.assertEqual(self._sensor(_forecast()).device_info, {
            "identifiers": {(DOMAIN, f"noaa_{OFFICE}_space")},
            "name": f"NOAA {OFFICE} Space",
            "manufacturer": "NOAA",
        })


class TestEclipseComingUpBinarySensor(unittest.TestCase):
    """The start-planning flag."""

    def _sensor(self, data):
        from noaa_it_all.binary_sensor import EclipseComingUpBinarySensor
        return EclipseComingUpBinarySensor(_make_coordinator(data), OFFICE)

    def test_on_inside_the_planning_window(self):
        self.assertTrue(self._sensor(_forecast()).is_on)

    def test_off_when_the_eclipse_is_still_far_away(self):
        from noaa_it_all.const import ECLIPSE_UPCOMING_DAYS
        data = _forecast()
        data["next"] = dict(data["next"], days_until=ECLIPSE_UPCOMING_DAYS + 10)
        self.assertFalse(self._sensor(data).is_on)

    def test_off_for_an_eclipse_not_worth_a_calendar_entry(self):
        from noaa_it_all.const import ECLIPSE_UPCOMING_MIN_COVERAGE
        data = _forecast()
        data["next"] = dict(data["next"],
                            disc_covered=ECLIPSE_UPCOMING_MIN_COVERAGE - 1, days_until=3)
        self.assertFalse(self._sensor(data).is_on)

    def test_its_bar_is_higher_than_the_live_alert(self):
        # A partial eclipse worth glancing at is not a partial eclipse worth booking a day off.
        from noaa_it_all.const import (
            ECLIPSE_UPCOMING_MIN_COVERAGE, ECLIPSE_VISIBLE_MIN_COVERAGE,
        )
        self.assertGreater(ECLIPSE_UPCOMING_MIN_COVERAGE, ECLIPSE_VISIBLE_MIN_COVERAGE)

    def test_off_when_nothing_is_coming(self):
        self.assertFalse(self._sensor(_quiet_forecast()).is_on)

    def test_off_before_first_refresh(self):
        self.assertFalse(self._sensor(None).is_on)

    def test_naming(self):
        sensor = self._sensor(_forecast())
        self.assertEqual(sensor.name, "Eclipse Coming Up")
        self.assertEqual(sensor._attr_unique_id, f"noaa_{OFFICE}_eclipse_coming_up")

    def test_attributes_carry_the_date(self):
        attrs = self._sensor(_forecast()).extra_state_attributes
        self.assertEqual(attrs["date"], "2026-08-12")
        self.assertAlmostEqual(attrs["days_until"], 2.4, delta=0.1)

    def test_attributes_before_first_refresh(self):
        self.assertEqual(self._sensor(None).extra_state_attributes["office_code"], OFFICE)


# ---------------------------------------------------------------------------
# Next Eclipse Time
# ---------------------------------------------------------------------------

class TestNextEclipseTimeSensor(unittest.TestCase):
    """The date to put on a dashboard, rather than an attribute to template out of one."""

    def _sensor(self, data):
        from noaa_it_all.sensors.eclipses import NextEclipseTimeSensor
        return NextEclipseTimeSensor(_make_coordinator(data), OFFICE)

    def test_state_is_when_the_eclipse_becomes_watchable(self):
        self.assertEqual(
            self._sensor(_forecast()).state, _forecast()["next"]["visible_start_utc"],
        )

    def test_state_is_a_parseable_timezone_aware_instant(self):
        """The assertion the whole design rests on.

        The state is published as a string rather than a datetime, so it being genuinely
        machine-readable ISO-8601 is what makes the timestamp device class mean anything -- to the
        frontend renderer, to a time trigger, and to any template doing date arithmetic.
        """
        parsed = datetime.fromisoformat(self._sensor(_forecast()).state)
        self.assertIsNotNone(parsed.tzinfo)
        self.assertIsNotNone(parsed.tzinfo.utcoffset(parsed))

    def test_it_declares_itself_a_timestamp(self):
        self.assertEqual(self._sensor(_forecast()).device_class, "timestamp")

    def test_state_is_none_when_nothing_is_due(self):
        # Not the string "None" and not 0, either of which a timestamp sensor would choke on.
        # Home Assistant renders None as "unknown", which is the honest answer.
        state = self._sensor(_quiet_forecast()).state
        self.assertIsNone(state)
        self.assertNotEqual(state, "None")

    def test_state_before_first_refresh(self):
        self.assertIsNone(self._sensor(None).state)

    def test_it_reports_the_eclipse_under_way_in_preference_to_the_next_one(self):
        sensor = self._sensor(_in_progress_forecast())
        self.assertTrue(sensor.extra_state_attributes["in_progress"])

    def test_naming(self):
        sensor = self._sensor(_forecast())
        self.assertEqual(sensor.name, "Next Eclipse Time")
        self.assertEqual(sensor.unique_id, f"noaa_{OFFICE}_next_eclipse_time")

    def test_attributes_carry_the_rest_of_the_window(self):
        attrs = self._sensor(_forecast()).extra_state_attributes
        self.assertEqual(attrs["date"], "2026-08-12")
        self.assertEqual(attrs["watch_until_utc"], _forecast()["next"]["visible_end_utc"])
        self.assertIn("look_towards", attrs)
        self.assertIn("totality_starts_local", attrs)

    def test_attributes_when_nothing_is_due(self):
        attrs = self._sensor(_quiet_forecast()).extra_state_attributes
        self.assertIsNone(attrs["eclipse"])
        self.assertIsNone(attrs["date"])

    def test_attributes_before_first_refresh(self):
        self.assertEqual(self._sensor(None).extra_state_attributes["office_code"], OFFICE)

    def test_device_grouping(self):
        from noaa_it_all.const import DOMAIN
        self.assertEqual(self._sensor(_forecast()).device_info, {
            "identifiers": {(DOMAIN, f"noaa_{OFFICE}_space")},
            "name": f"NOAA {OFFICE} Space",
            "manufacturer": "NOAA",
        })

    def test_the_watchable_moment_is_never_before_the_eclipse_begins(self):
        # It is the later of first contact and the body clearing the horizon, so it can equal
        # first contact but must never precede it.
        entry = _forecast()["next"]
        self.assertGreaterEqual(entry["visible_start_utc"], entry["start_utc"])


class TestTheAlertStopsWhenThereIsNothingToSee(unittest.TestCase):
    """Regression: the alert is keyed to the watchable window, not the geometric one.

    An eclipse continues between first and last contact whether or not the body is above your
    horizon. Keying "go outside now" to that meant New York spent nearly three hours of the
    2026-03-03 lunar eclipse being told to look at a Moon that had set.
    """

    def _sensor(self, data):
        from noaa_it_all.binary_sensor import EclipseVisibleNowBinarySensor
        return EclipseVisibleNowBinarySensor(_make_coordinator(data), OFFICE)

    def test_on_while_the_eclipse_is_watchable(self):
        self.assertTrue(self._sensor(_in_progress_forecast()).is_on)

    def test_off_once_the_body_has_set_even_though_the_eclipse_continues(self):
        # in_progress False is what the model now reports after the body sets; the eclipse entry
        # is still present and still "visible" in the sense that it *was* watchable.
        data = _forecast()
        data["current"] = None
        data["next"] = dict(data["next"], in_progress=False, hours_until_start=-2.0,
                            hours_until=-1.0)
        self.assertFalse(self._sensor(data).is_on)
