"""Tests for weather.py entity logic using mocked HA modules."""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CC = os.path.join(_REPO, "custom_components")

if _CC not in sys.path:
    sys.path.insert(0, _CC)

# ---------------------------------------------------------------------------
# Mock Home Assistant modules
# ---------------------------------------------------------------------------
_ha_entity = MagicMock()
_ha_coordinator = MagicMock()
_ha_weather_mod = MagicMock()
_ha_const = MagicMock()

_ha_coordinator.CoordinatorEntity = type("CoordinatorEntity", (), {
    "__init__": lambda self, coordinator: setattr(self, "coordinator", coordinator),
})
_ha_coordinator.DataUpdateCoordinator = type("DataUpdateCoordinator", (), {})
_ha_entity.DeviceInfo = dict
_ha_weather_mod.WeatherEntity = type("WeatherEntity", (), {})
_ha_weather_mod.WeatherEntityFeature = MagicMock()
_ha_weather_mod.WeatherEntityFeature.FORECAST_DAILY = 1
_ha_weather_mod.WeatherEntityFeature.FORECAST_HOURLY = 2
_ha_weather_mod.Forecast = MagicMock()

_MOCK_MODULES = {
    "homeassistant": MagicMock(),
    "homeassistant.components": MagicMock(),
    "homeassistant.components.weather": _ha_weather_mod,
    "homeassistant.components.binary_sensor": MagicMock(),
    "homeassistant.components.image": MagicMock(),
    "homeassistant.const": _ha_const,
    "homeassistant.config_entries": MagicMock(),
    "homeassistant.core": MagicMock(),
    "homeassistant.helpers": MagicMock(),
    "homeassistant.helpers.entity": _ha_entity,
    "homeassistant.helpers.entity_platform": MagicMock(),
    "homeassistant.helpers.update_coordinator": _ha_coordinator,
    "homeassistant.helpers.aiohttp_client": MagicMock(),
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


def _make_coordinator(data=None):
    coord = MagicMock()
    coord.data = data
    return coord


class TestNOAAWeatherEntity(unittest.TestCase):
    """Tests for NOAAWeather entity properties."""

    def _make(self, obs_data=None, forecast_data=None):
        from noaa_it_all.weather import NOAAWeather
        obs_coord = _make_coordinator(obs_data)
        forecast_coord = _make_coordinator(forecast_data)
        return NOAAWeather(obs_coord, forecast_coord, OFFICE, LAT, LON)

    def test_name(self):
        entity = self._make()
        self.assertEqual(entity.name, f"NOAA {OFFICE} Weather")

    def test_unique_id_format(self):
        entity = self._make()
        uid = entity.unique_id
        self.assertTrue(uid.startswith("noaa_"))
        self.assertIn(OFFICE, uid)
        self.assertTrue(uid.endswith("_weather"))

    def test_unique_id_negative_coords(self):
        from noaa_it_all.weather import NOAAWeather
        obs_coord = _make_coordinator(None)
        forecast_coord = _make_coordinator(None)
        entity = NOAAWeather(obs_coord, forecast_coord, OFFICE, -33.8688, 151.2093)
        uid = entity.unique_id
        self.assertIn("n33_8688", uid)
        self.assertNotIn("--", uid)

    def test_device_info(self):
        entity = self._make()
        info = entity.device_info
        self.assertIn("identifiers", info)
        self.assertIn("manufacturer", info)
        self.assertEqual(info["manufacturer"], "NOAA")

    def test_extra_state_attributes_no_data(self):
        entity = self._make(obs_data=None, forecast_data=None)
        entity.coordinator.data = None
        attrs = entity.extra_state_attributes
        self.assertIsInstance(attrs, dict)


if __name__ == "__main__":
    unittest.main()
