"""Tests for the meteor shower sensor and binary sensor entities.

Follows the repository's established pattern for entity tests: Home Assistant is replaced with
MagicMocks at import time, coordinators are stubbed with a fixture payload, and the entity classes
are imported inside the test methods once the patch is active.
"""

import json
import os
import sys
import unittest
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
    return _load_fixture("meteor_forecast.json")


def _quiet_forecast():
    """A forecast with no active shower — roughly a third of the year looks like this."""
    data = _forecast()
    data["active"] = []
    data["best"] = None
    return data


# ---------------------------------------------------------------------------
# Meteor Shower Activity
# ---------------------------------------------------------------------------

class TestMeteorShowerActivitySensor(unittest.TestCase):
    """The 'what is happening right now' sensor."""

    def _sensor(self, data):
        from noaa_it_all.sensors.meteor_showers import MeteorShowerActivitySensor
        return MeteorShowerActivitySensor(_make_coordinator(data), OFFICE)

    def test_state_is_best_shower_name(self):
        self.assertEqual(self._sensor(_forecast()).state, "Perseids")

    def test_state_when_nothing_active(self):
        self.assertEqual(self._sensor(_quiet_forecast()).state, "None")

    def test_state_before_first_refresh(self):
        self.assertEqual(self._sensor(None).state, "None")

    def test_name_and_unique_id(self):
        sensor = self._sensor(_forecast())
        self.assertEqual(sensor.name, "Meteor Shower Activity")
        self.assertEqual(sensor.unique_id, f"noaa_{OFFICE}_meteor_shower_activity")

    def test_icon(self):
        self.assertEqual(self._sensor(_forecast()).icon, "mdi:meteor")

    def test_attributes(self):
        attrs = self._sensor(_forecast()).extra_state_attributes
        self.assertEqual(attrs["office_code"], OFFICE)
        self.assertEqual(attrs["shower_code"], "PER")
        self.assertGreater(attrs["active_count"], 0)
        self.assertEqual(attrs["parent_body"], "109P/Swift-Tuttle")
        self.assertEqual(attrs["constellation"], "Perseus")
        self.assertTrue(attrs["is_peak_night"])
        self.assertIsInstance(attrs["active_showers"], list)

    def test_active_shower_entries_are_trimmed(self):
        """Per-shower entries stay small so recorder attributes never balloon."""
        attrs = self._sensor(_forecast()).extra_state_attributes
        for entry in attrs["active_showers"]:
            self.assertEqual(
                set(entry),
                {"code", "name", "zhr_now", "peak_local", "radiant_altitude",
                 "expected_per_hour"},
            )

    def test_attributes_when_nothing_active(self):
        attrs = self._sensor(_quiet_forecast()).extra_state_attributes
        self.assertEqual(attrs["active_count"], 0)
        self.assertEqual(attrs["active_showers"], [])
        self.assertNotIn("shower_code", attrs)

    def test_attributes_before_first_refresh(self):
        attrs = self._sensor(None).extra_state_attributes
        self.assertEqual(attrs["active_count"], 0)

    def test_device_is_the_space_group(self):
        info = self._sensor(_forecast()).device_info
        self.assertEqual(info["name"], f"NOAA {OFFICE} Space")


# ---------------------------------------------------------------------------
# Next Meteor Shower
# ---------------------------------------------------------------------------

class TestNextMeteorShowerSensor(unittest.TestCase):
    """The 'what is coming up' sensor that drives dashboard cards."""

    def _sensor(self, data):
        from noaa_it_all.sensors.meteor_showers import NextMeteorShowerSensor
        return NextMeteorShowerSensor(_make_coordinator(data), OFFICE)

    def test_state_is_next_shower_name(self):
        expected = _forecast()["upcoming"][0]["name"]
        self.assertEqual(self._sensor(_forecast()).state, expected)

    def test_state_before_first_refresh(self):
        self.assertIsNone(self._sensor(None).state)

    def test_name_and_unique_id(self):
        sensor = self._sensor(_forecast())
        self.assertEqual(sensor.name, "Next Meteor Shower")
        self.assertEqual(sensor.unique_id, f"noaa_{OFFICE}_next_meteor_shower")

    def test_icon(self):
        self.assertEqual(self._sensor(_forecast()).icon, "mdi:calendar-star")

    def test_attributes(self):
        attrs = self._sensor(_forecast()).extra_state_attributes
        for key in ("code", "peak_utc", "peak_local", "days_until", "zhr_max", "constellation"):
            self.assertIn(key, attrs)
        self.assertEqual(attrs["office_code"], OFFICE)

    def test_upcoming_list_populated_and_ordered(self):
        attrs = self._sensor(_forecast()).extra_state_attributes
        upcoming = attrs["upcoming"]
        self.assertGreater(len(upcoming), 0)
        days = [item["days_until"] for item in upcoming]
        self.assertEqual(days, sorted(days))

    def test_upcoming_survives_an_empty_payload(self):
        self.assertEqual(self._sensor(None).extra_state_attributes["upcoming"], [])


# ---------------------------------------------------------------------------
# Meteor Viewing Score
# ---------------------------------------------------------------------------

