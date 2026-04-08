"""Tests for weather.py entity logic using mocked HA modules."""

import asyncio
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


class _FakeCoordinatorEntity:
    """Minimal stand-in for CoordinatorEntity used by tests."""

    def __init__(self, coordinator):
        self.coordinator = coordinator
        self._remove_callbacks = []

    async def async_added_to_hass(self):
        pass

    def async_on_remove(self, callback):
        self._remove_callbacks.append(callback)

    def _handle_coordinator_update(self):
        pass

    def async_write_ha_state(self):
        pass


_ha_coordinator.CoordinatorEntity = _FakeCoordinatorEntity
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


class TestAsyncAddedToHass(unittest.TestCase):
    """Tests for async_added_to_hass lifecycle."""

    def _run(self, coro):
        return asyncio.get_event_loop().run_until_complete(coro)

    def _make(self, obs_data=None, forecast_data=None):
        from noaa_it_all.weather import NOAAWeather
        obs_coord = _make_coordinator(obs_data)
        forecast_coord = _make_coordinator(forecast_data)
        return NOAAWeather(obs_coord, forecast_coord, OFFICE, LAT, LON)

    def test_processes_existing_data_on_add(self):
        """Entity should populate attrs from pre-fetched coordinator data."""
        obs_data = {
            "properties": {
                "temperature": {"value": 20.0},
                "relativeHumidity": {"value": 65.0},
                "barometricPressure": {"value": 101325},
                "textDescription": "Sunny",
                "timestamp": "2025-01-15T12:00:00+00:00",
                "dewpoint": {"value": 10.0},
                "visibility": {"value": 16093},
                "windSpeed": {"value": 16.0},
                "windDirection": {"value": 180},
                "windChill": {"value": None},
                "heatIndex": {"value": None},
            },
            "station_id": "KSAN",
        }
        entity = self._make(obs_data=obs_data)
        self._run(entity.async_added_to_hass())
        # Temperature 20°C -> 68°F
        self.assertAlmostEqual(entity._attr_native_temperature, 68.0, places=0)
        self.assertEqual(entity._attr_humidity, 65)
        self.assertIsNotNone(entity._attr_native_pressure)

    def test_subscribes_to_forecast_coordinator(self):
        """Entity should register a listener on the forecast coordinator."""
        entity = self._make()
        self._run(entity.async_added_to_hass())
        entity._forecast_coordinator.async_add_listener.assert_called_once()
        # The listener should be _handle_forecast_update (lightweight),
        # not _handle_coordinator_update (which re-parses observations).
        listener = entity._forecast_coordinator.async_add_listener.call_args[0][0]
        self.assertEqual(listener.__name__, "_handle_forecast_update")
        # async_on_remove should have been called to register cleanup
        self.assertEqual(len(entity._remove_callbacks), 1)

    def test_forecast_update_calls_write_ha_state(self):
        """Forecast listener should call async_write_ha_state, not re-parse obs."""
        from unittest.mock import patch as _patch
        entity = self._make()
        self._run(entity.async_added_to_hass())
        with _patch.object(entity, "async_write_ha_state") as mock_write:
            entity._handle_forecast_update()
            mock_write.assert_called_once()

    def test_no_forecast_coordinator_no_listener(self):
        """Entity should not crash when forecast coordinator is None."""
        from noaa_it_all.weather import NOAAWeather
        obs_coord = _make_coordinator(None)
        entity = NOAAWeather(obs_coord, None, OFFICE, LAT, LON)
        self._run(entity.async_added_to_hass())
        self.assertEqual(len(entity._remove_callbacks), 0)

    def test_handles_none_data_gracefully(self):
        """Entity should not crash when coordinator data is None."""
        entity = self._make(obs_data=None)
        self._run(entity.async_added_to_hass())
        self.assertFalse(hasattr(entity, '_attr_native_temperature')
                         and entity._attr_native_temperature is not None)


if __name__ == "__main__":
    unittest.main()
