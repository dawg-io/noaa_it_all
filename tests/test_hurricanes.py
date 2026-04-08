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
        self.assertEqual(sensor.name, "NOAA Weather - Hurricane Alerts")

    def test_unique_id(self):
        sensor = self._make()
        self.assertEqual(sensor.unique_id, f"noaa_{OFFICE}_hurricane_alerts")

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

    def test_device_info_weather_group(self):
        sensor = self._make()
        info = sensor.device_info
        ids = list(info["identifiers"])[0]
        self.assertIn("weather", ids[1])


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
        self.assertEqual(sensor.name, "NOAA Weather - Hurricane Activity")

    def test_unique_id(self):
        sensor = self._make()
        self.assertEqual(sensor.unique_id, f"noaa_{OFFICE}_hurricane_activity")

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

    def test_device_info_weather_group(self):
        sensor = self._make()
        info = sensor.device_info
        ids = list(info["identifiers"])[0]
        self.assertIn("weather", ids[1])


if __name__ == "__main__":
    unittest.main()
