"""Tests for weather observation sensor entities.

Covers: Temperature, Humidity, Wind Speed, Wind Direction, Barometric Pressure,
Dewpoint, Visibility, Sky Conditions, Feels Like.
"""

import json
import os
import sys
import unittest
from enum import StrEnum
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
_ha_sensor = MagicMock()
_ha_sensor.SensorEntity = type("SensorEntity", (), {})
# A str enum, like Home Assistant's, so a test can tell a member from a plain string.
_ha_sensor.SensorDeviceClass = StrEnum("SensorDeviceClass", {
    name.upper(): name
    for name in ("temperature", "humidity", "wind_speed", "atmospheric_pressure", "distance")
})

_MOCK_MODULES = {
    "homeassistant": MagicMock(),
    "homeassistant.helpers": MagicMock(),
    "homeassistant.helpers.entity": _ha_entity,
    "homeassistant.helpers.update_coordinator": _ha_coordinator,
    "homeassistant.helpers.entity_platform": MagicMock(),
    "homeassistant.helpers.aiohttp_client": MagicMock(),
    "homeassistant.components": MagicMock(),
    "homeassistant.components.binary_sensor": MagicMock(),
    "homeassistant.components.sensor": _ha_sensor,
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
        self.assertEqual(sensor.name, "Temperature")

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
        self.assertEqual(sensor.native_unit_of_measurement, "°C")

    def test_state_is_nws_celsius(self):
        obs = _load_fixture("observations.json")
        sensor = self._make(obs)
        self.assertEqual(sensor.native_value, 22.2)

    def test_state_no_data(self):
        sensor = self._make(None)
        self.assertIsNone(sensor.native_value)

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
        self.assertEqual(sensor.name, "Humidity")

    def test_unit(self):
        sensor = self._make()
        self.assertEqual(sensor.native_unit_of_measurement, "%")

    def test_state_rounds_to_int(self):
        obs = _load_fixture("observations.json")
        sensor = self._make(obs)
        state = sensor.native_value
        self.assertIsNotNone(state)
        # 63.5 → 64 (rounded)
        self.assertEqual(state, 64)

    def test_state_no_data(self):
        sensor = self._make(None)
        self.assertIsNone(sensor.native_value)

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
        self.assertEqual(sensor.name, "Wind Speed")

    def test_unit(self):
        sensor = self._make()
        self.assertEqual(sensor.native_unit_of_measurement, "km/h")

    def test_state_is_nws_kmh(self):
        obs = _load_fixture("observations.json")
        sensor = self._make(obs)
        self.assertEqual(sensor.native_value, 16.1)

    def test_state_no_data(self):
        sensor = self._make(None)
        self.assertIsNone(sensor.native_value)

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
        self.assertEqual(sensor.name, "Wind Direction")

    def test_unit(self):
        sensor = self._make()
        self.assertEqual(sensor.native_unit_of_measurement, "°")

    def test_state_rounds_to_int(self):
        obs = _load_fixture("observations.json")
        sensor = self._make(obs)
        state = sensor.native_value
        self.assertIsNotNone(state)
        self.assertEqual(state, 200)

    def test_state_no_data(self):
        sensor = self._make(None)
        self.assertIsNone(sensor.native_value)

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
        self.assertEqual(sensor.name, "Barometric Pressure")

    def test_unit(self):
        sensor = self._make()
        self.assertEqual(sensor.native_unit_of_measurement, "hPa")

    def test_state_converts_pa_to_hpa(self):
        obs = _load_fixture("observations.json")
        sensor = self._make(obs)
        # 101325 Pa = 1013.25 hPa
        self.assertEqual(sensor.native_value, 1013.25)

    def test_state_no_data(self):
        sensor = self._make(None)
        self.assertIsNone(sensor.native_value)

    def test_icon(self):
        sensor = self._make()
        self.assertEqual(sensor.icon, "mdi:gauge")

    def test_device_class(self):
        sensor = self._make()
        self.assertEqual(sensor.device_class, "atmospheric_pressure")


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
        self.assertEqual(sensor.name, "Dewpoint")

    def test_unit(self):
        sensor = self._make()
        self.assertEqual(sensor.native_unit_of_measurement, "°C")

    def test_state_is_nws_celsius(self):
        obs = _load_fixture("observations.json")
        sensor = self._make(obs)
        self.assertEqual(sensor.native_value, 15.0)

    def test_state_no_data(self):
        sensor = self._make(None)
        self.assertIsNone(sensor.native_value)

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
        self.assertEqual(sensor.name, "Visibility")

    def test_unit(self):
        sensor = self._make()
        self.assertEqual(sensor.native_unit_of_measurement, "km")

    def test_state_converts_meters_to_km(self):
        obs = _load_fixture("observations.json")
        sensor = self._make(obs)
        # 16093 m = 16.093 km, which Home Assistant shows as 10.0 mi
        self.assertEqual(sensor.native_value, 16.093)

    def test_state_no_data(self):
        sensor = self._make(None)
        self.assertIsNone(sensor.native_value)

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
        self.assertEqual(sensor.name, "Sky Conditions")

    def test_state_returns_text(self):
        obs = _load_fixture("observations.json")
        sensor = self._make(obs)
        state = sensor.native_value
        self.assertEqual(state, "Mostly Cloudy")

    def test_state_no_data(self):
        sensor = self._make(None)
        self.assertIsNone(sensor.native_value)

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
        self.assertEqual(sensor.name, "Feels Like")

    def test_unit(self):
        sensor = self._make()
        self.assertEqual(sensor.native_unit_of_measurement, "°C")

    def test_state_uses_heat_index(self):
        obs = _load_fixture("observations.json")
        sensor = self._make(obs)
        # heatIndex 23.5°C
        self.assertEqual(sensor.native_value, 23.5)

    def test_state_no_data(self):
        sensor = self._make(None)
        self.assertIsNone(sensor.native_value)

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


# ---------------------------------------------------------------
# Per-field observation time
# ---------------------------------------------------------------
class TestObservationTimestamps(unittest.TestCase):
    """A value carried from an older observation says when it was observed."""

    DATA = {
        "station_id": "KILM",
        "properties": {
            "timestamp": "2026-10-13T18:30:00+00:00",
            "temperature": {"value": 29.0},
            "relativeHumidity": {"value": 52.0},
        },
        "field_times": {
            "temperature": "2026-10-13T18:30:00+00:00",
            "relativeHumidity": "2026-10-13T18:20:00+00:00",
        },
    }

    def test_carried_value_has_its_own_time(self):
        from noaa_it_all.sensors.weather_observations import HumiditySensor
        sensor = HumiditySensor(_make_coordinator(self.DATA), OFFICE, LAT, LON)
        self.assertEqual(sensor.native_value, 52)
        self.assertEqual(sensor.extra_state_attributes["timestamp"], "2026-10-13T18:20:00+00:00")

    def test_current_value_has_the_observation_time(self):
        from noaa_it_all.sensors.weather_observations import TemperatureSensor
        sensor = TemperatureSensor(_make_coordinator(self.DATA), OFFICE, LAT, LON)
        self.assertEqual(sensor.extra_state_attributes["timestamp"], "2026-10-13T18:30:00+00:00")

    def test_feels_like_has_the_time_of_its_temperature(self):
        # Its value is the wind chill, heat index or temperature, which all come
        # from the observation the temperature came from.
        from noaa_it_all.sensors.weather_observations import FeelsLikeSensor
        data = {
            "station_id": "KILM",
            "properties": {"timestamp": "2026-10-13T18:30:00+00:00", "temperature": {"value": 29.0}},
            "field_times": {"temperature": "2026-10-13T18:10:00+00:00"},
        }
        sensor = FeelsLikeSensor(_make_coordinator(data), OFFICE, LAT, LON)
        self.assertEqual(sensor.extra_state_attributes["timestamp"], "2026-10-13T18:10:00+00:00")

    def test_without_field_times_the_observation_time_is_used(self):
        from noaa_it_all.sensors.weather_observations import HumiditySensor
        data = {k: v for k, v in self.DATA.items() if k != "field_times"}
        sensor = HumiditySensor(_make_coordinator(data), OFFICE, LAT, LON)
        self.assertEqual(sensor.extra_state_attributes["timestamp"], "2026-10-13T18:30:00+00:00")


# ---------------------------------------------------------------
# Units: NWS's metric values, converted by Home Assistant (#77)
# ---------------------------------------------------------------
class TestObservationsFollowTheUnitSystem(unittest.TestCase):
    """Each sensor reports NWS's value in its metric unit, with a device class HA converts.

    Home Assistant converts a sensor to the install's unit system only when it
    is a SensorEntity reporting native_value and native_unit_of_measurement
    with a device class. The device classes and units are the ones a US
    customary install shows as °F, mph, inHg and mi.
    """

    def _make(self, cls):
        from noaa_it_all.sensors import weather_observations
        return getattr(weather_observations, cls)(
            _make_coordinator(_load_fixture("observations.json")), OFFICE, LAT, LON
        )

    def test_metric_native_values_and_units(self):
        # observations.json: 22.2 degC, dewpoint 15.0, heat index 23.5, 16.1 km/h,
        # 101325 Pa, 16093 m.
        cases = {
            "TemperatureSensor": (22.2, "°C", "temperature", 1),
            "DewpointSensor": (15.0, "°C", "temperature", 1),
            "FeelsLikeSensor": (23.5, "°C", "temperature", 1),
            "WindSpeedSensor": (16.1, "km/h", "wind_speed", 1),
            "BarometricPressureSensor": (1013.25, "hPa", "atmospheric_pressure", 1),
            "VisibilitySensor": (16.093, "km", "distance", 1),
        }
        for cls, (value, unit, device_class, precision) in cases.items():
            with self.subTest(cls):
                sensor = self._make(cls)
                self.assertIsInstance(sensor, _ha_sensor.SensorEntity)
                self.assertEqual(sensor.native_value, value)
                self.assertEqual(sensor.native_unit_of_measurement, unit)
                self.assertEqual(sensor.device_class, device_class)
                self.assertEqual(sensor.suggested_display_precision, precision)

    def test_device_classes_are_home_assistants_enum(self):
        """HA converts a temperature only if its device class *is* SensorDeviceClass.TEMPERATURE.

        sensor/__init__.py checks ``self.device_class is SensorDeviceClass.TEMPERATURE``,
        so a plain 'temperature' string left °C in a US customary install.
        """
        classes = _ha_sensor.SensorDeviceClass
        for cls, member in (
            ("TemperatureSensor", classes.TEMPERATURE), ("DewpointSensor", classes.TEMPERATURE),
            ("FeelsLikeSensor", classes.TEMPERATURE), ("HumiditySensor", classes.HUMIDITY),
            ("WindSpeedSensor", classes.WIND_SPEED),
            ("BarometricPressureSensor", classes.ATMOSPHERIC_PRESSURE),
            ("VisibilitySensor", classes.DISTANCE),
        ):
            with self.subTest(cls):
                self.assertIs(self._make(cls).device_class, member)

    def test_values_are_not_rounded_before_home_assistant_converts_them(self):
        """9.252 km/h is 5.7 mph; rounded to 9.3 km/h first it would show 5.8."""
        from noaa_it_all.sensors.weather_observations import WindSpeedSensor
        data = {"properties": {"windSpeed": {"value": 9.252}}}
        sensor = WindSpeedSensor(_make_coordinator(data), OFFICE, LAT, LON)
        self.assertEqual(sensor.native_value, 9.252)

    def test_a_missing_value_is_unknown(self):
        for cls in ("TemperatureSensor", "WindSpeedSensor", "BarometricPressureSensor",
                    "VisibilitySensor", "DewpointSensor"):
            with self.subTest(cls):
                from noaa_it_all.sensors import weather_observations
                sensor = getattr(weather_observations, cls)(
                    _make_coordinator({"properties": {}}), OFFICE, LAT, LON
                )
                self.assertIsNone(sensor.native_value)

    def test_unconverted_sensors_keep_their_units(self):
        self.assertEqual(self._make("HumiditySensor").native_unit_of_measurement, "%")
        self.assertEqual(self._make("WindDirectionSensor").native_unit_of_measurement, "°")
        self.assertIsNone(self._make("SkyConditionsSensor").native_unit_of_measurement)


if __name__ == "__main__":
    unittest.main()
