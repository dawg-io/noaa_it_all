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
        # 20 °C, as NWS reports it; Home Assistant converts it.
        self.assertEqual(entity._attr_native_temperature, 20.0)
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


def _f(celsius):
    """A native °C forecast temperature as a US customary install shows it: whole °F.

    Home Assistant converts with ×1.8 + 32 and rounds °F to whole degrees.
    """
    return None if celsius is None else round(celsius * 1.8 + 32)


def _highs_and_lows(forecasts):
    """Each entry's date, high and low, in the whole °F a US customary install shows."""
    return [(f["datetime"][:10], _f(f["native_temperature"]), _f(f["native_templow"])) for f in forecasts]


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
        self.assertEqual(_highs_and_lows(forecasts), [("2026-10-14", 75, 52), ("2026-10-15", 77, 50)])
        self.assertNotIn(self.OBSERVED, [f["native_temperature"] for f in forecasts])

    def test_evening_today_has_tonights_low_and_no_high(self):
        """In the evening NWS has no high left for today, so the observed temperature isn't used as one."""
        forecasts = self._daily([
            _period("2026-10-14T20:00:00-04:00", False, 52, "Tonight"),
            _period("2026-10-15T06:00:00-04:00", True, 77, "Thursday"),
            _period("2026-10-15T18:00:00-04:00", False, 50, "Thursday Night"),
        ], 20, 0)
        self.assertEqual(_highs_and_lows(forecasts), [("2026-10-14", None, 52), ("2026-10-15", 77, 50)])

    def test_overnight_starting_before_3am_is_not_a_separate_entry(self):
        """An Overnight period from 01:00 falls in the 3 AM cutoff window; still one entry for today."""
        forecasts = self._daily([
            _period("2026-10-14T01:00:00-04:00", False, 55, "Overnight"),
            _period("2026-10-14T06:00:00-04:00", True, 75, "Today"),
            _period("2026-10-14T18:00:00-04:00", False, 52, "Tonight"),
            _period("2026-10-15T06:00:00-04:00", True, 77, "Thursday"),
        ], 1, 30)
        self.assertEqual([entry[:2] for entry in _highs_and_lows(forecasts)],
                         [("2026-10-14", 75), ("2026-10-15", 77)])

    def test_last_nights_period_after_midnight_is_skipped(self):
        """A forecast fetched before midnight still starts with yesterday's Tonight; it gets no entry."""
        forecasts = self._daily([
            _period("2026-10-13T18:00:00-04:00", False, 54, "Tonight"),
            _period("2026-10-14T06:00:00-04:00", True, 75, "Wednesday"),
            _period("2026-10-14T18:00:00-04:00", False, 52, "Wednesday Night"),
        ], 0, 30)
        self.assertEqual(_highs_and_lows(forecasts), [("2026-10-14", 75, 52)])

    def test_a_night_after_a_day_never_takes_that_days_high(self):
        """With a day period missing, the night that follows gets no entry with the earlier day's high."""
        forecasts = self._daily([
            _period("2026-10-14T10:00:00-04:00", True, 75, "Today"),
            _period("2026-10-14T18:00:00-04:00", False, 52, "Tonight"),
            _period("2026-10-15T18:00:00-04:00", False, 50, "Thursday Night"),
            _period("2026-10-16T06:00:00-04:00", True, 80, "Friday"),
            _period("2026-10-16T18:00:00-04:00", False, 55, "Friday Night"),
        ], 10, 0)
        self.assertEqual([entry[:2] for entry in _highs_and_lows(forecasts)],
                         [("2026-10-14", 75), ("2026-10-16", 80)])

    def test_daytime_start_unchanged(self):
        """During the day the forecast starts with Today, as before."""
        forecasts = self._daily([
            _period("2026-10-14T10:00:00-04:00", True, 75, "Today"),
            _period("2026-10-14T18:00:00-04:00", False, 52, "Tonight"),
            _period("2026-10-15T06:00:00-04:00", True, 77, "Thursday"),
            _period("2026-10-15T18:00:00-04:00", False, 50, "Thursday Night"),
        ], 10, 0)
        self.assertEqual(_highs_and_lows(forecasts), [("2026-10-14", 75, 52), ("2026-10-15", 77, 50)])


