"""Tests for space weather and surf sensor entity state logic."""

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


OFFICE = "SGX"


def _load_fixture(name):
    with open(os.path.join(_FIXTURES, name)) as f:
        if name.endswith(".json"):
            return json.load(f)
        return f.read()


def _make_coordinator(data=None):
    coord = MagicMock()
    coord.data = data
    return coord


# ---------------------------------------------------------------
# Space weather sensor state tests
# ---------------------------------------------------------------

class TestGeomagneticSensor(unittest.TestCase):
    """Tests for GeomagneticSensor state computation."""

    def _make(self, dst_data=None):
        from noaa_it_all.sensors.space_weather import GeomagneticSensor
        data = {"dst": dst_data or []}
        coord = _make_coordinator(data)
        return GeomagneticSensor(coord, OFFICE)

    def test_state_returns_latest_dst(self):
        dst_data = _load_fixture("space_weather_dst.json")
        sensor = self._make(dst_data)
        self.assertEqual(sensor.state, -15)

    def test_state_no_data(self):
        from noaa_it_all.sensors.space_weather import GeomagneticSensor
        coord = _make_coordinator(None)
        sensor = GeomagneticSensor(coord, OFFICE)
        self.assertIsNone(sensor.state)

    def test_state_empty_dst(self):
        sensor = self._make([])
        self.assertIsNone(sensor.state)

    def test_name(self):
        sensor = self._make()
        self.assertEqual(sensor.name, "NOAA Space - Geomagnetic Storm")

    def test_unique_id(self):
        sensor = self._make()
        self.assertEqual(sensor.unique_id, f"noaa_{OFFICE}_geomagnetic_storm")

    def test_device_info_space_group(self):
        sensor = self._make()
        info = sensor.device_info
        ids = list(info["identifiers"])[0]
        self.assertIn("space", ids[1])


class TestGeomagneticSensorInterpretation(unittest.TestCase):
    """Tests for GeomagneticSensorInterpretation state computation."""

    def _make(self, dst_data=None):
        from noaa_it_all.sensors.space_weather import GeomagneticSensorInterpretation
        data = {"dst": dst_data or []}
        coord = _make_coordinator(data)
        return GeomagneticSensorInterpretation(coord, OFFICE)

    def test_state_quiet(self):
        sensor = self._make([{"dst": -10}])
        state = sensor.state
        self.assertIn("Quiet", state)

    def test_state_no_data(self):
        from noaa_it_all.sensors.space_weather import GeomagneticSensorInterpretation
        coord = _make_coordinator(None)
        sensor = GeomagneticSensorInterpretation(coord, OFFICE)
        self.assertIsNone(sensor.state)

    def test_name(self):
        sensor = self._make()
        self.assertEqual(sensor.name, "NOAA Space - Geomagnetic Storm Interpretation")

    def test_unique_id(self):
        sensor = self._make()
        self.assertEqual(sensor.unique_id, f"noaa_{OFFICE}_geomagnetic_storm_interpretation")

    def test_device_info_space_group(self):
        sensor = self._make()
        info = sensor.device_info
        ids = list(info["identifiers"])[0]
        self.assertIn("space", ids[1])


class TestPlanetaryKIndexSensor(unittest.TestCase):
    """Tests for PlanetaryKIndexSensor state computation."""

    def _make(self, kp_data=None):
        from noaa_it_all.sensors.space_weather import PlanetaryKIndexSensor
        data = {"kp_index": kp_data or []}
        coord = _make_coordinator(data)
        return PlanetaryKIndexSensor(coord, OFFICE)

    def test_state_returns_latest_kp(self):
        kp_data = _load_fixture("space_weather_kp.json")
        sensor = self._make(kp_data)
        # PlanetaryKIndexSensor uses kp_data[-1] (last element)
        self.assertEqual(sensor.state, 3.00)

    def test_state_no_data(self):
        from noaa_it_all.sensors.space_weather import PlanetaryKIndexSensor
        coord = _make_coordinator(None)
        sensor = PlanetaryKIndexSensor(coord, OFFICE)
        self.assertIsNone(sensor.state)

    def test_name(self):
        sensor = self._make()
        self.assertEqual(sensor.name, "NOAA Space - Planetary K-index")

    def test_unique_id(self):
        sensor = self._make()
        self.assertEqual(sensor.unique_id, f"noaa_{OFFICE}_planetary_k_index")

    def test_device_info_space_group(self):
        sensor = self._make()
        info = sensor.device_info
        ids = list(info["identifiers"])[0]
        self.assertIn("space", ids[1])


