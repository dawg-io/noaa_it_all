"""Tests for hurricane sensor entities.

Covers: HurricaneAlertsSensor, HurricaneActivitySensor.
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

_MOCK_MODULES = {
    "homeassistant": MagicMock(),
    "homeassistant.helpers": MagicMock(),
    "homeassistant.helpers.entity": _ha_entity,
    "homeassistant.helpers.update_coordinator": _ha_coordinator,
    "homeassistant.helpers.entity_platform": MagicMock(),
    "homeassistant.helpers.aiohttp_client": MagicMock(),
    "homeassistant.components": MagicMock(),
    "homeassistant.components.binary_sensor": MagicMock(),
    "homeassistant.components.weather": MagicMock(),
    "homeassistant.components.image": MagicMock(),
    "homeassistant.const": MagicMock(),
    "homeassistant.config_entries": MagicMock(),
    "homeassistant.core": MagicMock(),
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


# ---------------------------------------------------------------
# Hurricane Alerts sensor
# ---------------------------------------------------------------
class TestHurricaneAlertsSensor(unittest.TestCase):
    """Tests for HurricaneAlertsSensor."""

    def _make(self, data=None):
        from noaa_it_all.sensors.hurricanes import HurricaneAlertsSensor
        coord = _make_coordinator(data)
        return HurricaneAlertsSensor(coord, OFFICE)

    def test_name(self):
        sensor = self._make()
        self.assertEqual(sensor.name, "Alerts")

    def test_unique_id(self):
        sensor = self._make()
        self.assertEqual(sensor.unique_id, "noaa_hurricane_alerts")

    def test_state_with_alerts(self):
        data = _load_fixture("hurricane.json")
        sensor = self._make(data)
        state = sensor.state
        self.assertEqual(state, 1)

    def test_state_no_alerts(self):
        sensor = self._make({"alerts": {"features": []}, "storms": {}})
        self.assertEqual(sensor.state, 0)

    def test_state_no_data(self):
        sensor = self._make(None)
        self.assertIsNone(sensor.state)

    def test_extra_attrs_with_alerts(self):
        data = _load_fixture("hurricane.json")
        sensor = self._make(data)
        attrs = sensor.extra_state_attributes
        self.assertIn("alerts", attrs)
        self.assertIsInstance(attrs["alerts"], list)

    def test_failed_alerts_fetch_is_unknown_not_zero(self):
        """#33: the coordinator sets a failed feed to None; that is not 0 alerts."""
        sensor = self._make({"alerts": None, "storms": {"activeStorms": []}})
        self.assertIsNone(sensor.state)
        self.assertEqual(sensor.extra_state_attributes, {})

    def test_device_info_hurricane_group(self):
        sensor = self._make()
        info = sensor.device_info
        ids = list(info["identifiers"])[0]
        self.assertEqual(ids[1], "noaa_hurricane")
        self.assertEqual(info["name"], "NOAA Hurricane")


# ---------------------------------------------------------------
# Hurricane Activity sensor
# ---------------------------------------------------------------
class TestHurricaneActivitySensor(unittest.TestCase):
    """Tests for HurricaneActivitySensor."""

    def _make(self, data=None):
        from noaa_it_all.sensors.hurricanes import HurricaneActivitySensor
        coord = _make_coordinator(data)
        return HurricaneActivitySensor(coord, OFFICE)

    def test_name(self):
        sensor = self._make()
        self.assertEqual(sensor.name, "Activity")

    def test_unique_id(self):
        sensor = self._make()
        self.assertEqual(sensor.unique_id, "noaa_hurricane_activity")

    def test_state_no_data(self):
        sensor = self._make(None)
        self.assertIsNone(sensor.state)

    def test_state_with_activity(self):
        data = _load_fixture("hurricane.json")
        sensor = self._make(data)
        state = sensor.state
        # classify_hurricane_activity returns a string state
        self.assertIsNotNone(state)

    def test_extra_attrs_no_data(self):
        sensor = self._make(None)
        attrs = sensor.extra_state_attributes
        self.assertIsInstance(attrs, dict)

    def test_device_info_hurricane_group(self):
        sensor = self._make()
        info = sensor.device_info
        ids = list(info["identifiers"])[0]
        self.assertEqual(ids[1], "noaa_hurricane")
        self.assertEqual(info["name"], "NOAA Hurricane")


class TestHurricaneActivityWithAFeedMissing(unittest.TestCase):
    """#33: one failed feed must not read as quiet, or as a lower level."""

    _HURRICANE = {"classification": "HU", "name": "Test"}
    _TS_WATCH = {"properties": {"event": "Tropical Storm Watch"}}
    _HU_WARNING = {"properties": {"event": "Hurricane Warning"}}

    def _make(self, alerts, storms):
        from noaa_it_all.sensors.hurricanes import HurricaneActivitySensor
        data = {
            "alerts": None if alerts is None else {"features": alerts},
            "storms": None if storms is None else {"activeStorms": storms},
        }
        return HurricaneActivitySensor(_make_coordinator(data), OFFICE)

    def test_both_feeds_quiet_is_still_quiet(self):
        sensor = self._make(alerts=[], storms=[])
        self.assertEqual(sensor.state, "Quiet - No Active Storms or Alerts")

    def test_failed_alerts_with_no_storms_is_unknown_not_quiet(self):
        sensor = self._make(alerts=None, storms=[])
        self.assertIsNone(sensor.state)

    def test_failed_storms_below_high_is_unknown(self):
        """A watch alone reads Low, but an active hurricane may be unseen."""
        sensor = self._make(alerts=[self._TS_WATCH], storms=None)
        self.assertIsNone(sensor.state)

    def test_a_hurricane_is_high_even_with_alerts_missing(self):
        sensor = self._make(alerts=None, storms=[self._HURRICANE])
        self.assertEqual(sensor.state, "High - 1 Active Hurricane(s)")

    def test_a_hurricane_warning_is_high_even_with_storms_missing(self):
        sensor = self._make(alerts=[self._HU_WARNING], storms=None)
        self.assertEqual(sensor.state, "High - Hurricane Warnings Active")

    def test_failed_alerts_counts_are_unknown_not_zero(self):
        attrs = self._make(alerts=None, storms=[self._HURRICANE]).extra_state_attributes
        for key in ("hurricane_warnings", "hurricane_watches", "tropical_warnings",
                    "tropical_watches", "total_alerts"):
            self.assertIsNone(attrs[key], key)
        self.assertEqual(attrs["hurricanes"], 1)

    def test_failed_storms_counts_are_unknown_not_zero(self):
        attrs = self._make(alerts=[self._TS_WATCH], storms=None).extra_state_attributes
        for key in ("total_active_storms", "hurricanes", "tropical_storms",
                    "other_storms", "storm_details"):
            self.assertIsNone(attrs[key], key)
        self.assertEqual(attrs["tropical_watches"], 1)


if __name__ == "__main__":
    unittest.main()