class TestImperialByDefault(unittest.TestCase):
    """A new weather entity shows US customary units in any install.

    A weather entity has no suggested units, so the entity's own unit settings
    are stored when Home Assistant first sees it; it shows the unit system's
    units without them. Picking others in its settings replaces them.
    """

    def _initial(self, from_home_assistant=None):
        from noaa_it_all.weather import NOAAWeather
        entity = NOAAWeather(_make_coordinator(None), _make_coordinator(None), OFFICE, LAT, LON)
        with patch.object(_ha_weather_mod.WeatherEntity, "get_initial_entity_options",
                          lambda self: from_home_assistant, create=True):
            return entity.get_initial_entity_options()

    def test_its_settings_start_with_us_customary_units(self):
        self.assertEqual(self._initial(), {
            _ha_weather_mod.DOMAIN: {
                _ha_weather_mod.ATTR_WEATHER_TEMPERATURE_UNIT: _ha_const.UnitOfTemperature.FAHRENHEIT,
                _ha_weather_mod.ATTR_WEATHER_PRESSURE_UNIT: _ha_const.UnitOfPressure.INHG,
                _ha_weather_mod.ATTR_WEATHER_WIND_SPEED_UNIT: _ha_const.UnitOfSpeed.MILES_PER_HOUR,
                _ha_weather_mod.ATTR_WEATHER_VISIBILITY_UNIT: _ha_const.UnitOfLength.MILES,
                _ha_weather_mod.ATTR_WEATHER_PRECIPITATION_UNIT: _ha_const.UnitOfPrecipitationDepth.INCHES,
            },
        })

    def test_home_assistants_own_options_are_kept(self):
        options = self._initial({"cloud.alexa": {"should_expose": False}})
        self.assertEqual(options["cloud.alexa"], {"should_expose": False})
        self.assertIn(_ha_weather_mod.DOMAIN, options)

    def test_home_assistants_weather_options_are_kept_and_the_units_win(self):
        """Should WeatherEntity start to give weather options, they aren't dropped."""
        temperature_unit = _ha_weather_mod.ATTR_WEATHER_TEMPERATURE_UNIT
        weather = self._initial({_ha_weather_mod.DOMAIN: {"other": 1, temperature_unit: "°C"}})[
            _ha_weather_mod.DOMAIN]
        self.assertEqual(weather["other"], 1)
        self.assertIs(weather[temperature_unit], _ha_const.UnitOfTemperature.FAHRENHEIT)


