"""Tests for forecast, alerts, and extra weather sensor entities.

Covers: ExtendedForecastSensor, HourlyForecastSensor, NWSAlertsSensor,
CloudCoverSensor, RadarTimestampSensor, ForecastDiscussionSensor.
"""

import json
import os
import sys
import unittest
from datetime import datetime, timezone
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
LAT = 34.2257
LON = -77.9447


def _load_fixture(name):
    with open(os.path.join(_FIXTURES, name)) as f:
        return json.load(f)


def _make_coordinator(data=None):
    coord = MagicMock()
    coord.data = data
    return coord


# ---------------------------------------------------------------
# Extended Forecast sensor
# ---------------------------------------------------------------
class TestExtendedForecastSensor(unittest.TestCase):
    """Tests for ExtendedForecastSensor."""

    def _make(self, forecast_data=None):
        from noaa_it_all.sensors.forecasts import ExtendedForecastSensor
        coord = _make_coordinator(forecast_data)
        return ExtendedForecastSensor(coord, OFFICE, LAT, LON)

    def test_name(self):
        sensor = self._make()
        self.assertEqual(sensor.name, f"NOAA {OFFICE} Extended Forecast")

    def test_unique_id_contains_office(self):
        sensor = self._make()
        self.assertIn(OFFICE.lower(), sensor.unique_id.lower())

    def test_unique_id_contains_coords(self):
        sensor = self._make()
        uid = sensor.unique_id
        self.assertIn("34_2257", uid)
        self.assertIn("n77_9447", uid)

    def test_state_with_data(self):
        data = _load_fixture("forecast.json")
        sensor = self._make(data)
        state = sensor.state
        self.assertIn("periods", state)

    def test_state_no_data(self):
        sensor = self._make(None)
        self.assertIsNone(sensor.state)

    def test_icon(self):
        sensor = self._make()
        self.assertEqual(sensor.icon, "mdi:weather-partly-cloudy")

    def test_extra_attrs_with_data(self):
        data = _load_fixture("forecast.json")
        sensor = self._make(data)
        attrs = sensor.extra_state_attributes
        self.assertIn("periods", attrs)
        self.assertIn("office_code", attrs)

    def test_device_info_weather_group(self):
        sensor = self._make()
        info = sensor.device_info
        ids = list(info["identifiers"])[0]
        self.assertIn("weather", ids[1])


# ---------------------------------------------------------------
# Hourly Forecast sensor
# ---------------------------------------------------------------
class TestHourlyForecastSensor(unittest.TestCase):
    """Tests for HourlyForecastSensor."""

    def _make(self, forecast_data=None):
        from noaa_it_all.sensors.forecasts import HourlyForecastSensor
        coord = _make_coordinator(forecast_data)
        return HourlyForecastSensor(coord, OFFICE, LAT, LON)

    def test_name(self):
        sensor = self._make()
        self.assertEqual(sensor.name, f"NOAA {OFFICE} Hourly Forecast")

    def test_unique_id_contains_coords(self):
        sensor = self._make()
        uid = sensor.unique_id
        self.assertIn("34_2257", uid)
        self.assertIn("n77_9447", uid)

    def test_state_with_data(self):
        data = _load_fixture("forecast.json")
        sensor = self._make(data)
        state = sensor.state
        # First hourly period temperature
        self.assertEqual(state, 73)

    def test_state_no_data(self):
        sensor = self._make(None)
        self.assertIsNone(sensor.state)

    def test_icon(self):
        sensor = self._make()
        self.assertEqual(sensor.icon, "mdi:clock-outline")

    def test_extra_attrs_with_data(self):
        data = _load_fixture("forecast.json")
        sensor = self._make(data)
        attrs = sensor.extra_state_attributes
        self.assertIn("current_hour", attrs)
        self.assertIn("hourly_periods", attrs)


