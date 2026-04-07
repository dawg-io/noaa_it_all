"""Tests for binary_sensor.py entity logic using mocked HA modules."""

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
_ha_binary = MagicMock()

_ha_coordinator.CoordinatorEntity = type("CoordinatorEntity", (), {
    "__init__": lambda self, coordinator: setattr(self, "coordinator", coordinator),
})
_ha_coordinator.DataUpdateCoordinator = type("DataUpdateCoordinator", (), {})
_ha_entity.DeviceInfo = dict
_ha_binary.BinarySensorEntity = type("BinarySensorEntity", (), {})

_MOCK_MODULES = {
    "homeassistant": MagicMock(),
    "homeassistant.helpers": MagicMock(),
    "homeassistant.helpers.entity": _ha_entity,
    "homeassistant.helpers.update_coordinator": _ha_coordinator,
    "homeassistant.helpers.entity_platform": MagicMock(),
    "homeassistant.helpers.aiohttp_client": MagicMock(),
    "homeassistant.components": MagicMock(),
    "homeassistant.components.binary_sensor": _ha_binary,
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


OFFICE = "SGX"
LAT = 32.7157
LON = -117.1611


def _load_fixture(name):
    with open(os.path.join(_FIXTURES, name)) as f:
        return json.load(f)


def _make_coordinator(data=None):
    coord = MagicMock()
    coord.data = data
    return coord


class TestUnsafeToSwimBinarySensor(unittest.TestCase):
    """Tests for the UnsafeToSwimBinarySensor."""

    def _make(self, forecast_text=""):
        from noaa_it_all.binary_sensor import UnsafeToSwimBinarySensor
        coord = _make_coordinator({"forecast_text": forecast_text, "source_url": ""})
        return UnsafeToSwimBinarySensor(coord, OFFICE)

    def test_high_risk_is_on(self):
        sensor = self._make("high rip current risk expected today")
        self.assertTrue(sensor.is_on)

    def test_moderate_risk_is_off(self):
        sensor = self._make("moderate rip current risk expected")
        self.assertFalse(sensor.is_on)

    def test_low_risk_is_off(self):
        sensor = self._make("low rip current risk")
        self.assertFalse(sensor.is_on)

    def test_no_data_is_off(self):
        from noaa_it_all.binary_sensor import UnsafeToSwimBinarySensor
        coord = _make_coordinator(None)
        sensor = UnsafeToSwimBinarySensor(coord, OFFICE)
        self.assertFalse(sensor.is_on)

    def test_icon_when_on(self):
        sensor = self._make("high rip current risk")
        self.assertEqual(sensor.icon, "mdi:swim-off")

    def test_icon_when_off(self):
        sensor = self._make("low rip current risk")
        self.assertEqual(sensor.icon, "mdi:swim")

    def test_unique_id(self):
        sensor = self._make()
        self.assertEqual(sensor._attr_unique_id, f"noaa_{OFFICE}_unsafe_to_swim")

    def test_attributes_high_risk(self):
        sensor = self._make("high rip current risk expected")
        attrs = sensor.extra_state_attributes
        self.assertEqual(attrs["risk_level"], "High")
        self.assertTrue(attrs["high_risk_detected"])

    def test_attributes_moderate_risk(self):
        sensor = self._make("moderate rip current risk")
        attrs = sensor.extra_state_attributes
        self.assertEqual(attrs["risk_level"], "Moderate")
        self.assertTrue(attrs["moderate_risk_detected"])


class TestSevereWeatherAlertBinarySensor(unittest.TestCase):
    """Tests for the SevereWeatherAlertBinarySensor."""

    def _make(self, features=None):
        from noaa_it_all.binary_sensor import SevereWeatherAlertBinarySensor
        data = {"features": features or []}
        coord = _make_coordinator(data)
        return SevereWeatherAlertBinarySensor(coord, OFFICE, LAT, LON)

    def test_no_alerts_is_off(self):
        sensor = self._make([])
        self.assertFalse(sensor.is_on)

    def test_tornado_warning_is_on(self):
        features = _load_fixture("nws_alerts.json")["features"]
        sensor = self._make(features)
        self.assertTrue(sensor.is_on)

    def test_test_alert_excluded(self):
        features = [_load_fixture("nws_alerts.json")["features"][2]]
        sensor = self._make(features)
        self.assertFalse(sensor.is_on)

    def test_icon_when_on(self):
        features = _load_fixture("nws_alerts.json")["features"][:1]
        sensor = self._make(features)
        self.assertEqual(sensor.icon, "mdi:weather-lightning")

    def test_icon_when_off(self):
        sensor = self._make([])
        self.assertEqual(sensor.icon, "mdi:weather-partly-cloudy")

    def test_unique_id(self):
        sensor = self._make()
        self.assertEqual(sensor._attr_unique_id, f"noaa_{OFFICE}_severe_weather_alert")


class TestFloodWinterAlertBinarySensor(unittest.TestCase):
    """Tests for the FloodWinterAlertBinarySensor."""

    def _make(self, features=None):
        from noaa_it_all.binary_sensor import FloodWinterAlertBinarySensor
        data = {"features": features or []}
        coord = _make_coordinator(data)
        return FloodWinterAlertBinarySensor(coord, OFFICE, LAT, LON)

    def test_no_alerts_is_off(self):
        sensor = self._make([])
        self.assertFalse(sensor.is_on)

    def test_flood_warning_is_on(self):
        features = _load_fixture("nws_alerts.json")["features"]
        sensor = self._make(features)
        self.assertTrue(sensor.is_on)

    def test_unique_id(self):
        sensor = self._make()
        self.assertEqual(sensor._attr_unique_id, f"noaa_{OFFICE}_flood_winter_alert")


class TestActiveAlertsGeneralBinarySensor(unittest.TestCase):
    """Tests for the ActiveAlertsGeneralBinarySensor."""

    def _make(self, features=None):
        from noaa_it_all.binary_sensor import ActiveAlertsGeneralBinarySensor
        data = {"features": features or []}
        coord = _make_coordinator(data)
        return ActiveAlertsGeneralBinarySensor(coord, OFFICE, LAT, LON)

    def test_no_alerts_is_off(self):
        sensor = self._make([])
        self.assertFalse(sensor.is_on)

    def test_actual_alerts_is_on(self):
        features = _load_fixture("nws_alerts.json")["features"]
        sensor = self._make(features)
        self.assertTrue(sensor.is_on)

    def test_attributes_count(self):
        features = _load_fixture("nws_alerts.json")["features"]
        sensor = self._make(features)
        attrs = sensor.extra_state_attributes
        # 2 'Actual' alerts, 1 'Test' filtered out
        self.assertEqual(attrs["alert_count"], 2)

    def test_icon_when_on(self):
        features = _load_fixture("nws_alerts.json")["features"]
        sensor = self._make(features)
        self.assertEqual(sensor.icon, "mdi:alert")

    def test_icon_when_off(self):
        sensor = self._make([])
        self.assertEqual(sensor.icon, "mdi:check-circle")


if __name__ == "__main__":
    unittest.main()