class TestNativeUnits(unittest.TestCase):
    """#83: observations stay in NWS's metric units, so Home Assistant converts them once.

    Converting to °F, inHg, mph and mi and rounding first made a metric install convert
    them back: 101830 Pa showed as 1018.29 hPa next to the Barometric Pressure sensor's
    1018.3.
    """

    OBSERVATION = {
        "properties": {
            "temperature": {"value": 22.2},
            "relativeHumidity": {"value": 65.0},
            "barometricPressure": {"value": 101830},
            "textDescription": "Sunny",
            "timestamp": "2026-10-14T16:00:00+00:00",
            "dewpoint": {"value": 15.6},
            "visibility": {"value": 16090},
            "windSpeed": {"value": 9.252},
            "windDirection": {"value": 180},
            "windChill": {"value": None},
            "heatIndex": {"value": 24.1},
        },
    }

    def _entity(self, obs_data=None, forecast_data=None):
        from noaa_it_all.weather import NOAAWeather
        return NOAAWeather(_make_coordinator(obs_data), _make_coordinator(forecast_data), OFFICE, LAT, LON)

    def test_the_native_units_are_nws_metric_ones(self):
        from noaa_it_all.weather import NOAAWeather
        self.assertIs(NOAAWeather._attr_native_temperature_unit, _ha_const.UnitOfTemperature.CELSIUS)
        self.assertIs(NOAAWeather._attr_native_pressure_unit, _ha_const.UnitOfPressure.HPA)
        self.assertIs(NOAAWeather._attr_native_wind_speed_unit, _ha_const.UnitOfSpeed.KILOMETERS_PER_HOUR)
        self.assertIs(NOAAWeather._attr_native_visibility_unit, _ha_const.UnitOfLength.KILOMETERS)

    def test_observations_are_nws_values_unrounded(self):
        entity = self._entity(self.OBSERVATION)
        entity._handle_coordinator_update()
        self.assertEqual(entity._attr_native_temperature, 22.2)
        self.assertEqual(entity._attr_native_dew_point, 15.6)
        self.assertEqual(entity._attr_native_apparent_temperature, 24.1)
        self.assertEqual(entity._attr_native_pressure, 1018.3)
        self.assertEqual(entity._attr_native_wind_speed, 9.252)
        self.assertEqual(entity._attr_native_visibility, 16.09)

    def test_the_forecast_is_converted_to_the_native_units(self):
        hourly = {"properties": {"periods": [_period("2026-10-14T12:00:00-04:00", True, 75, "")]}}
        extended = {"properties": {"periods": [
            _period("2026-10-14T10:00:00-04:00", True, 75, "Today"),
            _period("2026-10-14T18:00:00-04:00", False, 52, "Tonight"),
        ]}}
        entity = self._entity(None, {"hourly": hourly, "extended": extended})
        with patch("noaa_it_all.weather.Forecast", dict), \
                patch("noaa_it_all.weather.datetime", _frozen_now(10, 0)):
            (day,) = asyncio.run(entity.async_forecast_daily())
            (hour,) = asyncio.run(entity.async_forecast_hourly())
        self.assertAlmostEqual(day["native_temperature"], 23.8889, places=4)
        self.assertAlmostEqual(day["native_templow"], 11.1111, places=4)
        self.assertAlmostEqual(hour["native_temperature"], 23.8889, places=4)
        # "5 mph"
        self.assertAlmostEqual(day["native_wind_speed"], 8.04672)
        self.assertAlmostEqual(hour["native_wind_speed"], 8.04672)

    def test_the_forecast_uses_the_native_keys(self):
        """The plain keys only convert through a fallback Home Assistant keeps for old integrations."""
        extended = {"properties": {"periods": [
            _period("2026-10-14T10:00:00-04:00", True, 75, "Today"),
            _period("2026-10-14T18:00:00-04:00", False, 52, "Tonight"),
        ]}}
        entity = self._entity(None, {"extended": extended})
        with patch("noaa_it_all.weather.Forecast", dict), \
                patch("noaa_it_all.weather.datetime", _frozen_now(10, 0)):
            (day,) = asyncio.run(entity.async_forecast_daily())
        self.assertEqual({"temperature", "templow", "wind_speed"} & set(day), set())

    def test_a_us_customary_install_still_shows_nws_fahrenheit(self):
        """Home Assistant converts °C back with ×1.8 + 32 and shows whole °F there."""
        from noaa_it_all.weather import NOAAWeather
        for fahrenheit in range(-60, 131):
            with self.subTest(fahrenheit):
                period = {"temperature": fahrenheit, "temperatureUnit": "F"}
                self.assertEqual(_f(NOAAWeather._forecast_temperature(period)), fahrenheit)

    def test_a_forecast_in_si_units_is_not_converted(self):
        from noaa_it_all.weather import NOAAWeather
        self.assertEqual(NOAAWeather._forecast_temperature({"temperature": 20, "temperatureUnit": "C"}), 20)
        self.assertEqual(NOAAWeather._parse_wind_speed("10 to 20 km/h"), 15)

    def test_an_odd_forecast_value_empties_only_that_field(self):
        """Before, Home Assistant skipped a field it couldn't convert; the conversion here must too."""
        from noaa_it_all.weather import NOAAWeather
        for temperature in (None, "75", True, {"unitCode": "wmoUnit:degF", "value": 75}):
            with self.subTest(temperature=temperature):
                self.assertIsNone(NOAAWeather._forecast_temperature({"temperature": temperature}))
        self.assertIsNone(NOAAWeather._forecast_temperature(None))
        for wind in (None, "", "calm", {"unitCode": "wmoUnit:km_h-1", "value": 10}):
            with self.subTest(wind=wind):
                self.assertIsNone(NOAAWeather._parse_wind_speed(wind))
        self.assertAlmostEqual(NOAAWeather._parse_wind_speed("5 to 10 mph"), 12.07008)


if __name__ == "__main__":
    unittest.main()