class TestMeteorViewingScoreSensor(unittest.TestCase):
    """The sky-conditions score."""

    def _sensor(self, data):
        from noaa_it_all.sensors.meteor_showers import MeteorViewingScoreSensor
        return MeteorViewingScoreSensor(_make_coordinator(data), OFFICE)

    def test_state_is_the_score(self):
        self.assertEqual(self._sensor(_forecast()).state, 85)

    def test_state_is_zero_when_nothing_active(self):
        self.assertEqual(self._sensor(_quiet_forecast()).state, 0)

    def test_state_before_first_refresh(self):
        self.assertEqual(self._sensor(None).state, 0)

    def test_name_unit_and_unique_id(self):
        sensor = self._sensor(_forecast())
        self.assertEqual(sensor.name, "Meteor Viewing Score")
        self.assertEqual(sensor.unit_of_measurement, "%")
        self.assertEqual(sensor.unique_id, f"noaa_{OFFICE}_meteor_viewing_score")

    def test_icon(self):
        self.assertEqual(self._sensor(_forecast()).icon, "mdi:star-shooting")

    def test_attributes_match_the_documented_shape(self):
        attrs = self._sensor(_forecast()).extra_state_attributes
        for key in (
            "rating", "best_window_start", "best_window_end", "radiant_alt_at_best",
            "moon_illumination", "moon_altitude", "darkness", "limiting_magnitude",
            "expected_per_hour", "limiting_factor", "shower", "shower_code",
        ):
            self.assertIn(key, attrs)

    def test_no_weather_attributes_present(self):
        """This is a pure-astronomy feature; nothing weather-derived belongs here."""
        attrs = self._sensor(_forecast()).extra_state_attributes
        for forbidden in ("sky_cover_pct", "cloud_cover", "precipitation", "sky_cover"):
            self.assertNotIn(forbidden, attrs)

    def test_attributes_when_nothing_active(self):
        attrs = self._sensor(_quiet_forecast()).extra_state_attributes
        self.assertIsNone(attrs["shower"])
        self.assertEqual(attrs["expected_per_hour"], 0)
        self.assertEqual(attrs["limiting_factor"], "no active shower")
        self.assertEqual(attrs["rating"], "Poor")

    def test_moon_illumination_is_an_integer_percentage(self):
        attrs = self._sensor(_forecast()).extra_state_attributes
        self.assertIsInstance(attrs["moon_illumination"], int)
        self.assertGreaterEqual(attrs["moon_illumination"], 0)
        self.assertLessEqual(attrs["moon_illumination"], 100)

    def test_device_is_the_space_group(self):
        info = self._sensor(_forecast()).device_info
        self.assertEqual(info["name"], f"NOAA {OFFICE} Space")


# ---------------------------------------------------------------------------
# Meteor Shower Active binary sensor
# ---------------------------------------------------------------------------

class TestMeteorShowerActiveBinarySensor(unittest.TestCase):
    """The automation trigger."""

    def _sensor(self, data):
        from noaa_it_all.binary_sensor import MeteorShowerActiveBinarySensor
        return MeteorShowerActiveBinarySensor(_make_coordinator(data), OFFICE)

    def test_on_for_a_strong_well_placed_shower(self):
        self.assertTrue(self._sensor(_forecast()).is_on)

    def test_off_when_nothing_active(self):
        self.assertFalse(self._sensor(_quiet_forecast()).is_on)

    def test_off_before_first_refresh(self):
        self.assertFalse(self._sensor(None).is_on)

    def test_off_when_rate_is_too_low(self):
        """A two-per-hour minor shower must not trip an overnight notification."""
        data = _forecast()
        data["best"] = dict(data["best"], expected_per_hour=2)
        self.assertFalse(self._sensor(data).is_on)

    def test_off_when_moonlight_ruins_the_sky(self):
        """A strong shower washed out by a full moon should not wake anyone up."""
        data = _forecast()
        data["best"] = dict(data["best"], viewing_score=10, limiting_factor="moonlight")
        self.assertFalse(self._sensor(data).is_on)

    def test_name_and_unique_id(self):
        sensor = self._sensor(_forecast())
        self.assertEqual(sensor.name, "Meteor Shower Active")
        self.assertEqual(sensor._attr_unique_id, f"noaa_{OFFICE}_meteor_shower_active")

    def test_uses_has_entity_name(self):
        """Deliberately unlike the other binary sensors, so the entity ID carries 'space'."""
        self.assertTrue(self._sensor(_forecast())._attr_has_entity_name)

    def test_icon_reflects_state(self):
        self.assertEqual(self._sensor(_forecast()).icon, "mdi:meteor")
        self.assertEqual(self._sensor(_quiet_forecast()).icon, "mdi:weather-night")

    def test_attributes(self):
        attrs = self._sensor(_forecast()).extra_state_attributes
        for key in (
            "shower", "shower_code", "zhr_now", "expected_per_hour", "viewing_score",
            "rating", "peak_local", "is_peak_night", "best_window_start", "best_window_end",
            "limiting_factor",
        ):
            self.assertIn(key, attrs)

    def test_thresholds_exposed_for_debugging(self):
        attrs = self._sensor(_quiet_forecast()).extra_state_attributes
        self.assertIn("minimum_rate", attrs)
        self.assertIn("minimum_score", attrs)

    def test_device_is_the_space_group(self):
        """The first binary sensor on the Space device; the others are Weather and Surf."""
        info = self._sensor(_forecast()).device_info
        self.assertEqual(info["name"], f"NOAA {OFFICE} Space")


if __name__ == "__main__":
    unittest.main()
