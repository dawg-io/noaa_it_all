"""Tests for space weather and surf sensor entity state logic."""

import json
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
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
# Str enums, like Home Assistant's.
_ha_sensor.SensorDeviceClass = StrEnum("SensorDeviceClass", {"TIMESTAMP": "timestamp"})
_ha_sensor.SensorStateClass = StrEnum("SensorStateClass", {"MEASUREMENT": "measurement"})

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

    def test_state_of_a_whole_number_dst(self):
        sensor = self._make([{"time_tag": "2026-10-14T08:00:00", "dst": 5}])
        with patch("noaa_it_all.sensors.space_weather.datetime", _at("2026-10-14 08:05")):
            self.assertEqual(sensor.native_value, 5.0)

    def test_state_no_data(self):
        from noaa_it_all.sensors.space_weather import GeomagneticSensor
        coord = _make_coordinator(None)
        sensor = GeomagneticSensor(coord, OFFICE)
        self.assertIsNone(sensor.native_value)

    def test_state_empty_dst(self):
        sensor = self._make([])
        self.assertIsNone(sensor.native_value)

    def test_name(self):
        sensor = self._make()
        self.assertEqual(sensor.name, "Geomagnetic Storm")

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
        sensor = self._make([{"time_tag": "2026-10-14T08:00:00", "dst": -10}])
        with patch("noaa_it_all.sensors.space_weather.datetime", _at("2026-10-14 08:05")):
            self.assertIn("Quiet", sensor.state)

    def test_state_no_data(self):
        from noaa_it_all.sensors.space_weather import GeomagneticSensorInterpretation
        coord = _make_coordinator(None)
        sensor = GeomagneticSensorInterpretation(coord, OFFICE)
        self.assertIsNone(sensor.state)

    def test_name(self):
        sensor = self._make()
        self.assertEqual(sensor.name, "Geomagnetic Storm Interpretation")

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
        self.assertEqual(sensor.name, "Planetary K-index")

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
        self.assertEqual(sensor.name, "Planetary K-index Rating")

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

    def test_failed_forecast_fetch_is_unknown_not_low(self):
        """#33 P1.2: a failed SRF fetch must not read as Low risk."""
        from noaa_it_all.sensors.surf import RipCurrentRiskSensor
        # What the surf coordinator returns when only the SRF fetch failed.
        coord = _make_coordinator({"source_url": "", "wave_height_ft": 3.0})
        sensor = RipCurrentRiskSensor(coord, OFFICE)
        self.assertIsNone(sensor.state)


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

    def test_state_no_data(self):
        from noaa_it_all.sensors.space_weather import AuroraNextTimeSensor
        coord = _make_coordinator(None)
        sensor = AuroraNextTimeSensor(coord, OFFICE)
        self.assertIsNone(sensor.native_value)

    def test_state_without_a_forecast_is_unknown(self):
        sensor = self._make([{"kp_index": 3.0}])
        self.assertIsNone(sensor.native_value)

    def test_unique_id(self):
        sensor = self._make()
        self.assertEqual(sensor.unique_id, f"noaa_{OFFICE}_aurora_next_time")

    def test_icon(self):
        sensor = self._make()
        self.assertEqual(sensor.icon, "mdi:weather-night")

    def test_extra_attrs_with_data(self):
        sensor = self._make([{"kp_index": 5.0}])
        attrs = sensor.extra_state_attributes
        self.assertEqual(attrs["current_kp"], 5.0)
        self.assertIn("required_kp", attrs)

    def test_extra_attrs_with_a_null_current_kp(self):
        sensor = self._make([{"kp_index": None}])
        self.assertIsNone(sensor.extra_state_attributes["current_kp"])

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
        self.assertEqual(sensor.name, "Aurora Duration")


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
        self.assertEqual(sensor.name, "Aurora Visibility Probability")

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
        self.assertEqual(sensor.name, "Solar Radiation Storm Alerts")

    def test_device_info_space_group(self):
        sensor = self._make()
        info = sensor.device_info
        ids = list(info["identifiers"])[0]
        self.assertIn("space", ids[1])


