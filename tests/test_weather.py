"""Tests for weather.py entity logic using mocked HA modules."""

import asyncio
import os
import sys
import unittest
from datetime import datetime
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
        entity = self._make()
        entity.hass = MagicMock()
        entity.async_update_listeners = MagicMock()
        self._run(entity.async_added_to_hass())
        with patch.object(entity, "async_write_ha_state") as mock_write:
            entity._handle_forecast_update()
            mock_write.assert_called_once()

    def test_forecast_update_pushes_the_new_forecast_to_subscribers(self):
        """Without this the weather card keeps the forecast it subscribed with."""
        entity = self._make()
        entity.hass = MagicMock()
        entity.async_update_listeners = MagicMock(return_value="update-coroutine")
        self._run(entity.async_added_to_hass())

        entity._handle_forecast_update()

        entity.async_update_listeners.assert_called_once_with(None)
        entity.hass.async_create_task.assert_called_once_with("update-coroutine")

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


class TestMapCondition(unittest.TestCase):
    """#33 P3.1: the sky descriptions NWS uses most must map correctly."""

    def _map(self, description, timestamp=None):
        from noaa_it_all.weather import NOAAWeather
        return NOAAWeather._map_condition(description, timestamp)

    def test_partly_cloudy_is_partlycloudy_not_cloudy(self):
        self.assertEqual(self._map("Partly Cloudy"), "partlycloudy")

    def test_partly_cloudy_night_is_partlycloudy(self):
        self.assertEqual(self._map("Partly Cloudy", "2026-10-03T04:00:00Z"), "partlycloudy")

    def test_mostly_cloudy_stays_cloudy(self):
        """As in Home Assistant's own NWS integration."""
        self.assertEqual(self._map("Mostly Cloudy"), "cloudy")

    def test_cloudy_and_overcast_are_cloudy(self):
        self.assertEqual(self._map("Cloudy"), "cloudy")
        self.assertEqual(self._map("Overcast"), "cloudy")

    def test_partly_and_mostly_sunny_are_partlycloudy(self):
        self.assertEqual(self._map("Partly Sunny"), "partlycloudy")
        self.assertEqual(self._map("Mostly Sunny"), "partlycloudy")

    def test_precipitation_still_wins_over_clouds(self):
        self.assertEqual(self._map("Partly Cloudy then Chance Rain Showers"), "rainy")

    def test_clear_by_day_and_night(self):
        self.assertEqual(self._map("Clear", "2026-10-03T15:00:00Z"), "sunny")
        self.assertEqual(self._map("Clear", "2026-10-03T03:00:00Z"), "clear-night")


def _period(start, is_daytime, temperature, name):
    """An NWS extended forecast period, as api.weather.gov serves it."""
    return {
        "name": name,
        "startTime": start,
        "isDaytime": is_daytime,
        "temperature": temperature,
        "shortForecast": "Partly Cloudy",
        "windSpeed": "5 mph",
        "windDirection": "SW",
        "probabilityOfPrecipitation": {"unitCode": "wmoUnit:percent", "value": None},
    }


def _frozen_now(hour, minute):
    """A datetime class whose now() is 2026-10-14 at the given local time."""
    class _Frozen(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 10, 14, hour, minute, tzinfo=tz)
    return _Frozen