class TestPlanetaryKIndexSensorRating(unittest.TestCase):
    """Tests for PlanetaryKIndexSensorRating state computation."""

    def _make(self, kp_data=None):
        from noaa_it_all.sensors.space_weather import PlanetaryKIndexSensorRating
        data = {"kp_index": kp_data or []}
        coord = _make_coordinator(data)
        return PlanetaryKIndexSensorRating(coord, OFFICE)

    def test_state_moderate(self):
        sensor = self._make([{"kp_index": 3.33}])
        self.assertEqual(sensor.state, "moderate")

    def test_state_low(self):
        sensor = self._make([{"kp_index": 1.0}])
        self.assertEqual(sensor.state, "low")

    def test_name(self):
        sensor = self._make()
        self.assertEqual(sensor.name, "NOAA Space - Planetary K-index Rating")

    def test_unique_id(self):
        sensor = self._make()
        self.assertEqual(sensor.unique_id, f"noaa_{OFFICE}_planetary_k_index_rating")

    def test_state_no_data(self):
        from noaa_it_all.sensors.space_weather import PlanetaryKIndexSensorRating
        coord = _make_coordinator(None)
        sensor = PlanetaryKIndexSensorRating(coord, OFFICE)
        self.assertIsNone(sensor.state)

    def test_device_info_space_group(self):
        sensor = self._make()
        info = sensor.device_info
        ids = list(info["identifiers"])[0]
        self.assertIn("space", ids[1])


# ---------------------------------------------------------------
# Surf sensor state tests
# ---------------------------------------------------------------

class TestRipCurrentRiskSensor(unittest.TestCase):
    """Tests for RipCurrentRiskSensor state computation."""

    def _make(self, forecast_text=""):
        from noaa_it_all.sensors.surf import RipCurrentRiskSensor
        data = {"forecast_text": forecast_text, "source_url": ""}
        coord = _make_coordinator(data)
        return RipCurrentRiskSensor(coord, OFFICE)

    def test_state_high(self):
        sensor = self._make("high rip current risk expected today")
        self.assertEqual(sensor.state, "High")

    def test_state_moderate(self):
        sensor = self._make("moderate rip current risk")
        self.assertEqual(sensor.state, "Moderate")

    def test_state_low(self):
        sensor = self._make("low rip current risk")
        self.assertEqual(sensor.state, "Low")

    def test_state_from_fixture(self):
        text = _load_fixture("surf_srf.txt")
        sensor = self._make(text)
        self.assertEqual(sensor.state, "Moderate")


class TestSurfHeightSensor(unittest.TestCase):
    """Tests for SurfHeightSensor state computation."""

    def _make(self, forecast_text=""):
        from noaa_it_all.sensors.surf import SurfHeightSensor
        data = {"forecast_text": forecast_text, "source_url": ""}
        coord = _make_coordinator(data)
        return SurfHeightSensor(coord, OFFICE)

    def test_state_from_fixture(self):
        text = _load_fixture("surf_srf.txt")
        sensor = self._make(text)
        # Should parse "3 TO 5 FEET" as numeric
        state = sensor.state
        self.assertIsNotNone(state)


class TestWaterTemperatureSensor(unittest.TestCase):
    """Tests for WaterTemperatureSensor state computation."""

    def _make(self, forecast_text="", water_temp_f=None):
        from noaa_it_all.sensors.surf import WaterTemperatureSensor
        data = {
            "forecast_text": forecast_text,
            "source_url": "",
            "water_temp_f": water_temp_f,
        }
        coord = _make_coordinator(data)
        return WaterTemperatureSensor(coord, OFFICE)

    def test_state_from_coops(self):
        sensor = self._make(water_temp_f=62.4)
        state = sensor.state
        self.assertEqual(state, 62.4)

    def test_state_no_data(self):
        from noaa_it_all.sensors.surf import WaterTemperatureSensor
        coord = _make_coordinator(None)
        sensor = WaterTemperatureSensor(coord, OFFICE)
        self.assertIsNone(sensor.state)


# ---------------------------------------------------------------
# Aurora and solar radiation sensor tests
# ---------------------------------------------------------------

class TestAuroraNextTimeSensor(unittest.TestCase):
    """Tests for AuroraNextTimeSensor state computation."""

    def _make(self, kp_data=None):
        from noaa_it_all.sensors.space_weather import AuroraNextTimeSensor
        data = {"kp_index": kp_data or []}
        coord = _make_coordinator(data)
        return AuroraNextTimeSensor(coord, OFFICE)

    def test_state_with_data(self):
        sensor = self._make([{"kp_index": 3.0}])
        state = sensor.state
        self.assertIsNotNone(state)
        self.assertIn("UTC", state)

    def test_state_no_data(self):
        from noaa_it_all.sensors.space_weather import AuroraNextTimeSensor
        coord = _make_coordinator(None)
        sensor = AuroraNextTimeSensor(coord, OFFICE)
        self.assertIsNone(sensor.state)

    def test_state_empty_kp(self):
        sensor = self._make([])
        self.assertEqual(sensor.state, "No Data")

    def test_unique_id(self):
        sensor = self._make()
        self.assertEqual(sensor.unique_id, f"noaa_{OFFICE}_aurora_next_time")

    def test_icon(self):
        sensor = self._make()
        self.assertEqual(sensor.icon, "mdi:weather-night")

    def test_extra_attrs_with_data(self):
        sensor = self._make([{"kp_index": 5.0}])
        attrs = sensor.extra_state_attributes
        self.assertIn("current_kp", attrs)
        self.assertIn("conditions", attrs)

    def test_device_info_space_group(self):
        sensor = self._make()
        info = sensor.device_info
        ids = list(info["identifiers"])[0]
        self.assertIn("space", ids[1])