def _at(when):
    """A datetime class whose now() is ``when``, a UTC time such as ``2026-01-19 19:00``."""
    fixed = datetime.fromisoformat(when).replace(tzinfo=timezone.utc)

    class _Frozen(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed if tz is None else fixed.astimezone(tz)
    return _Frozen


class TestSolarRadiationStormProducts(unittest.TestCase):
    """#78: only solar radiation storm (S-scale) products still in effect count.

    space_weather_alerts.json holds real alerts.json products, newest first as
    SWPC serves them: the January 2026 S4 storm, a cancelled warning, a
    cancelled summary and 100 MeV products from the live feed's archived
    copies, and the products the sensor used to count from the feed on
    2026-10-14 (12 electron flux and 2 Type IV radio emission alerts).
    """

    def _sensor(self, when):
        """The sensor with alerts.json as at ``when``: the products of the 30 days before it."""
        from noaa_it_all.sensors.space_weather import SolarRadiationStormAlertsSensor
        issued_by = datetime.fromisoformat(when)
        feed = [a for a in _load_fixture("space_weather_alerts.json")
                if timedelta(0) <= issued_by - datetime.fromisoformat(a["issue_datetime"]) <= timedelta(days=30)]
        return SolarRadiationStormAlertsSensor(_make_coordinator({"space_alerts": feed}), OFFICE)

    def _state(self, when):
        sensor = self._sensor(when)
        with patch("noaa_it_all.sensors.space_weather.datetime", _at(when)):
            return sensor.state, sensor.extra_state_attributes

    def _ids(self, attrs):
        return sorted(alert["product_id"] for alert in attrs["alerts"])

    def test_the_feed_on_the_day_it_read_14_has_no_radiation_storm(self):
        state, attrs = self._state("2026-10-14 08:00")
        self.assertEqual(state, 0)
        self.assertEqual(attrs["alerts"], [])

    def test_radio_emission_and_electron_flux_alerts_do_not_count(self):
        """Type II alerts mention coronal mass ejections; Type IV ones, solar radiation storms."""
        from noaa_it_all.parsers import radiation_storm_products_in_effect
        alerts = [a for a in _load_fixture("space_weather_alerts.json")
                  if a["product_id"] in ("TIIA", "TIVA", "EF3A")]
        self.assertTrue(any("coronal mass ejection" in a["message"].lower() for a in alerts))
        self.assertTrue(any("solar radiation storm" in a["message"].lower() for a in alerts))
        now = datetime(2026, 10, 14, 8, tzinfo=timezone.utc)
        self.assertEqual(radiation_storm_products_in_effect(alerts, now), [])

    def test_at_the_height_of_the_january_2026_s4_storm(self):
        state, attrs = self._state("2026-01-19 19:00")
        self.assertEqual(state, 5)
        self.assertEqual(self._ids(attrs), ["P11A", "P11W", "P12A", "P13A", "P14A"])

    def test_an_extended_warning_replaces_the_one_it_extends(self):
        """Serials 617, 618 and 619 were each extended; only 620 counts."""
        _, attrs = self._state("2026-01-19 19:00")
        warnings = [a for a in attrs["alerts"] if a["product_id"] == "P11W"]
        self.assertEqual(len(warnings), 1)
        self.assertIn("Serial Number: 620", warnings[0]["message_summary"])

    def test_an_alert_ends_when_its_summary_is_issued(self):
        """The S4 and S3 summaries came out at 23:21 and 01:03."""
        state, attrs = self._state("2026-01-20 02:00")
        self.assertEqual(state, 3)
        self.assertEqual(self._ids(attrs), ["P11A", "P11W", "P12A"])

    def test_nothing_counts_once_the_storm_is_over(self):
        state, _ = self._state("2026-01-23 00:00")
        self.assertEqual(state, 0)

    def test_a_warning_counts_until_it_expires(self):
        """Serial 628 was valid to 2026 Jul 31 0900 UTC."""
        self.assertIn("P11W", self._ids(self._state("2026-07-31 08:59")[1]))
        self.assertNotIn("P11W", self._ids(self._state("2026-07-31 09:01")[1]))

    def test_a_cancelled_warning_stops_counting(self):
        self.assertEqual(self._state("2026-06-30 16:20")[0], 1)
        self.assertEqual(self._state("2026-06-30 16:40")[0], 0)

    def test_a_summary_cancelled_for_a_wrong_time_leaves_the_event_ended(self):
        self.assertEqual(self._state("2026-05-26 12:00")[0], 2)
        self.assertEqual(self._state("2026-05-27 15:00")[0], 0)

    def test_100_mev_products_have_no_s_scale(self):
        state, attrs = self._state("2026-07-30 19:10")
        self.assertEqual(state, 2)
        self.assertEqual(self._ids(attrs), ["P11A", "P11W"])

    def _products(self, *keys):
        """Real fixture products, by (product_id, issue_datetime prefix)."""
        fixture = _load_fixture("space_weather_alerts.json")
        return [next(a for a in fixture if a["product_id"] == pid and a["issue_datetime"].startswith(t))
                for pid, t in keys]

    def _in_effect(self, alerts, when):
        from noaa_it_all.parsers import radiation_storm_products_in_effect
        now = datetime.fromisoformat(when).replace(tzinfo=timezone.utc)
        return radiation_storm_products_in_effect(alerts, now)

    def test_a_summary_ends_only_the_event_it_summarises(self):
        """SWPC summarised the 26 May event (over at 04:25) at 02:27 the next day.

        A second S1 alert, here the 26 May one re-timed to 20:00 that evening,
        began after that event ended, so the late summary doesn't end it.
        """
        first, summary = self._products(("P11A", "2026-05-26 00:35"), ("P11S", "2026-05-27 02:27"))
        second = dict(first, issue_datetime="2026-05-26 20:05:00.000", message=first["message"]
                      .replace("Serial Number: 365", "Serial Number: 999")
                      .replace("Begin Time: 2026 May 26 0010 UTC", "Begin Time: 2026 May 26 2000 UTC"))
        self.assertNotEqual(second["message"], first["message"])
        self.assertEqual(self._in_effect([summary, second, first], "2026-05-27 03:00"), [second])

    def test_a_cancelled_summary_ends_nothing(self):
        """Summary 130 was cancelled; without 129 the 26 May alert would still be in effect."""
        alert, cancelled, cancel = self._products(
            ("P11A", "2026-05-26 00:35"), ("P11S", "2026-05-27 02:28"), ("P11S", "2026-05-27 14:45"))
        self.assertEqual(self._in_effect([cancel, cancelled, alert], "2026-05-27 15:00"), [alert])

    def test_only_the_newest_alert_for_a_threshold_counts(self):
        """SWPC issued a second S1 alert on 22 January before summarising the first."""
        state, attrs = self._state("2026-01-22 12:00")
        self.assertEqual(state, 2)
        self.assertEqual(self._ids(attrs), ["P11A", "P11W"])

    def test_the_product_type_comes_from_its_id_not_its_wording(self):
        (alert,) = self._products(("P11A", "2026-05-26 00:35"))
        reworded = dict(alert, message=alert["message"].replace("ALERT: Proton", "Alert: Proton"))
        self.assertEqual(self._in_effect([reworded], "2026-05-26 01:00"), [reworded])

    def test_a_feed_that_is_not_a_list_is_unknown(self):
        from noaa_it_all.sensors.space_weather import SolarRadiationStormAlertsSensor
        for payload in ({}, {"error": "x"}, "x"):
            with self.subTest(payload=payload):
                sensor = SolarRadiationStormAlertsSensor(_make_coordinator({"space_alerts": payload}), OFFICE)
                self.assertIsNone(sensor.state)

    def test_a_product_that_fails_to_parse_still_counts(self):
        sensor = self._sensor("2026-06-30 16:20")
        with patch("noaa_it_all.sensors.space_weather.datetime", _at("2026-06-30 16:20")), \
                patch("noaa_it_all.sensors.space_weather.extract_storm_scale", side_effect=ValueError), \
                self.assertLogs("noaa_it_all.sensors.space_weather", level="WARNING"):
            self.assertEqual(sensor.state, 1)
            self.assertEqual(sensor.extra_state_attributes["total_alerts"], 1)

    def test_a_warning_gives_its_valid_window_and_stated_scale(self):
        """Warning 620 states S1, though its comment mentions an upgrade to S4."""
        _, attrs = self._state("2026-01-19 19:00")
        (warning,) = [a for a in attrs["alerts"] if a["product_id"] == "P11W"]
        self.assertEqual((warning["begin_time"], warning["end_time"], warning["scale"]),
                         ("2026 Jan 18 2130 UTC", "2026 Jan 20 2359 UTC", "S1"))

    def test_an_empty_field_is_not_read_from_the_next_line(self):
        from noaa_it_all.parsers import _message_field, _swpc_time
        self.assertIsNone(_message_field("Valid To: \r\nWarning Condition: Onset\r\n", "Valid To"))
        self.assertEqual(_swpc_time("2026 Jan 19 2359 UTC"), datetime(2026, 1, 19, 23, 59, tzinfo=timezone.utc))
        self.assertIsNone(_swpc_time("2026 Okt 19 2359 UTC"))

    def test_a_failed_alerts_fetch_is_unknown_not_zero(self):
        from noaa_it_all.sensors.space_weather import SolarRadiationStormAlertsSensor
        sensor = SolarRadiationStormAlertsSensor(_make_coordinator({"space_alerts": None}), OFFICE)
        self.assertIsNone(sensor.state)
        self.assertEqual(sensor.extra_state_attributes, {})


class TestAuroraNextTimeFromTheKpForecast(unittest.TestCase):
    """#79: the start of the next forecast period whose Kp reaches the location's threshold.

    space_weather_kp_forecast.json is SWPC's 3-day Kp forecast from
    2026-10-14 08:05 UTC, oldest first: observed periods to 03:00, estimated
    ones for the rest of the day (3.67 at 06:00 and 09:00, then 2.67, 3.0,
    3.33 and 3.33) and predicted ones to 2026-10-17 00:00 (at most 3.33).
    """

    NOW = "2026-10-14 08:05"

    def _sensor(self, office="DLH", forecast="fixture", lat=None, lon=None):
        from noaa_it_all.sensors.space_weather import AuroraNextTimeSensor
        if forecast == "fixture":
            forecast = _load_fixture("space_weather_kp_forecast.json")
        data = {"kp_index": [{"kp_index": 1}], "kp_forecast": forecast}
        return AuroraNextTimeSensor(_make_coordinator(data), office, lat, lon)

    def _value(self, sensor, when=None):
        with patch("noaa_it_all.sensors.space_weather.datetime", _at(when or self.NOW)):
            return sensor.native_value, sensor.extra_state_attributes

    def test_is_a_timestamp_sensor(self):
        sensor = self._sensor()
        self.assertEqual(sensor.device_class, "timestamp")
        self.assertIsInstance(sensor, _ha_sensor.SensorEntity)

    def test_a_northern_location_gets_the_next_period_with_enough_kp(self):
        """Duluth needs Kp 3; the 09:00 period is forecast at 3.67."""
        value, attrs = self._value(self._sensor("DLH"))
        self.assertEqual(value, datetime(2026, 10, 14, 9, tzinfo=timezone.utc))
        self.assertEqual(attrs["predicted_kp"], 3.67)
        self.assertEqual(attrs["required_kp"], 3)

    def test_the_period_in_progress_does_not_count(self):
        """At 08:05 the 06:00 period was estimated at 3.67 but measured at Kp 1; it was observed at 1.67."""
        value, _ = self._value(self._sensor("DLH"), "2026-10-14 06:30")
        self.assertEqual(value, datetime(2026, 10, 14, 9, tzinfo=timezone.utc))

    def test_periods_below_the_threshold_are_skipped(self):
        """After 09:00 the next period at 3 or more is 15:00 (3.0)."""
        value, _ = self._value(self._sensor("DLH"), "2026-10-14 09:30")
        self.assertEqual(value, datetime(2026, 10, 14, 15, tzinfo=timezone.utc))

    def test_observed_periods_never_count(self):
        forecast = [dict(p, observed="observed") if p["time_tag"] == "2026-10-14T09:00:00" else p
                    for p in _load_fixture("space_weather_kp_forecast.json")]
        value, _ = self._value(self._sensor("DLH", forecast=forecast))
        self.assertEqual(value, datetime(2026, 10, 14, 15, tzinfo=timezone.utc))

    def test_the_earliest_period_wins_whatever_the_feed_order(self):
        forecast = list(reversed(_load_fixture("space_weather_kp_forecast.json")))
        value, _ = self._value(self._sensor("DLH", forecast=forecast))
        self.assertEqual(value, datetime(2026, 10, 14, 9, tzinfo=timezone.utc))

    def test_the_state_and_required_kp_agree_below_magnetic_latitude_0(self):
        """Pago Pago is about -15.4 magnetic; it needs Kp 9, and a Kp 9 forecast reaches it."""
        forecast = [{"time_tag": "2026-10-14T12:00:00", "kp": 9.0, "observed": "predicted", "noaa_scale": "G5"}]
        value, attrs = self._value(self._sensor("PPG", forecast=forecast, lat=-14.27, lon=-170.70))
        self.assertEqual(attrs["required_kp"], 9)
        self.assertLess(attrs["magnetic_latitude"], 0)
        self.assertEqual(value, datetime(2026, 10, 14, 12, tzinfo=timezone.utc))

    def test_unknown_when_no_period_reaches_the_threshold(self):
        """Wilmington needs Kp 7; the forecast tops out at 3.67."""
        value, attrs = self._value(self._sensor("ILM"))
        self.assertIsNone(value)
        self.assertEqual(attrs["required_kp"], 7)

    def test_does_not_move_with_the_clock(self):
        sensor = self._sensor("DLH")
        self.assertEqual(self._value(sensor, "2026-10-14 08:05")[0],
                         self._value(sensor, "2026-10-14 08:55")[0])

    def test_an_odd_current_kp_payload_does_not_break_the_attributes(self):
        from noaa_it_all.sensors.space_weather import AuroraNextTimeSensor
        for kp_index in ({"error": "x"}, [None], [{"kp_index": "1"}], None):
            with self.subTest(kp_index=kp_index):
                data = {"kp_index": kp_index, "kp_forecast": _load_fixture("space_weather_kp_forecast.json")}
                sensor = AuroraNextTimeSensor(_make_coordinator(data), "DLH")
                self.assertIsNone(self._value(sensor)[1]["current_kp"])

    def test_a_failed_forecast_fetch_is_unknown(self):
        value, _ = self._value(self._sensor("DLH", forecast=None))
        self.assertIsNone(value)

    def test_a_null_or_missing_kp_is_skipped(self):
        forecast = [
            {"time_tag": "2026-10-14T09:00:00", "kp": None, "observed": "estimated", "noaa_scale": None},
            {"time_tag": "2026-10-14T12:00:00", "observed": "predicted", "noaa_scale": None},
            {"time_tag": "2026-10-14T15:00:00", "kp": "5", "observed": "predicted", "noaa_scale": None},
            {"time_tag": "2026-10-14T18:00:00", "kp": 4.0, "observed": "predicted", "noaa_scale": None},
        ]
        value, _ = self._value(self._sensor("DLH", forecast=forecast))
        self.assertEqual(value, datetime(2026, 10, 14, 18, tzinfo=timezone.utc))

    def test_no_data_at_all_is_unknown(self):
        from noaa_it_all.sensors.space_weather import AuroraNextTimeSensor
        sensor = AuroraNextTimeSensor(_make_coordinator(None), OFFICE)
        self.assertIsNone(self._value(sensor)[0])


class TestDstReadsTheNewestSample(unittest.TestCase):
    """#80: SWPC serves geospace_dst_1_hour.json oldest first; the sensors read the newest sample.

    space_weather_dst.json is the end of the live feed fetched at 08:04 UTC on
    2026-10-14, whose newest sample, at 08:27, runs ahead of the clock as the
    Geospace model does. space_weather_dst_storm.json is the end of an
    archived copy from the 2024-05-11 storm, when Dst went from -95.8 to
    -117.8 nT.
    """

    LIVE = "2026-10-14 08:05"
    STORM = "2024-05-11 23:00"

    def _sensors(self, dst):
        from noaa_it_all.sensors.space_weather import (
            GeomagneticSensor, GeomagneticSensorInterpretation,
        )
        coord = _make_coordinator({"dst": dst})
        return GeomagneticSensor(coord, OFFICE), GeomagneticSensorInterpretation(coord, OFFICE)

    def _read(self, dst, when):
        storm, interpretation = self._sensors(dst)
        with patch("noaa_it_all.sensors.space_weather.datetime", _at(when)):
            return storm.native_value, interpretation.state, storm.extra_state_attributes

    def test_the_fixtures_are_in_the_feed_order(self):
        for name in ("space_weather_dst.json", "space_weather_dst_storm.json"):
            tags = [s["time_tag"] for s in _load_fixture(name)]
            self.assertEqual(tags, sorted(tags), name)

    def test_geomagnetic_storm_is_the_newest_sample_in_nt_to_one_decimal(self):
        storm, _ = self._sensors(_load_fixture("space_weather_dst.json"))  # -3.9576199 ... -3.5359199
        with patch("noaa_it_all.sensors.space_weather.datetime", _at(self.LIVE)):
            self.assertEqual(storm.native_value, -3.5)
            self.assertEqual(storm.extra_state_attributes, {"timestamp": "2026-10-14T08:27:00+00:00"})
        self.assertEqual(storm.native_unit_of_measurement, "nT")
        self.assertEqual(storm.state_class, "measurement")
        self.assertEqual(storm.suggested_display_precision, 1)
        self.assertIsInstance(storm, _ha_sensor.SensorEntity)

    def test_interpretation_is_of_the_newest_sample(self):
        _, state, _ = self._read(_load_fixture("space_weather_dst_storm.json"), self.STORM)
        # The oldest sample, -95.8, would read Moderate Storm.
        self.assertEqual(state, "Strong Storm")

    def test_the_newest_by_time_whatever_the_order(self):
        value, state, _ = self._read(list(reversed(_load_fixture("space_weather_dst_storm.json"))), self.STORM)
        self.assertEqual((value, state), (-117.8, "Strong Storm"))

    def test_both_sensors_judge_the_value_shown(self):
        """-19.96 shows as -20.0 nT, which is a Minor Storm."""
        value, state, _ = self._read([{"time_tag": "2026-10-14T08:00:00", "dst": -19.96}], self.LIVE)
        self.assertEqual((value, state), (-20.0, "Minor Storm"))

    def test_a_value_just_below_zero_is_not_minus_zero(self):
        value, _, _ = self._read([{"time_tag": "2026-10-14T08:00:00", "dst": -0.04}], self.LIVE)
        self.assertEqual(str(value), "0.0")

    def test_a_null_newest_sample_falls_back_to_the_one_before(self):
        dst = [{"time_tag": "2026-10-14T08:26:00", "dst": -3.57},
               {"time_tag": "2026-10-14T08:27:00", "dst": None}]
        value, _, _ = self._read(dst, self.LIVE)
        self.assertEqual(value, -3.6)

    def test_a_feed_that_stopped_updating_is_unknown(self):
        """Two hours after its newest sample, a feed served unchanged no longer reads as now."""
        value, state, _ = self._read(_load_fixture("space_weather_dst.json"), "2026-10-14 10:30")
        self.assertEqual((value, state), (None, None))

    def test_a_failed_or_malformed_fetch_is_unknown(self):
        for dst in (None, [], {}, {"error": "x"}, [None], [["time_tag", "dst"], ["2026-10-14 08:00:00", "-3"]],
                    [{"time_tag": "2026-10-14T08:00:00", "dst": float("nan")}],
                    [{"time_tag": "2026-10-14T08:00:00", "dst": float("-inf")}],
                    [{"dst": -3.5}]):
            with self.subTest(dst=dst):
                value, state, attrs = self._read(dst, self.LIVE)
                self.assertEqual((value, state, attrs), (None, None, {}))


if __name__ == "__main__":
    unittest.main()
