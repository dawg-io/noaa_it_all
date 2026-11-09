"""Tests for forecast, alerts, and extra weather sensor entities.

Covers: ExtendedForecastSensor, HourlyForecastSensor, NWSAlertsSensor,
CloudCoverSensor, SnowfallForecastSensor, RadarTimestampSensor,
ForecastDiscussionSensor.
"""

import json
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
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

_MOCK_MODULES = {
    "homeassistant": MagicMock(),
    "homeassistant.helpers": MagicMock(),
    "homeassistant.helpers.entity": _ha_entity,
    "homeassistant.helpers.update_coordinator": _ha_coordinator,
    "homeassistant.helpers.entity_platform": MagicMock(),
    "homeassistant.helpers.aiohttp_client": MagicMock(),
    "homeassistant.components": MagicMock(),
    "homeassistant.components.sensor": _ha_sensor,
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
        self.assertEqual(sensor.name, "Extended Forecast")

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
        self.assertEqual(sensor.name, "Hourly Forecast")

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
        self.assertEqual(sensor.name, "Active NWS Alerts")

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
        self.assertEqual(sensor.name, "Cloud Cover")

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
# Snowfall Forecast sensor
# ---------------------------------------------------------------
def _blocks(start, count, mm_per_block, hours=6, overrides=None):
    """A gridpoint series of ``count`` blocks of ``hours`` from ``start`` (UTC)."""
    values = []
    for i in range(count):
        block = start + timedelta(hours=hours * i)
        mm = (overrides or {}).get(block, mm_per_block)
        values.append({"validTime": block.strftime("%Y-%m-%dT%H:%M:%S+00:00") + f"/PT{hours}H", "value": mm})
    return {"uom": "wmoUnit:mm", "values": values}


class TestSnowfallForecastSensor(unittest.TestCase):
    """Snow depth over the next 24 hours, and each local day's snow and ice.

    Chicago, 2026-11-09 10:30 CST (16:30 UTC). Snow is 1 mm an hour from 06:00 CST
    (12:00 UTC) for 60 hours, to 18:00 CST on the 11th, except 2 mm an hour from
    midnight to 06:00 CST on the 10th. Ice is 0.1 mm an hour for the first 24 hours,
    to 06:00 CST on the 10th.
    """

    NOW = datetime(2026, 11, 9, 16, 30, tzinfo=timezone.utc)

    @staticmethod
    def _gridpoint():
        first = datetime(2026, 11, 9, 12, tzinfo=timezone.utc)
        return {"properties": {
            "snowfallAmount": _blocks(first, 10, 6.0, overrides={datetime(2026, 11, 10, 6, tzinfo=timezone.utc): 12.0}),
            "iceAccumulation": _blocks(first, 4, 0.6),
            "quantitativePrecipitation": _blocks(first, 10, 100.0),
        }}

    def _make(self, data="default", last_update_success=True, unit="in", now=None):
        from noaa_it_all.sensors.weather_extra import SnowfallForecastSensor
        coord = _make_coordinator(self._gridpoint() if data == "default" else data)
        coord.last_update_success = last_update_success
        sensor = SnowfallForecastSensor(coord, OFFICE, LAT, LON)
        sensor.hass = MagicMock()
        sensor.hass.config.time_zone = "America/Chicago"
        sensor.unit_of_measurement = unit
        when = now or self.NOW
        patcher = patch("noaa_it_all.sensors.weather_extra._now", lambda tz: when.astimezone(tz))
        patcher.start()
        self.addCleanup(patcher.stop)
        return sensor

    def test_name_unique_id_and_device(self):
        sensor = self._make()
        self.assertEqual(sensor.name, "Snowfall Forecast")
        self.assertEqual(sensor.unique_id, "noaa_ILM_34_2257_n77_9447_snowfall_forecast")
        self.assertEqual(list(sensor.device_info["identifiers"])[0][1], "noaa_ILM_weather")

    def test_units_let_home_assistant_convert_to_inches(self):
        sensor = self._make()
        self.assertIs(sensor.device_class, _ha_sensor.SensorDeviceClass.PRECIPITATION)
        self.assertEqual(sensor.native_unit_of_measurement, "mm")
        self.assertEqual(sensor.suggested_unit_of_measurement, "in")
        self.assertEqual(sensor.suggested_display_precision, 1)
        self.assertEqual(sensor.icon, "mdi:snowflake")

    def test_state_is_snow_depth_over_the_next_24_whole_hours(self):
        """From 16:00 UTC: 18 hours at 1 mm and 6 at 2 mm. Not the liquid equivalent."""
        self.assertEqual(self._make().native_value, 30.0)

    def test_no_snow_forecast_is_zero(self):
        data = self._gridpoint()
        data["properties"]["snowfallAmount"] = _blocks(datetime(2026, 11, 9, 12, tzinfo=timezone.utc), 10, 0)
        self.assertEqual(self._make(data).native_value, 0.0)

    def test_24_hours_the_forecast_doesnt_fully_cover_are_unknown(self):
        """At 19:30 CST on the 10th the forecast ends 23 whole hours on."""
        sensor = self._make(now=datetime(2026, 11, 11, 1, 30, tzinfo=timezone.utc))
        self.assertIsNone(sensor.native_value)
        self.assertIsNone(sensor.extra_state_attributes["ice_next_24h"])

    def test_a_failed_fetch_is_unknown_not_zero(self):
        """A failure never reads as safe: no snow is never shown for a forecast that didn't arrive."""
        for sensor in (self._make(last_update_success=False), self._make(data=None),
                       self._make(data={"properties": {}})):
            with self.subTest():
                self.assertIsNone(sensor.native_value)
                self.assertEqual(sensor.extra_state_attributes, {"ice_next_24h": None, "days": []})

    def test_days_are_local_dates_today_from_now(self):
        """Today 16:00-06:00 UTC is 14 hours; the 10th has 6 at 2 mm and 18 at 1; the 11th isn't covered."""
        attrs = self._make(unit="mm").extra_state_attributes
        self.assertEqual(attrs["days"], [
            {"date": "2026-11-09", "snowfall": 14.0, "ice": 1.4},
            {"date": "2026-11-10", "snowfall": 30.0, "ice": None},
            {"date": "2026-11-11", "snowfall": None, "ice": None},
        ])
        self.assertIsNone(attrs["ice_next_24h"])

    def test_ice_next_24h(self):
        sensor = self._make(now=datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc), unit="mm")
        self.assertEqual(sensor.extra_state_attributes["ice_next_24h"], 2.4)

    def test_attributes_are_in_the_unit_the_state_is_shown_in(self):
        """Home Assistant converts the state but not attributes, so the sensor does."""
        days = self._make(unit="in").extra_state_attributes["days"]
        self.assertEqual(days[0], {"date": "2026-11-09", "snowfall": 0.55, "ice": 0.06})
        self.assertEqual(days[1]["snowfall"], 1.18)
        self.assertEqual(self._make(unit="cm").extra_state_attributes["days"][1]["snowfall"], 3.0)

    def test_a_dst_change_day_has_its_25_hours(self):
        """Chicago leaves CDT on 2026-11-01, so that date runs 05:00 UTC to 06:00 UTC the next day."""
        data = {"properties": {"snowfallAmount": _blocks(
            datetime(2026, 10, 31, 17, tzinfo=timezone.utc), 44, 1.0, hours=1)}}
        days = self._make(data, unit="mm", now=datetime(2026, 10, 31, 17, tzinfo=timezone.utc)
                          ).extra_state_attributes["days"]
        self.assertEqual(days[1], {"date": "2026-11-01", "snowfall": 25.0, "ice": None})


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
        self.assertEqual(sensor.name, "Radar Timestamp")

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
        self.assertEqual(sensor.name, "Forecast Discussion")

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

    def test_issue_time_is_read_from_the_header(self):
        # The header line NWS issues every discussion with. The month was
        # missing from the pattern, so this always read "Unknown".
        text = ("000\nFXUS62 KILM 131835\nAFDILM\n\nArea Forecast Discussion\n"
                "National Weather Service Wilmington NC\n235 PM EDT Tue Oct 13 2026\n\n"
                ".WHAT HAS CHANGED...\nNo major changes.")
        sensor = self._make({"discussion_text": text})
        self.assertEqual(sensor.extra_state_attributes["issue_time"], "235 PM EDT Tue Oct 13 2026")

    def test_issue_time_with_a_four_letter_zone(self):
        text = "Area Forecast Discussion\nNational Weather Service Tiyan GU\n1000 AM ChST Wed Oct 14 2026\n"
        sensor = self._make({"discussion_text": text})
        self.assertEqual(sensor.extra_state_attributes["issue_time"], "1000 AM ChST Wed Oct 14 2026")

    def test_device_info_weather_group(self):
        sensor = self._make()
        info = sensor.device_info
        ids = list(info["identifiers"])[0]
        self.assertIn("weather", ids[1])


if __name__ == "__main__":
    unittest.main()