class TestAuroraDurationSensor(unittest.TestCase):
    """Tests for AuroraDurationSensor state computation."""

    def _make(self, kp_data=None):
        from noaa_it_all.sensors.space_weather import AuroraDurationSensor
        data = {"kp_index": kp_data or []}
        coord = _make_coordinator(data)
        return AuroraDurationSensor(coord, OFFICE)

    def test_state_with_data(self):
        sensor = self._make([{"kp_index": 5.0}])
        state = sensor.state
        self.assertIsNotNone(state)

    def test_state_no_data(self):
        from noaa_it_all.sensors.space_weather import AuroraDurationSensor
        coord = _make_coordinator(None)
        sensor = AuroraDurationSensor(coord, OFFICE)
        self.assertIsNone(sensor.state)

    def test_unique_id(self):
        sensor = self._make()
        self.assertEqual(sensor.unique_id, f"noaa_{OFFICE}_aurora_duration")

    def test_icon(self):
        sensor = self._make()
        self.assertEqual(sensor.icon, "mdi:timer-outline")

    def test_unit(self):
        sensor = self._make()
        self.assertEqual(sensor.unit_of_measurement, "hours")

    def test_name(self):
        sensor = self._make()
        self.assertEqual(sensor.name, f"NOAA {OFFICE} Aurora Duration")


class TestAuroraVisibilityProbabilitySensor(unittest.TestCase):
    """Tests for AuroraVisibilityProbabilitySensor state computation."""

    def _make(self, kp_data=None):
        from noaa_it_all.sensors.space_weather import AuroraVisibilityProbabilitySensor
        data = {"kp_index": kp_data or []}
        coord = _make_coordinator(data)
        return AuroraVisibilityProbabilitySensor(coord, OFFICE)

    def test_state_with_data(self):
        sensor = self._make([{"kp_index": 5.0}])
        state = sensor.state
        self.assertIsNotNone(state)

    def test_state_no_data(self):
        from noaa_it_all.sensors.space_weather import AuroraVisibilityProbabilitySensor
        coord = _make_coordinator(None)
        sensor = AuroraVisibilityProbabilitySensor(coord, OFFICE)
        self.assertIsNone(sensor.state)

    def test_unique_id(self):
        sensor = self._make()
        self.assertEqual(sensor.unique_id, f"noaa_{OFFICE}_aurora_visibility_probability")

    def test_icon(self):
        sensor = self._make()
        self.assertEqual(sensor.icon, "mdi:percent")

    def test_unit(self):
        sensor = self._make()
        self.assertEqual(sensor.unit_of_measurement, "%")

    def test_name(self):
        sensor = self._make()
        self.assertEqual(sensor.name, f"NOAA {OFFICE} Aurora Visibility Probability")

    def test_extra_attrs_with_data(self):
        sensor = self._make([{"kp_index": 5.0}])
        attrs = sensor.extra_state_attributes
        self.assertIn("current_kp", attrs)
        self.assertIn("visibility_class", attrs)
        self.assertIn("required_kp", attrs)


class TestSolarRadiationStormAlertsSensor(unittest.TestCase):
    """Tests for SolarRadiationStormAlertsSensor state computation."""

    def _make(self, space_alerts=None):
        from noaa_it_all.sensors.space_weather import SolarRadiationStormAlertsSensor
        data = {"space_alerts": space_alerts or []}
        coord = _make_coordinator(data)
        return SolarRadiationStormAlertsSensor(coord, OFFICE)

    def test_state_no_alerts(self):
        sensor = self._make([])
        self.assertEqual(sensor.state, 0)

    def test_state_no_data(self):
        from noaa_it_all.sensors.space_weather import SolarRadiationStormAlertsSensor
        coord = _make_coordinator(None)
        sensor = SolarRadiationStormAlertsSensor(coord, OFFICE)
        self.assertIsNone(sensor.state)

    def test_unique_id(self):
        sensor = self._make()
        self.assertEqual(sensor.unique_id, f"noaa_{OFFICE}_solar_radiation_storm_alerts")

    def test_icon(self):
        sensor = self._make()
        self.assertEqual(sensor.icon, "mdi:radioactive")

    def test_unit(self):
        sensor = self._make()
        self.assertEqual(sensor.unit_of_measurement, "alerts")

    def test_name(self):
        sensor = self._make()
        self.assertEqual(sensor.name, f"NOAA {OFFICE} Solar Radiation Storm Alerts")

    def test_device_info_space_group(self):
        sensor = self._make()
        info = sensor.device_info
        ids = list(info["identifiers"])[0]
        self.assertIn("space", ids[1])


if __name__ == "__main__":
    unittest.main()