class TestDailyForecast(unittest.TestCase):
    """#75: one daily forecast entry per date, and never the observed temperature as a high."""

    OBSERVED = 61.3

    def _daily(self, periods, hour, minute):
        from noaa_it_all.weather import NOAAWeather
        entity = NOAAWeather(_make_coordinator(None), _make_coordinator({"extended": {
            "properties": {"periods": periods}}}), OFFICE, LAT, LON)
        entity._attr_native_temperature = self.OBSERVED
        with patch("noaa_it_all.weather.Forecast", dict), \
                patch("noaa_it_all.weather.datetime", _frozen_now(hour, minute)):
            return asyncio.run(entity.async_forecast_daily())

    def test_after_midnight_one_entry_for_today(self):
        """At 03:30 NWS starts with an Overnight period; today has one entry, from Today and Tonight."""
        forecasts = self._daily([
            _period("2026-10-14T03:00:00-04:00", False, 55, "Overnight"),
            _period("2026-10-14T06:00:00-04:00", True, 75, "Today"),
            _period("2026-10-14T18:00:00-04:00", False, 52, "Tonight"),
            _period("2026-10-15T06:00:00-04:00", True, 77, "Thursday"),
            _period("2026-10-15T18:00:00-04:00", False, 50, "Thursday Night"),
        ], 3, 30)
        dates = [f["datetime"][:10] for f in forecasts]
        self.assertEqual(dates, ["2026-10-14", "2026-10-15"])
        self.assertEqual((forecasts[0]["temperature"], forecasts[0]["templow"]), (75, 52))
        self.assertNotIn(self.OBSERVED, [f["temperature"] for f in forecasts])

    def test_evening_today_has_tonights_low_and_no_high(self):
        """In the evening NWS has no high left for today, so the observed temperature isn't used as one."""
        forecasts = self._daily([
            _period("2026-10-14T20:00:00-04:00", False, 52, "Tonight"),
            _period("2026-10-15T06:00:00-04:00", True, 77, "Thursday"),
            _period("2026-10-15T18:00:00-04:00", False, 50, "Thursday Night"),
        ], 20, 0)
        dates = [f["datetime"][:10] for f in forecasts]
        self.assertEqual(dates, ["2026-10-14", "2026-10-15"])
        self.assertEqual((forecasts[0]["temperature"], forecasts[0]["templow"]), (None, 52))
        self.assertEqual((forecasts[1]["temperature"], forecasts[1]["templow"]), (77, 50))

    def test_overnight_starting_before_3am_is_not_a_separate_entry(self):
        """An Overnight period from 01:00 falls in the 3 AM cutoff window; still one entry for today."""
        forecasts = self._daily([
            _period("2026-10-14T01:00:00-04:00", False, 55, "Overnight"),
            _period("2026-10-14T06:00:00-04:00", True, 75, "Today"),
            _period("2026-10-14T18:00:00-04:00", False, 52, "Tonight"),
            _period("2026-10-15T06:00:00-04:00", True, 77, "Thursday"),
        ], 1, 30)
        self.assertEqual([(f["datetime"][:10], f["temperature"]) for f in forecasts],
                         [("2026-10-14", 75), ("2026-10-15", 77)])

    def test_last_nights_period_after_midnight_is_skipped(self):
        """A forecast fetched before midnight still starts with yesterday's Tonight; it gets no entry."""
        forecasts = self._daily([
            _period("2026-10-13T18:00:00-04:00", False, 54, "Tonight"),
            _period("2026-10-14T06:00:00-04:00", True, 75, "Wednesday"),
            _period("2026-10-14T18:00:00-04:00", False, 52, "Wednesday Night"),
        ], 0, 30)
        self.assertEqual([(f["datetime"][:10], f["temperature"], f["templow"]) for f in forecasts],
                         [("2026-10-14", 75, 52)])

    def test_a_night_after_a_day_never_takes_that_days_high(self):
        """With a day period missing, the night that follows gets no entry with the earlier day's high."""
        forecasts = self._daily([
            _period("2026-10-14T10:00:00-04:00", True, 75, "Today"),
            _period("2026-10-14T18:00:00-04:00", False, 52, "Tonight"),
            _period("2026-10-15T18:00:00-04:00", False, 50, "Thursday Night"),
            _period("2026-10-16T06:00:00-04:00", True, 80, "Friday"),
            _period("2026-10-16T18:00:00-04:00", False, 55, "Friday Night"),
        ], 10, 0)
        self.assertEqual([(f["datetime"][:10], f["temperature"]) for f in forecasts],
                         [("2026-10-14", 75), ("2026-10-16", 80)])

    def test_daytime_start_unchanged(self):
        """During the day the forecast starts with Today, as before."""
        forecasts = self._daily([
            _period("2026-10-14T10:00:00-04:00", True, 75, "Today"),
            _period("2026-10-14T18:00:00-04:00", False, 52, "Tonight"),
            _period("2026-10-15T06:00:00-04:00", True, 77, "Thursday"),
            _period("2026-10-15T18:00:00-04:00", False, 50, "Thursday Night"),
        ], 10, 0)
        self.assertEqual([(f["datetime"][:10], f["temperature"], f["templow"]) for f in forecasts],
                         [("2026-10-14", 75, 52), ("2026-10-15", 77, 50)])


if __name__ == "__main__":
    unittest.main()