# ---------------------------------------------------------------
# NWS Alerts sensor
# ---------------------------------------------------------------
class TestNWSAlertsSensor(unittest.TestCase):
    """Tests for NWSAlertsSensor."""

    def _make(self, alerts_data=None):
        from noaa_it_all.sensors.alerts import NWSAlertsSensor
        coord = _make_coordinator(alerts_data)
        return NWSAlertsSensor(coord, OFFICE, LAT, LON)

    def test_name(self):
        sensor = self._make()
        self.assertEqual(sensor.name, f"NOAA {OFFICE} Active NWS Alerts")

    def test_unique_id_contains_office(self):
        sensor = self._make()
        self.assertIn(OFFICE.lower(), sensor.unique_id.lower())

    def test_unique_id_contains_coords(self):
        sensor = self._make()
        uid = sensor.unique_id
        self.assertIn("34_2257", uid)
        self.assertIn("n77_9447", uid)

    def test_state_with_alerts(self):
        alerts = _load_fixture("nws_alerts.json")
        sensor = self._make(alerts)
        state = sensor.state
        self.assertIsNotNone(state)
        self.assertIsInstance(state, int)

    def test_state_no_data(self):
        sensor = self._make(None)
        self.assertIsNone(sensor.state)

    def test_state_empty_features(self):
        sensor = self._make({"features": []})
        self.assertEqual(sensor.state, 0)

    def test_icon_with_alerts(self):
        alerts = _load_fixture("nws_alerts.json")
        sensor = self._make(alerts)
        if sensor.state and sensor.state > 0:
            self.assertEqual(sensor.icon, "mdi:alert-circle")

    def test_icon_no_alerts(self):
        sensor = self._make({"features": []})
        self.assertEqual(sensor.icon, "mdi:check-circle-outline")

    def test_extra_attrs_with_alerts(self):
        alerts = _load_fixture("nws_alerts.json")
        sensor = self._make(alerts)
        attrs = sensor.extra_state_attributes
        self.assertIn("alert_count", attrs)
        self.assertIn("office_code", attrs)
        self.assertIn("latitude", attrs)
        self.assertIn("longitude", attrs)

    def test_device_info_weather_group(self):
        sensor = self._make()
        info = sensor.device_info
        ids = list(info["identifiers"])[0]
        self.assertIn("weather", ids[1])


# ---------------------------------------------------------------
# Cloud Cover sensor
# ---------------------------------------------------------------
class TestCloudCoverSensor(unittest.TestCase):
    """Tests for CloudCoverSensor."""

    def _make(self, data=None):
        from noaa_it_all.sensors.weather_extra import CloudCoverSensor
        coord = _make_coordinator(data)
        return CloudCoverSensor(coord, OFFICE, LAT, LON)

    def test_name(self):
        sensor = self._make()
        self.assertEqual(sensor.name, f"NOAA {OFFICE} Cloud Cover")

    def test_unique_id_contains_coords(self):
        sensor = self._make()
        uid = sensor.unique_id
        self.assertIn("34_2257", uid)
        self.assertIn("n77_9447", uid)

    def test_unit(self):
        sensor = self._make()
        self.assertEqual(sensor.unit_of_measurement, "%")

    def test_state_with_data(self):
        data = _load_fixture("cloud_cover.json")
        sensor = self._make(data)
        state = sensor.state
        self.assertEqual(state, 75)

    def test_state_no_data(self):
        sensor = self._make(None)
        self.assertIsNone(sensor.state)

    def test_icon(self):
        sensor = self._make()
        self.assertEqual(sensor.icon, "mdi:cloud-percent")

    def test_extra_attrs_with_data(self):
        data = _load_fixture("cloud_cover.json")
        sensor = self._make(data)
        attrs = sensor.extra_state_attributes
        self.assertIn("office_code", attrs)
        self.assertIn("availability", attrs)

    def test_device_info_weather_group(self):
        sensor = self._make()
        info = sensor.device_info
        ids = list(info["identifiers"])[0]
        self.assertIn("weather", ids[1])


