"""Tests for weather observation sensor entities.

Covers: Temperature, Humidity, Wind Speed, Wind Direction, Barometric Pressure,
Dewpoint, Visibility, Sky Conditions, Feels Like.
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
# Temperature sensor
# ---------------------------------------------------------------
class TestTemperatureSensor(unittest.TestCase):
    """Tests for TemperatureSensor."""

    def _make(self, obs_data=None):
        from noaa_it_all.sensors.weather_observations import TemperatureSensor
        coord = _make_coordinator(obs_data)
        return TemperatureSensor(coord, OFFICE, LAT, LON)

    def test_name(self):
        sensor = self._make()
        self.assertEqual(sensor.name, f"NOAA {OFFICE} Temperature")

    def test_unique_id_contains_office(self):
        sensor = self._make()
        self.assertIn(OFFICE, sensor.unique_id)

    def test_unique_id_contains_coords(self):
        sensor = self._make()
        uid = sensor.unique_id
        self.assertIn("34_2257", uid)
        self.assertIn("n77_9447", uid)

    def test_unit_of_measurement(self):
        sensor = self._make()
        self.assertEqual(sensor.unit_of_measurement, "°F")

    def test_state_converts_celsius_to_fahrenheit(self):
        obs = _load_fixture("observations.json")
        sensor = self._make(obs)
        state = sensor.state
        self.assertIsNotNone(state)
        # 22.2°C ≈ 72.0°F
        self.assertAlmostEqual(state, 72.0, delta=0.5)

    def test_state_no_data(self):
        sensor = self._make(None)
        self.assertIsNone(sensor.state)

    def test_icon(self):
        sensor = self._make()
        self.assertEqual(sensor.icon, "mdi:thermometer")

    def test_device_class(self):
        sensor = self._make()
        self.assertEqual(sensor.device_class, "temperature")

    def test_device_info_weather_group(self):
        sensor = self._make()
        info = sensor.device_info
        self.assertIn("identifiers", info)
        ids = list(info["identifiers"])[0]
        self.assertIn("weather", ids[1])


# ---------------------------------------------------------------
# Humidity sensor
# ---------------------------------------------------------------
class TestHumiditySensor(unittest.TestCase):
    """Tests for HumiditySensor."""

    def _make(self, obs_data=None):
        from noaa_it_all.sensors.weather_observations import HumiditySensor
        coord = _make_coordinator(obs_data)
        return HumiditySensor(coord, OFFICE, LAT, LON)

    def test_name(self):
        sensor = self._make()
        self.assertEqual(sensor.name, f"NOAA {OFFICE} Humidity")

    def test_unit(self):
        sensor = self._make()
        self.assertEqual(sensor.unit_of_measurement, "%")

    def test_state_rounds_to_int(self):
        obs = _load_fixture("observations.json")
        sensor = self._make(obs)
        state = sensor.state
        self.assertIsNotNone(state)
        # 63.5 → 64 (rounded)
        self.assertEqual(state, 64)

    def test_state_no_data(self):
        sensor = self._make(None)
        self.assertIsNone(sensor.state)

    def test_icon(self):
        sensor = self._make()
        self.assertEqual(sensor.icon, "mdi:water-percent")

    def test_device_class(self):
        sensor = self._make()
        self.assertEqual(sensor.device_class, "humidity")


# ---------------------------------------------------------------
# Wind Speed sensor
# ---------------------------------------------------------------
class TestWindSpeedSensor(unittest.TestCase):
    """Tests for WindSpeedSensor."""

    def _make(self, obs_data=None):
        from noaa_it_all.sensors.weather_observations import WindSpeedSensor
        coord = _make_coordinator(obs_data)
        return WindSpeedSensor(coord, OFFICE, LAT, LON)

    def test_name(self):
        sensor = self._make()
        self.assertEqual(sensor.name, f"NOAA {OFFICE} Wind Speed")

    def test_unit(self):
        sensor = self._make()
        self.assertEqual(sensor.unit_of_measurement, "mph")

    def test_state_converts_kmh_to_mph(self):
        obs = _load_fixture("observations.json")
        sensor = self._make(obs)
        state = sensor.state
        self.assertIsNotNone(state)
        # 16.1 km/h ≈ 10.0 mph
        self.assertAlmostEqual(state, 10.0, delta=0.5)

    def test_state_no_data(self):
        sensor = self._make(None)
        self.assertIsNone(sensor.state)

    def test_icon(self):
        sensor = self._make()
        self.assertEqual(sensor.icon, "mdi:weather-windy")


# ---------------------------------------------------------------
# Wind Direction sensor
# ---------------------------------------------------------------
class TestWindDirectionSensor(unittest.TestCase):
    """Tests for WindDirectionSensor."""

    def _make(self, obs_data=None):
        from noaa_it_all.sensors.weather_observations import WindDirectionSensor
        coord = _make_coordinator(obs_data)
        return WindDirectionSensor(coord, OFFICE, LAT, LON)

    def test_name(self):
        sensor = self._make()
        self.assertEqual(sensor.name, f"NOAA {OFFICE} Wind Direction")

    def test_unit(self):
        sensor = self._make()
        self.assertEqual(sensor.unit_of_measurement, "°")

    def test_state_rounds_to_int(self):
        obs = _load_fixture("observations.json")
        sensor = self._make(obs)
        state = sensor.state
        self.assertIsNotNone(state)
        self.assertEqual(state, 200)

    def test_state_no_data(self):
        sensor = self._make(None)
        self.assertIsNone(sensor.state)

    def test_icon(self):
        sensor = self._make()
        self.assertEqual(sensor.icon, "mdi:compass")

    def test_extra_attrs_cardinal_direction(self):
        obs = _load_fixture("observations.json")
        sensor = self._make(obs)
        attrs = sensor.extra_state_attributes
        self.assertIn("cardinal_direction", attrs)


# ---------------------------------------------------------------
# Barometric Pressure sensor
# ---------------------------------------------------------------
class TestBarometricPressureSensor(unittest.TestCase):
    """Tests for BarometricPressureSensor."""

    def _make(self, obs_data=None):
        from noaa_it_all.sensors.weather_observations import BarometricPressureSensor
        coord = _make_coordinator(obs_data)
        return BarometricPressureSensor(coord, OFFICE, LAT, LON)

    def test_name(self):
        sensor = self._make()
        self.assertEqual(sensor.name, f"NOAA {OFFICE} Barometric Pressure")

    def test_unit(self):
        sensor = self._make()
        self.assertEqual(sensor.unit_of_measurement, "inHg")

    def test_state_converts_pa_to_inhg(self):
        obs = _load_fixture("observations.json")
        sensor = self._make(obs)
        state = sensor.state
        self.assertIsNotNone(state)
        # 101325 Pa ≈ 29.92 inHg
        self.assertAlmostEqual(state, 29.92, delta=0.1)

    def test_state_no_data(self):
        sensor = self._make(None)
        self.assertIsNone(sensor.state)

    def test_icon(self):
        sensor = self._make()
        self.assertEqual(sensor.icon, "mdi:gauge")

    def test_device_class(self):
        sensor = self._make()
        self.assertEqual(sensor.device_class, "pressure")


# ---------------------------------------------------------------
# Dewpoint sensor
# ---------------------------------------------------------------
class TestDewpointSensor(unittest.TestCase):
    """Tests for DewpointSensor."""

    def _make(self, obs_data=None):
        from noaa_it_all.sensors.weather_observations import DewpointSensor
        coord = _make_coordinator(obs_data)
        return DewpointSensor(coord, OFFICE, LAT, LON)

    def test_name(self):
        sensor = self._make()
        self.assertEqual(sensor.name, f"NOAA {OFFICE} Dewpoint")

    def test_unit(self):
        sensor = self._make()
        self.assertEqual(sensor.unit_of_measurement, "°F")

    def test_state_converts_celsius_to_fahrenheit(self):
        obs = _load_fixture("observations.json")
        sensor = self._make(obs)
        state = sensor.state
        self.assertIsNotNone(state)
        # 15.0°C = 59.0°F
        self.assertAlmostEqual(state, 59.0, delta=0.5)

    def test_state_no_data(self):
        sensor = self._make(None)
        self.assertIsNone(sensor.state)

    def test_device_class(self):
        sensor = self._make()
        self.assertEqual(sensor.device_class, "temperature")


# ---------------------------------------------------------------
# Visibility sensor
# ---------------------------------------------------------------
class TestVisibilitySensor(unittest.TestCase):
    """Tests for VisibilitySensor."""

    def _make(self, obs_data=None):
        from noaa_it_all.sensors.weather_observations import VisibilitySensor
        coord = _make_coordinator(obs_data)
        return VisibilitySensor(coord, OFFICE, LAT, LON)

    def test_name(self):
        sensor = self._make()
        self.assertEqual(sensor.name, f"NOAA {OFFICE} Visibility")

    def test_unit(self):
        sensor = self._make()
        self.assertEqual(sensor.unit_of_measurement, "mi")

    def test_state_converts_meters_to_miles(self):
        obs = _load_fixture("observations.json")
        sensor = self._make(obs)
        state = sensor.state
        self.assertIsNotNone(state)
        # 16093 m ≈ 10.0 miles
        self.assertAlmostEqual(state, 10.0, delta=0.5)

    def test_state_no_data(self):
        sensor = self._make(None)
        self.assertIsNone(sensor.state)

    def test_icon(self):
        sensor = self._make()
        self.assertEqual(sensor.icon, "mdi:eye")


# ---------------------------------------------------------------
# Sky Conditions sensor
# ---------------------------------------------------------------
class TestSkyConditionsSensor(unittest.TestCase):
    """Tests for SkyConditionsSensor."""

    def _make(self, obs_data=None):
        from noaa_it_all.sensors.weather_observations import SkyConditionsSensor
        coord = _make_coordinator(obs_data)
        return SkyConditionsSensor(coord, OFFICE, LAT, LON)

    def test_name(self):
        sensor = self._make()
        self.assertEqual(sensor.name, f"NOAA {OFFICE} Sky Conditions")

    def test_state_returns_text(self):
        obs = _load_fixture("observations.json")
        sensor = self._make(obs)
        state = sensor.state
        self.assertEqual(state, "Mostly Cloudy")

    def test_state_no_data(self):
        sensor = self._make(None)
        self.assertIsNone(sensor.state)

    def test_icon(self):
        sensor = self._make()
        self.assertEqual(sensor.icon, "mdi:weather-partly-cloudy")


# ---------------------------------------------------------------
# Feels Like sensor
# ---------------------------------------------------------------
class TestFeelsLikeSensor(unittest.TestCase):
    """Tests for FeelsLikeSensor."""

    def _make(self, obs_data=None):
        from noaa_it_all.sensors.weather_observations import FeelsLikeSensor
        coord = _make_coordinator(obs_data)
        return FeelsLikeSensor(coord, OFFICE, LAT, LON)

    def test_name(self):
        sensor = self._make()
        self.assertEqual(sensor.name, f"NOAA {OFFICE} Feels Like")

    def test_unit(self):
        sensor = self._make()
        self.assertEqual(sensor.unit_of_measurement, "°F")

    def test_state_uses_heat_index(self):
        obs = _load_fixture("observations.json")
        sensor = self._make(obs)
        state = sensor.state
        self.assertIsNotNone(state)
        # heatIndex 23.5°C ≈ 74.3°F
        self.assertAlmostEqual(state, 74.3, delta=0.5)

    def test_state_no_data(self):
        sensor = self._make(None)
        self.assertIsNone(sensor.state)

    def test_device_class(self):
        sensor = self._make()
        self.assertEqual(sensor.device_class, "temperature")

    def test_extra_attrs_feels_like_type(self):
        obs = _load_fixture("observations.json")
        sensor = self._make(obs)
        attrs = sensor.extra_state_attributes
        self.assertIn("feels_like_type", attrs)
        self.assertEqual(attrs["feels_like_type"], "Heat Index")

    def test_extra_attrs_wind_chill_type(self):
        obs = _load_fixture("observations.json")
        # Override to have wind chill
        obs["properties"]["windChill"] = {"value": 18.0}
        obs["properties"]["heatIndex"] = {"value": None}
        sensor = self._make(obs)
        attrs = sensor.extra_state_attributes
        self.assertEqual(attrs["feels_like_type"], "Wind Chill")

    def test_extra_attrs_actual_temp_type(self):
        obs = _load_fixture("observations.json")
        obs["properties"]["windChill"] = {"value": None}
        obs["properties"]["heatIndex"] = {"value": None}
        sensor = self._make(obs)
        attrs = sensor.extra_state_attributes
        self.assertEqual(attrs["feels_like_type"], "Actual Temperature")


if __name__ == "__main__":
    unittest.main()