# ---------------------------------------------------------------
# Radar Timestamp sensor
# ---------------------------------------------------------------
class TestRadarTimestampSensor(unittest.TestCase):
    """Tests for RadarTimestampSensor."""

    def _make(self, data=None):
        from noaa_it_all.sensors.weather_extra import RadarTimestampSensor
        coord = _make_coordinator(data)
        return RadarTimestampSensor(coord, OFFICE)

    def test_name(self):
        sensor = self._make()
        self.assertEqual(sensor.name, f"NOAA {OFFICE} Radar Timestamp")

    def test_unique_id(self):
        sensor = self._make()
        self.assertEqual(sensor.unique_id, f"noaa_{OFFICE}_radar_timestamp")

    def test_state_with_timestamp(self):
        ts = datetime(2025, 4, 7, 18, 0, 0, tzinfo=timezone.utc)
        sensor = self._make({"timestamp": ts, "radar_site": "KLTX", "radar_url": "https://example.com"})
        state = sensor.state
        self.assertIn("2025-04-07", state)
        self.assertIn("UTC", state)

    def test_state_no_data(self):
        sensor = self._make(None)
        self.assertIsNone(sensor.state)

    def test_icon(self):
        sensor = self._make()
        self.assertEqual(sensor.icon, "mdi:radar")

    def test_extra_attrs_with_data(self):
        ts = datetime(2025, 4, 7, 18, 0, 0, tzinfo=timezone.utc)
        sensor = self._make({"timestamp": ts, "radar_site": "KLTX", "radar_url": "https://example.com"})
        attrs = sensor.extra_state_attributes
        self.assertIn("radar_site", attrs)
        self.assertEqual(attrs["radar_site"], "KLTX")

    def test_device_info_weather_group(self):
        sensor = self._make()
        info = sensor.device_info
        ids = list(info["identifiers"])[0]
        self.assertIn("weather", ids[1])


# ---------------------------------------------------------------
# Forecast Discussion sensor
# ---------------------------------------------------------------
class TestForecastDiscussionSensor(unittest.TestCase):
    """Tests for ForecastDiscussionSensor."""

    def _make(self, data=None):
        from noaa_it_all.sensors.weather_extra import ForecastDiscussionSensor
        coord = _make_coordinator(data)
        return ForecastDiscussionSensor(coord, OFFICE)

    def test_name(self):
        sensor = self._make()
        self.assertEqual(sensor.name, f"NOAA {OFFICE} Forecast Discussion")

    def test_unique_id(self):
        sensor = self._make()
        self.assertEqual(sensor.unique_id, f"noaa_{OFFICE}_forecast_discussion")

    def test_state_available(self):
        sensor = self._make({"discussion_text": "Synopsis and near-term forecast..."})
        self.assertEqual(sensor.state, "Available")

    def test_state_no_text(self):
        sensor = self._make({"discussion_text": ""})
        self.assertIsNone(sensor.state)

    def test_state_no_data(self):
        sensor = self._make(None)
        self.assertIsNone(sensor.state)

    def test_icon(self):
        sensor = self._make()
        self.assertEqual(sensor.icon, "mdi:text-box-outline")

    def test_extra_attrs_with_text(self):
        sensor = self._make({"discussion_text": "Synopsis and near-term forecast discussion text."})
        attrs = sensor.extra_state_attributes
        self.assertIn("summary", attrs)
        self.assertIn("full_text", attrs)
        self.assertIn("text_length", attrs)

    def test_extra_attrs_no_text(self):
        sensor = self._make({"discussion_text": ""})
        attrs = sensor.extra_state_attributes
        self.assertIn("availability", attrs)

    def test_device_info_weather_group(self):
        sensor = self._make()
        info = sensor.device_info
        ids = list(info["identifiers"])[0]
        self.assertIn("weather", ids[1])


if __name__ == "__main__":
    unittest.main()
